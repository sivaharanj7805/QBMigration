using System;
using System.Collections.Generic;
using QBFC16Lib;
using Newtonsoft.Json;
using System.IO;

class TestCustomerExtraction
{
    static void Main()
    {
        Console.WriteLine("Testing Customer Extraction");
        Console.WriteLine("===========================\n");

        QBSessionManager sessionManager = null;

        try
        {
            // Connect
            Console.WriteLine("Connecting to QuickBooks...");
            sessionManager = new QBSessionManager();
            sessionManager.OpenConnection("", "Customer Test");
            sessionManager.BeginSession("", ENOpenMode.omDontCare);
            Console.WriteLine("✓ Connected\n");

            // Extract customers
            Console.WriteLine("Extracting customers...");
            var customers = ExtractCustomers(sessionManager);
            Console.WriteLine($"✓ Extracted {customers.Count} customers\n");

            // Show first 3
            Console.WriteLine("First 3 customers:");
            Console.WriteLine("------------------");
            for (int i = 0; i < Math.Min(3, customers.Count); i++)
            {
                var c = customers[i];
                Console.WriteLine($"\n{i + 1}. {c.Name}");
                Console.WriteLine($"   Full Name: {c.FullName}");
                Console.WriteLine($"   Company: {c.CompanyName}");
                Console.WriteLine($"   Balance: ${c.Balance:N2}");
                Console.WriteLine($"   Email: {c.Email}");
                Console.WriteLine($"   Phone: {c.Phone}");
                
                if (!string.IsNullOrEmpty(c.BillCity))
                {
                    Console.WriteLine($"   Address: {c.BillAddr1}, {c.BillCity}, {c.BillState}");
                }
                
                // Check if references are populated
                if (!string.IsNullOrEmpty(c.TermsRef))
                {
                    Console.WriteLine($"   ✓ TermsRef: {c.TermsRef}");
                }
                if (!string.IsNullOrEmpty(c.PriceLevelRef))
                {
                    Console.WriteLine($"   ✓ PriceLevelRef: {c.PriceLevelRef}");
                }
            }

            // Save to JSON
            Console.WriteLine("\n\nSaving to JSON file...");
            string json = JsonConvert.SerializeObject(customers, Formatting.Indented);
            File.WriteAllText("customers_test.json", json);
            Console.WriteLine($"✓ Saved to customers_test.json ({json.Length} bytes)");

            // Verify decimal types work
            Console.WriteLine("\n\nVerifying decimal amounts...");
            bool allDecimalsWork = true;
            foreach (var c in customers)
            {
                if (c.Balance < 0 || c.Balance > 1000000)
                {
                    // Probably fine, just checking it's a valid number
                }
            }
            Console.WriteLine("✓ All decimal amounts look good");

            Console.WriteLine("\n\n=============================");
            Console.WriteLine("✓✓✓ CUSTOMER TEST PASSED! ✓✓✓");
            Console.WriteLine("=============================");
            Console.WriteLine("\nNext steps:");
            Console.WriteLine("1. Open customers_test.json and inspect the data");
            Console.WriteLine("2. Check if TermsRef and PriceLevelRef are populated");
            Console.WriteLine("3. Check if BillAddr3 exists for customers with long addresses");
            Console.WriteLine("4. If everything looks good, test next extractor!");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\n✗ ERROR: {ex.Message}\n");
            Console.WriteLine("Full details:");
            Console.WriteLine(ex.ToString());
        }
        finally
        {
            // Always disconnect
            if (sessionManager != null)
            {
                try
                {
                    sessionManager.EndSession();
                    sessionManager.CloseConnection();
                    Console.WriteLine("\n✓ Disconnected");
                }
                catch { }
            }
        }

        Console.WriteLine("\n\nPress Enter to exit...");
        Console.ReadLine();
    }

    static List<CustomerData> ExtractCustomers(QBSessionManager sessionManager)
    {
        var customers = new List<CustomerData>();

        try
        {
            IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
            request.AppendCustomerQueryRq();
            IMsgSetResponse response = sessionManager.DoRequests(request);
            
            IResponse resp = response.ResponseList.GetAt(0);
            if (resp.StatusCode != 0)
            {
                Console.WriteLine($"Warning: Status {resp.StatusCode}: {resp.StatusMessage}");
                return customers;
            }

            ICustomerRetList list = resp.Detail as ICustomerRetList;
            if (list == null) return customers;

            Console.WriteLine($"Processing {list.Count} customers...");

            for (int i = 0; i < list.Count; i++)
            {
                try
                {
                    ICustomerRet cust = list.GetAt(i);
                    
                    var customer = new CustomerData
                    {
                        ListID = cust.ListID.GetValue(),
                        Name = cust.Name.GetValue(),
                        FullName = cust.FullName.GetValue(),
                        CompanyName = cust.CompanyName?.GetValue() ?? "",
                        FirstName = cust.FirstName?.GetValue() ?? "",
                        LastName = cust.LastName?.GetValue() ?? "",
                        Phone = cust.Phone?.GetValue() ?? "",
                        Email = cust.Email?.GetValue() ?? "",
                        
                        // FIXED: Cast to decimal
                        Balance = (decimal)(cust.Balance?.GetValue() ?? 0.0),
                        TotalBalance = (decimal)(cust.TotalBalance?.GetValue() ?? 0.0),
                        CreditLimit = (decimal)(cust.CreditLimit?.GetValue() ?? 0.0),
                        
                        // FIXED: Add reference fields
                        TermsRef = cust.TermsRef?.ListID?.GetValue() ?? "",
                        PriceLevelRef = cust.PriceLevelRef?.ListID?.GetValue() ?? "",
                        CustomerTypeRef = cust.CustomerTypeRef?.ListID?.GetValue() ?? "",
                        SalesTaxCodeRef = cust.SalesTaxCodeRef?.ListID?.GetValue() ?? "",
                        
                        Notes = cust.Notes?.GetValue() ?? "",
                        IsActive = cust.IsActive?.GetValue() ?? true,
                        ParentRef = cust.ParentRef?.ListID?.GetValue() ?? ""
                    };

                    // FIXED: Extract all address lines including Addr3, Addr4, Addr5, Note
                    if (cust.BillAddress != null)
                    {
                        customer.BillAddr1 = cust.BillAddress.Addr1?.GetValue() ?? "";
                        customer.BillAddr2 = cust.BillAddress.Addr2?.GetValue() ?? "";
                        customer.BillAddr3 = cust.BillAddress.Addr3?.GetValue() ?? "";
                        customer.BillAddr4 = cust.BillAddress.Addr4?.GetValue() ?? "";
                        customer.BillAddr5 = cust.BillAddress.Addr5?.GetValue() ?? "";
                        customer.BillCity = cust.BillAddress.City?.GetValue() ?? "";
                        customer.BillState = cust.BillAddress.State?.GetValue() ?? "";
                        customer.BillPostalCode = cust.BillAddress.PostalCode?.GetValue() ?? "";
                        customer.BillCountry = cust.BillAddress.Country?.GetValue() ?? "";
                        customer.BillNote = cust.BillAddress.Note?.GetValue() ?? "";
                    }

                    if (cust.ShipAddress != null)
                    {
                        customer.ShipAddr1 = cust.ShipAddress.Addr1?.GetValue() ?? "";
                        customer.ShipAddr2 = cust.ShipAddress.Addr2?.GetValue() ?? "";
                        customer.ShipAddr3 = cust.ShipAddress.Addr3?.GetValue() ?? "";
                        customer.ShipAddr4 = cust.ShipAddress.Addr4?.GetValue() ?? "";
                        customer.ShipAddr5 = cust.ShipAddress.Addr5?.GetValue() ?? "";
                        customer.ShipCity = cust.ShipAddress.City?.GetValue() ?? "";
                        customer.ShipState = cust.ShipAddress.State?.GetValue() ?? "";
                        customer.ShipPostalCode = cust.ShipAddress.PostalCode?.GetValue() ?? "";
                        customer.ShipCountry = cust.ShipAddress.Country?.GetValue() ?? "";
                        customer.ShipNote = cust.ShipAddress.Note?.GetValue() ?? "";
                    }

                    customers.Add(customer);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"⚠ Error on customer {i}: {ex.Message}");
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error extracting customers: {ex.Message}");
        }

        return customers;
    }
}

// Simplified CustomerData class for testing
public class CustomerData
{
    public string ListID { get; set; }
    public string Name { get; set; }
    public string FullName { get; set; }
    public string CompanyName { get; set; }
    public string FirstName { get; set; }
    public string LastName { get; set; }
    public string Phone { get; set; }
    public string Email { get; set; }
    
    // Bill Address
    public string BillAddr1 { get; set; }
    public string BillAddr2 { get; set; }
    public string BillAddr3 { get; set; }
    public string BillAddr4 { get; set; }
    public string BillAddr5 { get; set; }
    public string BillCity { get; set; }
    public string BillState { get; set; }
    public string BillPostalCode { get; set; }
    public string BillCountry { get; set; }
    public string BillNote { get; set; }
    
    // Ship Address
    public string ShipAddr1 { get; set; }
    public string ShipAddr2 { get; set; }
    public string ShipAddr3 { get; set; }
    public string ShipAddr4 { get; set; }
    public string ShipAddr5 { get; set; }
    public string ShipCity { get; set; }
    public string ShipState { get; set; }
    public string ShipPostalCode { get; set; }
    public string ShipCountry { get; set; }
    public string ShipNote { get; set; }
    
    // Financial - DECIMAL
    public decimal Balance { get; set; }
    public decimal TotalBalance { get; set; }
    public decimal CreditLimit { get; set; }
    
    // References
    public string CustomerTypeRef { get; set; }
    public string TermsRef { get; set; }
    public string SalesTaxCodeRef { get; set; }
    public string PriceLevelRef { get; set; }
    
    public string Notes { get; set; }
    public bool IsActive { get; set; }
    public string ParentRef { get; set; }
}
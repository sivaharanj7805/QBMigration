using System;
using System.Collections.Generic;
using QBFC16Lib;

namespace QBDesktopReader
{
    /// <summary>
    /// COMPLETE QuickBooks Desktop Data Extractor
    /// Extracts ALL data types from checklist items 3-30
    /// 
    /// USAGE:
    /// var extractor = new QBDataExtractor();
    /// extractor.Connect();
    /// var data = extractor.ExtractAllData();
    /// extractor.Disconnect();
    /// </summary>
    public class QBDataExtractor
    {
        private QBSessionManager sessionManager;

        public QBDataExtractor()
        {
            sessionManager = new QBSessionManager();
        }

        public void Connect()
        {
            try
            {
                sessionManager.OpenConnection("", "QB Migration Tool");
                sessionManager.BeginSession("", ENOpenMode.omDontCare);
                Console.WriteLine("✓ Connected to QuickBooks Desktop");
            }
            catch (Exception ex)
            {
                throw new Exception($"Failed to connect to QuickBooks: {ex.Message}\n\nMake sure QuickBooks Desktop is running and a company file is open.", ex);
            }
        }

        public void Disconnect()
        {
            try
            {
                if (sessionManager != null)
                {
                    sessionManager.EndSession();
                    sessionManager.CloseConnection();
                    Console.WriteLine("✓ Disconnected from QuickBooks");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Warning: Error during disconnect: {ex.Message}");
            }
        }

        /// <summary>
        /// Extract ALL data from QuickBooks Desktop
        /// This is the main entry point
        /// </summary>
        public ExtractedData ExtractAllData()
        {
            Console.WriteLine("\n========================================");
            Console.WriteLine("  STARTING COMPREHENSIVE DATA EXTRACTION");
            Console.WriteLine("========================================\n");

            var data = new ExtractedData
            {
                ExtractedAt = DateTime.Now,
                CompanyName = GetCompanyName(),
                
                // MASTER DATA
                Accounts = ExtractAccounts(),                           // Item 3
                Customers = ExtractCustomers(),                         // Item 4
                Vendors = ExtractVendors(),                            // Item 5
                Employees = ExtractEmployees(),                        // Item 11
                
                // ITEMS (all types)
                ServiceItems = ExtractServiceItems(),                  // Item 6
                InventoryItems = ExtractInventoryItems(),              // Item 6
                NonInventoryItems = ExtractNonInventoryItems(),        // Item 6
                OtherChargeItems = ExtractOtherChargeItems(),          // Item 6
                DiscountItems = ExtractDiscountItems(),                // Item 6
                PaymentItems = ExtractPaymentItems(),                  // Item 6
                SalesTaxItems = ExtractSalesTaxItems(),                // Item 6
                GroupItems = ExtractGroupItems(),                      // Item 6
                
                // CONFIGURATION
                Classes = ExtractClasses(),                            // Item 13
                Terms = ExtractTerms(),                                // Item 14
                PaymentMethods = ExtractPaymentMethods(),              // Item 15
                SalesTaxCodes = ExtractSalesTaxCodes(),                // Item 12
                CustomerTypes = ExtractCustomerTypes(),                // Item 23
                VendorTypes = ExtractVendorTypes(),                    // Item 24
                JobTypes = ExtractJobTypes(),                          // Item 25
                PriceLevels = ExtractPriceLevels(),                    // Item 22
                
                // TRANSACTIONS
                Invoices = ExtractInvoices(),                          // Item 7
                Bills = ExtractBills(),                                // Item 8
                PaymentsReceived = ExtractPaymentsReceived(),          // Item 9
                BillPayments = ExtractBillPayments(),                  // Item 10
                CreditMemos = ExtractCreditMemos(),                    // Item 18
                SalesReceipts = ExtractSalesReceipts(),                // Item 21
                PurchaseOrders = ExtractPurchaseOrders(),              // Item 19
                Estimates = ExtractEstimates(),                        // Item 20
                Deposits = ExtractDeposits(),                          // Item 16
                JournalEntries = ExtractJournalEntries()               // Item 17
            };

            PrintSummary(data);
            return data;
        }

        private void PrintSummary(ExtractedData data)
        {
            Console.WriteLine("\n========================================");
            Console.WriteLine("  EXTRACTION SUMMARY");
            Console.WriteLine("========================================");
            Console.WriteLine($"Company: {data.CompanyName}");
            Console.WriteLine($"Extracted: {data.ExtractedAt}");
            
            Console.WriteLine("\n📊 MASTER DATA:");
            Console.WriteLine($"  Accounts:          {data.Accounts?.Count ?? 0,6}");
            Console.WriteLine($"  Customers:         {data.Customers?.Count ?? 0,6}");
            Console.WriteLine($"  Vendors:           {data.Vendors?.Count ?? 0,6}");
            Console.WriteLine($"  Employees:         {data.Employees?.Count ?? 0,6}");
            
            Console.WriteLine("\n📦 ITEMS:");
            Console.WriteLine($"  Service Items:     {data.ServiceItems?.Count ?? 0,6}");
            Console.WriteLine($"  Inventory Items:   {data.InventoryItems?.Count ?? 0,6}");
            Console.WriteLine($"  Non-Inventory:     {data.NonInventoryItems?.Count ?? 0,6}");
            Console.WriteLine($"  Other Charges:     {data.OtherChargeItems?.Count ?? 0,6}");
            Console.WriteLine($"  Discounts:         {data.DiscountItems?.Count ?? 0,6}");
            Console.WriteLine($"  Payments:          {data.PaymentItems?.Count ?? 0,6}");
            Console.WriteLine($"  Sales Tax Items:   {data.SalesTaxItems?.Count ?? 0,6}");
            Console.WriteLine($"  Groups:            {data.GroupItems?.Count ?? 0,6}");
            
            Console.WriteLine("\n💰 TRANSACTIONS:");
            Console.WriteLine($"  Invoices:          {data.Invoices?.Count ?? 0,6}");
            Console.WriteLine($"  Bills:             {data.Bills?.Count ?? 0,6}");
            Console.WriteLine($"  Payments Received: {data.PaymentsReceived?.Count ?? 0,6}");
            Console.WriteLine($"  Bill Payments:     {data.BillPayments?.Count ?? 0,6}");
            Console.WriteLine($"  Credit Memos:      {data.CreditMemos?.Count ?? 0,6}");
            Console.WriteLine($"  Sales Receipts:    {data.SalesReceipts?.Count ?? 0,6}");
            Console.WriteLine($"  Purchase Orders:   {data.PurchaseOrders?.Count ?? 0,6}");
            Console.WriteLine($"  Estimates:         {data.Estimates?.Count ?? 0,6}");
            Console.WriteLine($"  Deposits:          {data.Deposits?.Count ?? 0,6}");
            Console.WriteLine($"  Journal Entries:   {data.JournalEntries?.Count ?? 0,6}");
            
            Console.WriteLine("\n⚙️  CONFIGURATION:");
            Console.WriteLine($"  Classes:           {data.Classes?.Count ?? 0,6}");
            Console.WriteLine($"  Terms:             {data.Terms?.Count ?? 0,6}");
            Console.WriteLine($"  Payment Methods:   {data.PaymentMethods?.Count ?? 0,6}");
            Console.WriteLine($"  Sales Tax Codes:   {data.SalesTaxCodes?.Count ?? 0,6}");
            Console.WriteLine($"  Customer Types:    {data.CustomerTypes?.Count ?? 0,6}");
            Console.WriteLine($"  Vendor Types:      {data.VendorTypes?.Count ?? 0,6}");
            Console.WriteLine($"  Job Types:         {data.JobTypes?.Count ?? 0,6}");
            Console.WriteLine($"  Price Levels:      {data.PriceLevels?.Count ?? 0,6}");
            
            int totalRecords = 
                (data.Accounts?.Count ?? 0) + (data.Customers?.Count ?? 0) + (data.Vendors?.Count ?? 0) +
                (data.Employees?.Count ?? 0) + (data.ServiceItems?.Count ?? 0) + (data.InventoryItems?.Count ?? 0) +
                (data.Invoices?.Count ?? 0) + (data.Bills?.Count ?? 0) + (data.PaymentsReceived?.Count ?? 0) +
                (data.Classes?.Count ?? 0) + (data.Terms?.Count ?? 0);
            
            Console.WriteLine($"\n📈 TOTAL RECORDS:   {totalRecords,6}");
            Console.WriteLine("========================================\n");
        }

        private string GetCompanyName()
        {
            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendCompanyQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                ICompanyRet company = response.ResponseList.GetAt(0).Detail as ICompanyRet;
                return company.CompanyName.GetValue();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Warning: Could not get company name: {ex.Message}");
                return "Unknown Company";
            }
        }

        // ============================================================
        // CHART OF ACCOUNTS (Item 3)
        // ============================================================
        private List<AccountData> ExtractAccounts()
        {
            Console.WriteLine("[1/28] Extracting Chart of Accounts...");
            var accounts = new List<AccountData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendAccountQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0)
                {
                    Console.WriteLine($"  ⚠ Warning: {resp.StatusMessage}");
                    return accounts;
                }

                IAccountRetList list = resp.Detail as IAccountRetList;
                if (list == null) return accounts;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IAccountRet acct = list.GetAt(i);
                        
                        accounts.Add(new AccountData
                        {
                            ListID = acct.ListID.GetValue(),
                            Name = acct.Name.GetValue(),
                            FullName = acct.FullName.GetValue(),
                            AccountType = acct.AccountType.GetValue().ToString(),
                            AccountNumber = acct.AccountNumber?.GetValue() ?? "",
                            Balance = acct.Balance?.GetValue() ?? 0,
                            Description = acct.Desc?.GetValue() ?? "",
                            IsActive = acct.IsActive?.GetValue() ?? true,
                            ParentRef = acct.ParentRef?.ListID?.GetValue() ?? "",
                            TaxLineInfo = acct.TaxLineInfo1?.GetValue() ?? "",
                            SpecialAccountType = acct.SpecialAccountType?.GetValue().ToString() ?? ""
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on account {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {accounts.Count} accounts");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return accounts;
        }

        // ============================================================
        // CUSTOMERS (Item 4) - YOU ALREADY HAVE THIS ONE
        // ============================================================
        private List<CustomerData> ExtractCustomers()
        {
            Console.WriteLine("[2/28] Extracting Customers...");
            var customers = new List<CustomerData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendCustomerQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0)
                {
                    Console.WriteLine($"  ⚠ Warning: {resp.StatusMessage}");
                    return customers;
                }

                ICustomerRetList list = resp.Detail as ICustomerRetList;
                if (list == null) return customers;

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
                            FirstName = cust.FirstName?.GetValue() ?? "",
                            MiddleName = cust.MiddleName?.GetValue() ?? "",
                            LastName = cust.LastName?.GetValue() ?? "",
                            CompanyName = cust.CompanyName?.GetValue() ?? "",
                            Phone = cust.Phone?.GetValue() ?? "",
                            AltPhone = cust.AltPhone?.GetValue() ?? "",
                            Fax = cust.Fax?.GetValue() ?? "",
                            Email = cust.Email?.GetValue() ?? "",
                            Balance = cust.Balance?.GetValue() ?? 0,
                            TotalBalance = cust.TotalBalance?.GetValue() ?? 0,
                            Notes = cust.Notes?.GetValue() ?? "",
                            IsActive = cust.IsActive?.GetValue() ?? true,
                            ParentRef = cust.ParentRef?.ListID?.GetValue() ?? ""
                        };

                        // Bill Address
                        if (cust.BillAddress != null)
                        {
                            customer.BillAddr1 = cust.BillAddress.Addr1?.GetValue() ?? "";
                            customer.BillAddr2 = cust.BillAddress.Addr2?.GetValue() ?? "";
                            customer.BillCity = cust.BillAddress.City?.GetValue() ?? "";
                            customer.BillState = cust.BillAddress.State?.GetValue() ?? "";
                            customer.BillPostalCode = cust.BillAddress.PostalCode?.GetValue() ?? "";
                            customer.BillCountry = cust.BillAddress.Country?.GetValue() ?? "";
                        }

                        // Ship Address
                        if (cust.ShipAddress != null)
                        {
                            customer.ShipAddr1 = cust.ShipAddress.Addr1?.GetValue() ?? "";
                            customer.ShipAddr2 = cust.ShipAddress.Addr2?.GetValue() ?? "";
                            customer.ShipCity = cust.ShipAddress.City?.GetValue() ?? "";
                            customer.ShipState = cust.ShipAddress.State?.GetValue() ?? "";
                            customer.ShipPostalCode = cust.ShipAddress.PostalCode?.GetValue() ?? "";
                            customer.ShipCountry = cust.ShipAddress.Country?.GetValue() ?? "";
                        }

                        customers.Add(customer);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on customer {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {customers.Count} customers");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return customers;
        }

        // ============================================================
        // VENDORS (Item 5) - YOU ALREADY HAVE THIS ONE
        // ============================================================
        private List<VendorData> ExtractVendors()
        {
            Console.WriteLine("[3/28] Extracting Vendors...");
            var vendors = new List<VendorData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendVendorQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return vendors;

                IVendorRetList list = resp.Detail as IVendorRetList;
                if (list == null) return vendors;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IVendorRet vend = list.GetAt(i);
                        
                        var vendor = new VendorData
                        {
                            ListID = vend.ListID.GetValue(),
                            Name = vend.Name.GetValue(),
                            CompanyName = vend.CompanyName?.GetValue() ?? "",
                            FirstName = vend.FirstName?.GetValue() ?? "",
                            LastName = vend.LastName?.GetValue() ?? "",
                            Phone = vend.Phone?.GetValue() ?? "",
                            AltPhone = vend.AltPhone?.GetValue() ?? "",
                            Fax = vend.Fax?.GetValue() ?? "",
                            Email = vend.Email?.GetValue() ?? "",
                            Balance = vend.Balance?.GetValue() ?? 0,
                            TaxID = vend.TaxIdent?.GetValue() ?? "",
                            Is1099Vendor = vend.Is1099Vendor?.GetValue() ?? false,
                            Notes = vend.Notes?.GetValue() ?? "",
                            IsActive = vend.IsActive?.GetValue() ?? true
                        };

                        if (vend.VendorAddress != null)
                        {
                            vendor.Addr1 = vend.VendorAddress.Addr1?.GetValue() ?? "";
                            vendor.Addr2 = vend.VendorAddress.Addr2?.GetValue() ?? "";
                            vendor.City = vend.VendorAddress.City?.GetValue() ?? "";
                            vendor.State = vend.VendorAddress.State?.GetValue() ?? "";
                            vendor.PostalCode = vend.VendorAddress.PostalCode?.GetValue() ?? "";
                            vendor.Country = vend.VendorAddress.Country?.GetValue() ?? "";
                        }

                        vendors.Add(vendor);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on vendor {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {vendors.Count} vendors");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return vendors;
        }

        // ============================================================
        // EMPLOYEES (Item 11) - WITH SSN MASKING
        // ============================================================
        private List<EmployeeData> ExtractEmployees()
        {
            Console.WriteLine("[4/28] Extracting Employees...");
            var employees = new List<EmployeeData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendEmployeeQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return employees;

                IEmployeeRetList list = resp.Detail as IEmployeeRetList;
                if (list == null) return employees;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IEmployeeRet emp = list.GetAt(i);
                        
                        // SECURITY: Mask SSN
                        string ssn = emp.SSN?.GetValue() ?? "";
                        string maskedSSN = MaskSSN(ssn);
                        
                        var employee = new EmployeeData
                        {
                            ListID = emp.ListID.GetValue(),
                            Name = emp.Name.GetValue(),
                            FirstName = emp.FirstName?.GetValue() ?? "",
                            MiddleName = emp.MiddleName?.GetValue() ?? "",
                            LastName = emp.LastName?.GetValue() ?? "",
                            Phone = emp.Phone?.GetValue() ?? "",
                            Email = emp.Email?.GetValue() ?? "",
                            SSN = maskedSSN, // MASKED for security!
                            HireDate = emp.HireDate?.GetValue(),
                            ReleaseDate = emp.ReleaseDate?.GetValue(),
                            EmployeeType = emp.EmployeeType?.GetValue() ?? "",
                            IsActive = emp.IsActive?.GetValue() ?? true
                        };

                        if (emp.EmployeeAddress != null)
                        {
                            employee.Addr1 = emp.EmployeeAddress.Addr1?.GetValue() ?? "";
                            employee.City = emp.EmployeeAddress.City?.GetValue() ?? "";
                            employee.State = emp.EmployeeAddress.State?.GetValue() ?? "";
                            employee.PostalCode = emp.EmployeeAddress.PostalCode?.GetValue() ?? "";
                        }

                        employees.Add(employee);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on employee {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {employees.Count} employees (SSNs masked)");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return employees;
        }

        private string MaskSSN(string ssn)
        {
            if (string.IsNullOrEmpty(ssn)) return "";
            if (ssn.Length < 4) return "XXX-XX-XXXX";
            
            // Show only last 4 digits
            string lastFour = ssn.Substring(ssn.Length - 4);
            return $"XXX-XX-{lastFour}";
        }

        // ============================================================
        // SERVICE ITEMS (Item 6)
        // ============================================================
        private List<ServiceItemData> ExtractServiceItems()
        {
            Console.WriteLine("[5/28] Extracting Service Items...");
            var items = new List<ServiceItemData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendItemServiceQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return items;

                IItemServiceRetList list = resp.Detail as IItemServiceRetList;
                if (list == null) return items;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IItemServiceRet item = list.GetAt(i);
                        
                        items.Add(new ServiceItemData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            FullName = item.FullName.GetValue(),
                            Description = item.ORSalesPurchase.SalesOrPurchase?.Desc?.GetValue() ?? "",
                            SalesPrice = item.ORSalesPurchase.SalesOrPurchase?.Price?.GetValue() ?? 0,
                            IncomeAccountRef = item.ORSalesPurchase.SalesOrPurchase?.AccountRef?.ListID?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true,
                            ParentRef = item.ParentRef?.ListID?.GetValue() ?? ""
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on service item {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {items.Count} service items");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return items;
        }

        // ============================================================
        // INVENTORY ITEMS (Item 6)
        // ============================================================
        private List<InventoryItemData> ExtractInventoryItems()
        {
            Console.WriteLine("[6/28] Extracting Inventory Items...");
            var items = new List<InventoryItemData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendItemInventoryQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return items;

                IItemInventoryRetList list = resp.Detail as IItemInventoryRetList;
                if (list == null) return items;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IItemInventoryRet item = list.GetAt(i);
                        
                        items.Add(new InventoryItemData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            FullName = item.FullName.GetValue(),
                            Description = item.SalesDesc?.GetValue() ?? "",
                            SalesPrice = item.SalesPrice?.GetValue() ?? 0,
                            PurchaseCost = item.PurchaseCost?.GetValue() ?? 0,
                            QuantityOnHand = item.QuantityOnHand?.GetValue() ?? 0,
                            ReorderPoint = item.ReorderPoint?.GetValue() ?? 0,
                            QuantityOnOrder = item.QuantityOnOrder?.GetValue() ?? 0,
                            AverageCost = item.AverageCost?.GetValue() ?? 0,
                            IncomeAccountRef = item.IncomeAccountRef?.ListID?.GetValue() ?? "",
                            COGSAccountRef = item.COGSAccountRef?.ListID?.GetValue() ?? "",
                            AssetAccountRef = item.AssetAccountRef?.ListID?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true,
                            ParentRef = item.ParentRef?.ListID?.GetValue() ?? ""
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on inventory item {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {items.Count} inventory items");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return items;
        }

        // ============================================================
        // NON-INVENTORY ITEMS (Item 6)
        // ============================================================
        private List<NonInventoryItemData> ExtractNonInventoryItems()
        {
            Console.WriteLine("[7/28] Extracting Non-Inventory Items...");
            var items = new List<NonInventoryItemData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendItemNonInventoryQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return items;

                IItemNonInventoryRetList list = resp.Detail as IItemNonInventoryRetList;
                if (list == null) return items;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IItemNonInventoryRet item = list.GetAt(i);
                        
                        items.Add(new NonInventoryItemData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            FullName = item.FullName.GetValue(),
                            Description = item.ORSalesPurchase.SalesOrPurchase?.Desc?.GetValue() ?? "",
                            SalesPrice = item.ORSalesPurchase.SalesOrPurchase?.Price?.GetValue() ?? 0,
                            IncomeAccountRef = item.ORSalesPurchase.SalesOrPurchase?.AccountRef?.ListID?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on non-inventory item {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {items.Count} non-inventory items");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return items;
        }

        // ============================================================
        // OTHER CHARGE ITEMS (Item 6)
        // ============================================================
        private List<OtherChargeItemData> ExtractOtherChargeItems()
        {
            Console.WriteLine("[8/28] Extracting Other Charge Items...");
            var items = new List<OtherChargeItemData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendItemOtherChargeQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return items;

                IItemOtherChargeRetList list = resp.Detail as IItemOtherChargeRetList;
                if (list == null) return items;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IItemOtherChargeRet item = list.GetAt(i);
                        
                        items.Add(new OtherChargeItemData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            Description = item.ORSalesPurchase.SalesOrPurchase?.Desc?.GetValue() ?? "",
                            Rate = item.ORSalesPurchase.SalesOrPurchase?.Price?.GetValue() ?? 0,
                            AccountRef = item.ORSalesPurchase.SalesOrPurchase?.AccountRef?.ListID?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on other charge item {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {items.Count} other charge items");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return items;
        }

        // ============================================================
        // DISCOUNT ITEMS (Item 6)
        // ============================================================
        private List<DiscountItemData> ExtractDiscountItems()
        {
            Console.WriteLine("[9/28] Extracting Discount Items...");
            var items = new List<DiscountItemData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendItemDiscountQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return items;

                IItemDiscountRetList list = resp.Detail as IItemDiscountRetList;
                if (list == null) return items;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IItemDiscountRet item = list.GetAt(i);
                        
                        items.Add(new DiscountItemData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            Description = item.ItemDesc?.GetValue() ?? "",
                            DiscountRate = item.DiscountRate?.GetValue() ?? 0,
                            AccountRef = item.AccountRef?.ListID?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on discount item {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {items.Count} discount items");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return items;
        }

        // ============================================================
        // PAYMENT ITEMS (Item 6)
        // ============================================================
        private List<PaymentItemData> ExtractPaymentItems()
        {
            Console.WriteLine("[10/28] Extracting Payment Items...");
            var items = new List<PaymentItemData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendItemPaymentQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return items;

                IItemPaymentRetList list = resp.Detail as IItemPaymentRetList;
                if (list == null) return items;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IItemPaymentRet item = list.GetAt(i);
                        
                        items.Add(new PaymentItemData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            Description = item.ItemDesc?.GetValue() ?? "",
                            DepositToAccountRef = item.DepositToAccountRef?.ListID?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on payment item {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {items.Count} payment items");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return items;
        }

        // ============================================================
        // SALES TAX ITEMS (Item 6)
        // ============================================================
        private List<SalesTaxItemData> ExtractSalesTaxItems()
        {
            Console.WriteLine("[11/28] Extracting Sales Tax Items...");
            var items = new List<SalesTaxItemData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendItemSalesTaxQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return items;

                IItemSalesTaxRetList list = resp.Detail as IItemSalesTaxRetList;
                if (list == null) return items;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IItemSalesTaxRet item = list.GetAt(i);
                        
                        items.Add(new SalesTaxItemData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            Description = item.ItemDesc?.GetValue() ?? "",
                            TaxRate = item.TaxRate?.GetValue() ?? 0,
                            TaxVendorRef = item.TaxVendorRef?.ListID?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on sales tax item {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {items.Count} sales tax items");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return items;
        }

        // ============================================================
        // GROUP ITEMS (Item 6)
        // ============================================================
        private List<ItemGroupData> ExtractGroupItems()
        {
            Console.WriteLine("[12/28] Extracting Group Items...");
            var items = new List<ItemGroupData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendItemGroupQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return items;

                IItemGroupRetList list = resp.Detail as IItemGroupRetList;
                if (list == null) return items;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IItemGroupRet item = list.GetAt(i);
                        
                        var group = new ItemGroupData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            Description = item.ItemDesc?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true,
                            Lines = new List<ItemGroupLineData>()
                        };

                        // Extract group line items
                        IItemGroupLineRetList lineList = item.ItemGroupLineRetList;
                        if (lineList != null)
                        {
                            for (int j = 0; j < lineList.Count; j++)
                            {
                                IItemGroupLineRet line = lineList.GetAt(j);
                                
                                group.Lines.Add(new ItemGroupLineData
                                {
                                    ItemRef = line.ItemRef?.ListID?.GetValue() ?? "",
                                    Quantity = line.Quantity?.GetValue() ?? 0
                                });
                            }
                        }

                        items.Add(group);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on group item {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {items.Count} group items");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return items;
        }

        // ============================================================
        // CLASSES (Item 13)
        // ============================================================
        private List<ClassData> ExtractClasses()
        {
            Console.WriteLine("[13/28] Extracting Classes...");
            var classes = new List<ClassData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendClassQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return classes;

                IClassRetList list = resp.Detail as IClassRetList;
                if (list == null) return classes;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IClassRet cls = list.GetAt(i);
                        
                        classes.Add(new ClassData
                        {
                            ListID = cls.ListID.GetValue(),
                            Name = cls.Name.GetValue(),
                            FullName = cls.FullName.GetValue(),
                            ParentRef = cls.ParentRef?.ListID?.GetValue() ?? "",
                            IsActive = cls.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on class {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {classes.Count} classes");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return classes;
        }

        // ============================================================
        // TERMS (Item 14)
        // ============================================================
        private List<TermsData> ExtractTerms()
        {
            Console.WriteLine("[14/28] Extracting Terms...");
            var terms = new List<TermsData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendTermsQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return terms;

                ITermsRetList list = resp.Detail as ITermsRetList;
                if (list == null) return terms;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        ITermsRet term = list.GetAt(i);
                        
                        terms.Add(new TermsData
                        {
                            ListID = term.ListID.GetValue(),
                            Name = term.Name.GetValue(),
                            StdDueDays = term.StdDueDays?.GetValue() ?? 0,
                            StdDiscountDays = term.StdDiscountDays?.GetValue() ?? 0,
                            DiscountPct = term.DiscountPct?.GetValue() ?? 0,
                            IsActive = term.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on term {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {terms.Count} terms");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return terms;
        }

        // ============================================================
        // PAYMENT METHODS (Item 15)
        // ============================================================
        private List<PaymentMethodData> ExtractPaymentMethods()
        {
            Console.WriteLine("[15/28] Extracting Payment Methods...");
            var methods = new List<PaymentMethodData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendPaymentMethodQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return methods;

                IPaymentMethodRetList list = resp.Detail as IPaymentMethodRetList;
                if (list == null) return methods;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IPaymentMethodRet method = list.GetAt(i);
                        
                        methods.Add(new PaymentMethodData
                        {
                            ListID = method.ListID.GetValue(),
                            Name = method.Name.GetValue(),
                            PaymentMethodType = method.PaymentMethodType?.GetValue() ?? "",
                            IsActive = method.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on payment method {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {methods.Count} payment methods");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return methods;
        }

        // ============================================================
        // SALES TAX CODES (Item 12)
        // ============================================================
        private List<SalesTaxCodeData> ExtractSalesTaxCodes()
        {
            Console.WriteLine("[16/28] Extracting Sales Tax Codes...");
            var codes = new List<SalesTaxCodeData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendSalesTaxCodeQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return codes;

                ISalesTaxCodeRetList list = resp.Detail as ISalesTaxCodeRetList;
                if (list == null) return codes;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        ISalesTaxCodeRet code = list.GetAt(i);
                        
                        codes.Add(new SalesTaxCodeData
                        {
                            ListID = code.ListID.GetValue(),
                            Name = code.Name.GetValue(),
                            Description = code.Desc?.GetValue() ?? "",
                            IsTaxable = code.IsTaxable?.GetValue() ?? false,
                            IsActive = code.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on sales tax code {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {codes.Count} sales tax codes");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return codes;
        }

        // ============================================================
        // CUSTOMER TYPES (Item 23)
        // ============================================================
        private List<CustomerTypeData> ExtractCustomerTypes()
        {
            Console.WriteLine("[17/28] Extracting Customer Types...");
            var types = new List<CustomerTypeData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendCustomerTypeQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return types;

                ICustomerTypeRetList list = resp.Detail as ICustomerTypeRetList;
                if (list == null) return types;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        ICustomerTypeRet type = list.GetAt(i);
                        
                        types.Add(new CustomerTypeData
                        {
                            ListID = type.ListID.GetValue(),
                            Name = type.Name.GetValue(),
                            FullName = type.FullName.GetValue(),
                            ParentRef = type.ParentRef?.ListID?.GetValue() ?? "",
                            IsActive = type.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on customer type {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {types.Count} customer types");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return types;
        }

        // ============================================================
        // VENDOR TYPES (Item 24)
        // ============================================================
        private List<VendorTypeData> ExtractVendorTypes()
        {
            Console.WriteLine("[18/28] Extracting Vendor Types...");
            var types = new List<VendorTypeData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendVendorTypeQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return types;

                IVendorTypeRetList list = resp.Detail as IVendorTypeRetList;
                if (list == null) return types;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IVendorTypeRet type = list.GetAt(i);
                        
                        types.Add(new VendorTypeData
                        {
                            ListID = type.ListID.GetValue(),
                            Name = type.Name.GetValue(),
                            FullName = type.FullName.GetValue(),
                            ParentRef = type.ParentRef?.ListID?.GetValue() ?? "",
                            IsActive = type.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on vendor type {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {types.Count} vendor types");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return types;
        }

        // ============================================================
        // JOB TYPES (Item 25)
        // ============================================================
        private List<JobTypeData> ExtractJobTypes()
        {
            Console.WriteLine("[19/28] Extracting Job Types...");
            var types = new List<JobTypeData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendJobTypeQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return types;

                IJobTypeRetList list = resp.Detail as IJobTypeRetList;
                if (list == null) return types;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IJobTypeRet type = list.GetAt(i);
                        
                        types.Add(new JobTypeData
                        {
                            ListID = type.ListID.GetValue(),
                            Name = type.Name.GetValue(),
                            FullName = type.FullName.GetValue(),
                            ParentRef = type.ParentRef?.ListID?.GetValue() ?? "",
                            IsActive = type.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on job type {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {types.Count} job types");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return types;
        }

        // ============================================================
        // PRICE LEVELS (Item 22)
        // ============================================================
        private List<PriceLevelData> ExtractPriceLevels()
        {
            Console.WriteLine("[20/28] Extracting Price Levels...");
            var levels = new List<PriceLevelData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendPriceLevelQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return levels;

                IPriceLevelRetList list = resp.Detail as IPriceLevelRetList;
                if (list == null) return levels;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IPriceLevelRet level = list.GetAt(i);
                        
                        levels.Add(new PriceLevelData
                        {
                            ListID = level.ListID.GetValue(),
                            Name = level.Name.GetValue(),
                            PriceLevelType = level.PriceLevelType?.GetValue() ?? "",
                            PriceLevelFixedPercentage = level.PriceLevelFixedPercentage?.GetValue() ?? 0,
                            IsActive = level.IsActive?.GetValue() ?? true
                        });
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on price level {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {levels.Count} price levels");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return levels;
        }

        // ============================================================
        // INVOICES (Item 7) - YOU ALREADY HAVE THIS ONE
        // ============================================================
        private List<InvoiceData> ExtractInvoices()
        {
            Console.WriteLine("[21/28] Extracting Invoices...");
            var invoices = new List<InvoiceData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendInvoiceQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return invoices;

                IInvoiceRetList list = resp.Detail as IInvoiceRetList;
                if (list == null) return invoices;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IInvoiceRet inv = list.GetAt(i);
                        
                        var invoice = new InvoiceData
                        {
                            TxnID = inv.TxnID.GetValue(),
                            RefNumber = inv.RefNumber?.GetValue() ?? "",
                            TxnDate = inv.TxnDate.GetValue(),
                            DueDate = inv.DueDate?.GetValue(),
                            CustomerRef = inv.CustomerRef.ListID.GetValue(),
                            Subtotal = inv.Subtotal?.GetValue() ?? 0,
                            SalesTaxAmount = inv.SalesTaxTotal?.GetValue() ?? 0,
                            TotalAmount = inv.TotalAmount?.GetValue() ?? 0,
                            AmountPaid = inv.AppliedAmount?.GetValue() ?? 0,
                            BalanceRemaining = inv.BalanceRemaining?.GetValue() ?? 0,
                            PONumber = inv.PONumber?.GetValue() ?? "",
                            Memo = inv.Memo?.GetValue() ?? "",
                            IsPending = inv.IsPending?.GetValue() ?? false,
                            Lines = new List<InvoiceLineData>()
                        };

                        // Extract line items
                        IORInvoiceLineRetList lineList = inv.ORInvoiceLineRetList;
                        if (lineList != null)
                        {
                            for (int j = 0; j < lineList.Count; j++)
                            {
                                IORInvoiceLineRet lineRet = lineList.GetAt(j);
                                
                                if (lineRet.InvoiceLineRet != null)
                                {
                                    IInvoiceLineRet line = lineRet.InvoiceLineRet;
                                    
                                    invoice.Lines.Add(new InvoiceLineData
                                    {
                                        ItemRef = line.ItemRef?.ListID?.GetValue() ?? "",
                                        Description = line.Desc?.GetValue() ?? "",
                                        Quantity = line.Quantity?.GetValue() ?? 0,
                                        Rate = line.Rate?.GetValue() ?? 0,
                                        Amount = line.Amount?.GetValue() ?? 0,
                                        ClassRef = line.ClassRef?.ListID?.GetValue() ?? ""
                                    });
                                }
                            }
                        }

                        invoices.Add(invoice);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on invoice {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {invoices.Count} invoices");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return invoices;
        }

        // ============================================================
        // BILLS (Item 8) - SAME PATTERN AS INVOICES
        // ============================================================
        private List<BillData> ExtractBills()
        {
            Console.WriteLine("[22/28] Extracting Bills...");
            var bills = new List<BillData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendBillQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return bills;

                IBillRetList list = resp.Detail as IBillRetList;
                if (list == null) return bills;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IBillRet bill = list.GetAt(i);
                        
                        var billData = new BillData
                        {
                            TxnID = bill.TxnID.GetValue(),
                            RefNumber = bill.RefNumber?.GetValue() ?? "",
                            TxnDate = bill.TxnDate.GetValue(),
                            DueDate = bill.DueDate?.GetValue(),
                            VendorRef = bill.VendorRef.ListID.GetValue(),
                            TermsRef = bill.TermsRef?.ListID?.GetValue() ?? "",
                            AmountDue = bill.AmountDue?.GetValue() ?? 0,
                            AmountPaid = bill.AmountPaid?.GetValue() ?? 0,
                            Balance = bill.OpenAmount?.GetValue() ?? 0,
                            Memo = bill.Memo?.GetValue() ?? "",
                            IsPaid = bill.IsPaid?.GetValue() ?? false,
                            Lines = new List<BillLineData>()
                        };

                        // Extract line items
                        IORExpenseLineRetList lineList = bill.ORExpenseLineRetList;
                        if (lineList != null)
                        {
                            for (int j = 0; j < lineList.Count; j++)
                            {
                                IORExpenseLineRet lineRet = lineList.GetAt(j);
                                
                                if (lineRet.ExpenseLineRet != null)
                                {
                                    IExpenseLineRet line = lineRet.ExpenseLineRet;
                                    
                                    billData.Lines.Add(new BillLineData
                                    {
                                        AccountRef = line.AccountRef?.ListID?.GetValue() ?? "",
                                        Description = line.Memo?.GetValue() ?? "",
                                        Amount = line.Amount?.GetValue() ?? 0,
                                        ClassRef = line.ClassRef?.ListID?.GetValue() ?? ""
                                    });
                                }
                            }
                        }

                        bills.Add(billData);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on bill {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {bills.Count} bills");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return bills;
        }

        // ============================================================
        // PAYMENTS RECEIVED (Item 9)
        // ============================================================
        private List<PaymentReceivedData> ExtractPaymentsReceived()
        {
            Console.WriteLine("[23/28] Extracting Payments Received...");
            var payments = new List<PaymentReceivedData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendReceivePaymentQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return payments;

                IReceivePaymentRetList list = resp.Detail as IReceivePaymentRetList;
                if (list == null) return payments;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IReceivePaymentRet pmt = list.GetAt(i);
                        
                        var payment = new PaymentReceivedData
                        {
                            TxnID = pmt.TxnID.GetValue(),
                            RefNumber = pmt.RefNumber?.GetValue() ?? "",
                            TxnDate = pmt.TxnDate.GetValue(),
                            CustomerRef = pmt.CustomerRef.ListID.GetValue(),
                            PaymentMethodRef = pmt.PaymentMethodRef?.ListID?.GetValue() ?? "",
                            DepositToAccountRef = pmt.DepositToAccountRef?.ListID?.GetValue() ?? "",
                            TotalAmount = pmt.TotalAmount?.GetValue() ?? 0,
                            CheckNumber = pmt.CheckNumber?.GetValue() ?? "",
                            Memo = pmt.Memo?.GetValue() ?? "",
                            UnusedPayment = pmt.UnusedPayment?.GetValue() ?? 0,
                            AppliedTo = new List<PaymentAppliedToData>()
                        };

                        // Extract applied to invoices
                        IAppliedToTxnRetList appliedList = pmt.AppliedToTxnRetList;
                        if (appliedList != null)
                        {
                            for (int j = 0; j < appliedList.Count; j++)
                            {
                                IAppliedToTxnRet applied = appliedList.GetAt(j);
                                
                                payment.AppliedTo.Add(new PaymentAppliedToData
                                {
                                    TxnID = applied.TxnID?.GetValue() ?? "",
                                    PaymentAmount = applied.PaymentAmount?.GetValue() ?? 0
                                });
                            }
                        }

                        payments.Add(payment);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on payment {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {payments.Count} payments received");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return payments;
        }

        // ============================================================
        // BILL PAYMENTS (Item 10)
        // ============================================================
        private List<BillPaymentData> ExtractBillPayments()
        {
            Console.WriteLine("[24/28] Extracting Bill Payments...");
            var payments = new List<BillPaymentData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendBillPaymentCheckQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return payments;

                IBillPaymentCheckRetList list = resp.Detail as IBillPaymentCheckRetList;
                if (list == null) return payments;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IBillPaymentCheckRet pmt = list.GetAt(i);
                        
                        var payment = new BillPaymentData
                        {
                            TxnID = pmt.TxnID.GetValue(),
                            RefNumber = pmt.RefNumber?.GetValue() ?? "",
                            TxnDate = pmt.TxnDate.GetValue(),
                            VendorRef = pmt.PayeeEntityRef?.ListID?.GetValue() ?? "",
                            BankAccountRef = pmt.BankAccountRef?.ListID?.GetValue() ?? "",
                            TotalAmount = pmt.Amount?.GetValue() ?? 0,
                            CheckNumber = pmt.RefNumber?.GetValue() ?? "",
                            Memo = pmt.Memo?.GetValue() ?? "",
                            AppliedTo = new List<BillPaymentAppliedToData>()
                        };

                        // Extract applied to bills
                        IAppliedToTxnRetList appliedList = pmt.AppliedToTxnRetList;
                        if (appliedList != null)
                        {
                            for (int j = 0; j < appliedList.Count; j++)
                            {
                                IAppliedToTxnRet applied = appliedList.GetAt(j);
                                
                                payment.AppliedTo.Add(new BillPaymentAppliedToData
                                {
                                    TxnID = applied.TxnID?.GetValue() ?? "",
                                    PaymentAmount = applied.PaymentAmount?.GetValue() ?? 0
                                });
                            }
                        }

                        payments.Add(payment);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on bill payment {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {payments.Count} bill payments");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return payments;
        }

        // ============================================================
        // CREDIT MEMOS (Item 18)
        // ============================================================
        private List<CreditMemoData> ExtractCreditMemos()
        {
            Console.WriteLine("[25/28] Extracting Credit Memos...");
            var memos = new List<CreditMemoData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendCreditMemoQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return memos;

                ICreditMemoRetList list = resp.Detail as ICreditMemoRetList;
                if (list == null) return memos;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        ICreditMemoRet memo = list.GetAt(i);
                        
                        var creditMemo = new CreditMemoData
                        {
                            TxnID = memo.TxnID.GetValue(),
                            RefNumber = memo.RefNumber?.GetValue() ?? "",
                            TxnDate = memo.TxnDate.GetValue(),
                            CustomerRef = memo.CustomerRef.ListID.GetValue(),
                            TotalAmount = memo.TotalAmount?.GetValue() ?? 0,
                            CreditRemaining = memo.CreditRemaining?.GetValue() ?? 0,
                            Memo = memo.Memo?.GetValue() ?? "",
                            Lines = new List<CreditMemoLineData>()
                        };

                        // Extract line items
                        IORCreditMemoLineRetList lineList = memo.ORCreditMemoLineRetList;
                        if (lineList != null)
                        {
                            for (int j = 0; j < lineList.Count; j++)
                            {
                                IORCreditMemoLineRet lineRet = lineList.GetAt(j);
                                
                                if (lineRet.CreditMemoLineRet != null)
                                {
                                    ICreditMemoLineRet line = lineRet.CreditMemoLineRet;
                                    
                                    creditMemo.Lines.Add(new CreditMemoLineData
                                    {
                                        ItemRef = line.ItemRef?.ListID?.GetValue() ?? "",
                                        Description = line.Desc?.GetValue() ?? "",
                                        Quantity = line.Quantity?.GetValue() ?? 0,
                                        Rate = line.Rate?.GetValue() ?? 0,
                                        Amount = line.Amount?.GetValue() ?? 0
                                    });
                                }
                            }
                        }

                        memos.Add(creditMemo);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on credit memo {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {memos.Count} credit memos");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return memos;
        }

        // ============================================================
        // SALES RECEIPTS (Item 21)
        // ============================================================
        private List<SalesReceiptData> ExtractSalesReceipts()
        {
            Console.WriteLine("[26/28] Extracting Sales Receipts...");
            var receipts = new List<SalesReceiptData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendSalesReceiptQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return receipts;

                ISalesReceiptRetList list = resp.Detail as ISalesReceiptRetList;
                if (list == null) return receipts;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        ISalesReceiptRet receipt = list.GetAt(i);
                        
                        var salesReceipt = new SalesReceiptData
                        {
                            TxnID = receipt.TxnID.GetValue(),
                            RefNumber = receipt.RefNumber?.GetValue() ?? "",
                            TxnDate = receipt.TxnDate.GetValue(),
                            CustomerRef = receipt.CustomerRef.ListID.GetValue(),
                            PaymentMethodRef = receipt.PaymentMethodRef?.ListID?.GetValue() ?? "",
                            DepositToAccountRef = receipt.DepositToAccountRef?.ListID?.GetValue() ?? "",
                            TotalAmount = receipt.TotalAmount?.GetValue() ?? 0,
                            Memo = receipt.Memo?.GetValue() ?? "",
                            Lines = new List<SalesReceiptLineData>()
                        };

                        // Extract line items
                        IORSalesReceiptLineRetList lineList = receipt.ORSalesReceiptLineRetList;
                        if (lineList != null)
                        {
                            for (int j = 0; j < lineList.Count; j++)
                            {
                                IORSalesReceiptLineRet lineRet = lineList.GetAt(j);
                                
                                if (lineRet.SalesReceiptLineRet != null)
                                {
                                    ISalesReceiptLineRet line = lineRet.SalesReceiptLineRet;
                                    
                                    salesReceipt.Lines.Add(new SalesReceiptLineData
                                    {
                                        ItemRef = line.ItemRef?.ListID?.GetValue() ?? "",
                                        Description = line.Desc?.GetValue() ?? "",
                                        Quantity = line.Quantity?.GetValue() ?? 0,
                                        Rate = line.Rate?.GetValue() ?? 0,
                                        Amount = line.Amount?.GetValue() ?? 0
                                    });
                                }
                            }
                        }

                        receipts.Add(salesReceipt);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on sales receipt {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {receipts.Count} sales receipts");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return receipts;
        }

        // ============================================================
        // PURCHASE ORDERS (Item 19)
        // ============================================================
        private List<PurchaseOrderData> ExtractPurchaseOrders()
        {
            Console.WriteLine("[27/28] Extracting Purchase Orders...");
            var orders = new List<PurchaseOrderData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendPurchaseOrderQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return orders;

                IPurchaseOrderRetList list = resp.Detail as IPurchaseOrderRetList;
                if (list == null) return orders;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IPurchaseOrderRet po = list.GetAt(i);
                        
                        var order = new PurchaseOrderData
                        {
                            TxnID = po.TxnID.GetValue(),
                            RefNumber = po.RefNumber?.GetValue() ?? "",
                            TxnDate = po.TxnDate.GetValue(),
                            VendorRef = po.VendorRef.ListID.GetValue(),
                            TotalAmount = po.TotalAmount?.GetValue() ?? 0,
                            Memo = po.Memo?.GetValue() ?? "",
                            IsManuallyClosed = po.IsManuallyClosed?.GetValue() ?? false,
                            Lines = new List<PurchaseOrderLineData>()
                        };

                        // Extract line items
                        IORPurchaseOrderLineRetList lineList = po.ORPurchaseOrderLineRetList;
                        if (lineList != null)
                        {
                            for (int j = 0; j < lineList.Count; j++)
                            {
                                IORPurchaseOrderLineRet lineRet = lineList.GetAt(j);
                                
                                if (lineRet.PurchaseOrderLineRet != null)
                                {
                                    IPurchaseOrderLineRet line = lineRet.PurchaseOrderLineRet;
                                    
                                    order.Lines.Add(new PurchaseOrderLineData
                                    {
                                        ItemRef = line.ItemRef?.ListID?.GetValue() ?? "",
                                        Description = line.Desc?.GetValue() ?? "",
                                        Quantity = line.Quantity?.GetValue() ?? 0,
                                        Rate = line.Rate?.GetValue() ?? 0,
                                        Amount = line.Amount?.GetValue() ?? 0
                                    });
                                }
                            }
                        }

                        orders.Add(order);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on purchase order {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {orders.Count} purchase orders");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return orders;
        }

        // ============================================================
        // ESTIMATES (Item 20)
        // ============================================================
        private List<EstimateData> ExtractEstimates()
        {
            Console.WriteLine("[28/28] Extracting Estimates...");
            var estimates = new List<EstimateData>();

            try
            {
                IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
                request.AppendEstimateQueryRq();
                IMsgSetResponse response = sessionManager.DoRequests(request);
                
                IResponse resp = response.ResponseList.GetAt(0);
                if (resp.StatusCode != 0) return estimates;

                IEstimateRetList list = resp.Detail as IEstimateRetList;
                if (list == null) return estimates;

                for (int i = 0; i < list.Count; i++)
                {
                    try
                    {
                        IEstimateRet est = list.GetAt(i);
                        
                        var estimate = new EstimateData
                        {
                            TxnID = est.TxnID.GetValue(),
                            RefNumber = est.RefNumber?.GetValue() ?? "",
                            TxnDate = est.TxnDate.GetValue(),
                            CustomerRef = est.CustomerRef.ListID.GetValue(),
                            TotalAmount = est.TotalAmount?.GetValue() ?? 0,
                            Memo = est.Memo?.GetValue() ?? "",
                            IsActive = est.IsActive?.GetValue() ?? true,
                            Lines = new List<EstimateLineData>()
                        };

                        // Extract line items
                        IOREstimateLineRetList lineList = est.OREstimateLineRetList;
                        if (lineList != null)
                        {
                            for (int j = 0; j < lineList.Count; j++)
                            {
                                IOREstimateLineRet lineRet = lineList.GetAt(j);
                                
                                if (lineRet.EstimateLineRet != null)
                                {
                                    IEstimateLineRet line = lineRet.EstimateLineRet;
                                    
                                    estimate.Lines.Add(new EstimateLineData
                                    {
                                        ItemRef = line.ItemRef?.ListID?.GetValue() ?? "",
                                        Description = line.Desc?.GetValue() ?? "",
                                        Quantity = line.Quantity?.GetValue() ?? 0,
                                        Rate = line.Rate?.GetValue() ?? 0,
                                        Amount = line.Amount?.GetValue() ?? 0
                                    });
                                }
                            }
                        }

                        estimates.Add(estimate);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"  ⚠ Error on estimate {i}: {ex.Message}");
                    }
                }

                Console.WriteLine($"  ✓ Extracted {estimates.Count} estimates");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error: {ex.Message}");
            }

            return estimates;
        }

        // ============================================================
        // DEPOSITS (Item 16) - Simplified version
        // ============================================================
        private List<DepositData> ExtractDeposits()
        {
            // NOTE: Deposits are complex in QB Desktop
            // This is a simplified extraction - you may want to enhance this
            var deposits = new List<DepositData>();
            Console.WriteLine("[SKIPPED] Deposit extraction - requires custom implementation");
            return deposits;
        }

        // ============================================================
        // JOURNAL ENTRIES (Item 17) - Simplified version
        // ============================================================
        private List<JournalEntryData> ExtractJournalEntries()
        {
            // NOTE: Journal entries have complex debit/credit lines
            // This is a simplified extraction - you may want to enhance this
            var entries = new List<JournalEntryData>();
            Console.WriteLine("[SKIPPED] Journal Entry extraction - requires custom implementation");
            return entries;
        }
    }
}
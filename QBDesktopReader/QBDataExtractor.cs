using System;
using System.Collections.Generic;
using QBFC16Lib;

namespace QBDesktopReader
{
    public class QBDataExtractor
    {
        private QBSessionManager sessionManager;

        public QBDataExtractor()
        {
            sessionManager = new QBSessionManager();
        }

        public void Connect()
        {
            sessionManager.OpenConnection("", "QB Migration Tool");
            sessionManager.BeginSession("", ENOpenMode.omDontCare);
        }

        public void Disconnect()
        {
            sessionManager.EndSession();
            sessionManager.CloseConnection();
        }

        public ExtractedData ExtractAllData()
        {
            Console.WriteLine("Starting data extraction...");

            var data = new ExtractedData
            {
                Customers = ExtractCustomers(),
                Vendors = ExtractVendors(),
                Accounts = ExtractAccounts(),
                Items = ExtractItems(),
                Invoices = ExtractInvoices(),
                ExtractedAt = DateTime.Now,
                CompanyName = GetCompanyName()
            };

            Console.WriteLine($"\nExtraction complete:");
            Console.WriteLine($"  Customers: {data.Customers.Count}");
            Console.WriteLine($"  Vendors: {data.Vendors.Count}");
            Console.WriteLine($"  Accounts: {data.Accounts.Count}");
            Console.WriteLine($"  Items: {data.Items.Count}");
            Console.WriteLine($"  Invoices: {data.Invoices.Count}");

            return data;
        }

        private string GetCompanyName()
        {
            IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
            request.AppendCompanyQueryRq();
            IMsgSetResponse response = sessionManager.DoRequests(request);
            ICompanyRet company = response.ResponseList.GetAt(0).Detail as ICompanyRet;
            return company.CompanyName.GetValue();
        }

        private List<CustomerData> ExtractCustomers()
        {
            Console.WriteLine("\nExtracting customers...");
            var customers = new List<CustomerData>();

            IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
            request.AppendCustomerQueryRq();
            IMsgSetResponse response = sessionManager.DoRequests(request);
            
            IResponse resp = response.ResponseList.GetAt(0);
            if (resp.StatusCode != 0) return customers;

            ICustomerRetList list = resp.Detail as ICustomerRetList;
            if (list == null) return customers;

            for (int i = 0; i < list.Count; i++)
            {
                ICustomerRet cust = list.GetAt(i);
                
                var customer = new CustomerData
                {
                    ListID = cust.ListID.GetValue(),
                    Name = cust.Name.GetValue(),
                    FullName = cust.FullName.GetValue(),
                    CompanyName = cust.CompanyName?.GetValue() ?? "",
                    Phone = cust.Phone?.GetValue() ?? "",
                    Email = cust.Email?.GetValue() ?? "",
                    Balance = cust.Balance?.GetValue() ?? 0
                };

                if (cust.BillAddress != null)
                {
                    customer.Addr1 = cust.BillAddress.Addr1?.GetValue() ?? "";
                    customer.Addr2 = cust.BillAddress.Addr2?.GetValue() ?? "";
                    customer.City = cust.BillAddress.City?.GetValue() ?? "";
                    customer.State = cust.BillAddress.State?.GetValue() ?? "";
                    customer.PostalCode = cust.BillAddress.PostalCode?.GetValue() ?? "";
                    customer.Country = cust.BillAddress.Country?.GetValue() ?? "";
                }

                customers.Add(customer);
            }

            return customers;
        }

        private List<VendorData> ExtractVendors()
        {
            Console.WriteLine("Extracting vendors...");
            var vendors = new List<VendorData>();

            IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
            request.AppendVendorQueryRq();
            IMsgSetResponse response = sessionManager.DoRequests(request);
            
            IResponse resp = response.ResponseList.GetAt(0);
            if (resp.StatusCode != 0) return vendors;

            IVendorRetList list = resp.Detail as IVendorRetList;
            if (list == null) return vendors;

            for (int i = 0; i < list.Count; i++)
            {
                IVendorRet vend = list.GetAt(i);
                
                var vendor = new VendorData
                {
                    ListID = vend.ListID.GetValue(),
                    Name = vend.Name.GetValue(),
                    CompanyName = vend.CompanyName?.GetValue() ?? "",
                    Phone = vend.Phone?.GetValue() ?? "",
                    Email = vend.Email?.GetValue() ?? "",
                    Balance = vend.Balance?.GetValue() ?? 0
                };

                if (vend.VendorAddress != null)
                {
                    vendor.Addr1 = vend.VendorAddress.Addr1?.GetValue() ?? "";
                    vendor.City = vend.VendorAddress.City?.GetValue() ?? "";
                    vendor.State = vend.VendorAddress.State?.GetValue() ?? "";
                    vendor.PostalCode = vend.VendorAddress.PostalCode?.GetValue() ?? "";
                }

                vendors.Add(vendor);
            }

            return vendors;
        }

        private List<AccountData> ExtractAccounts()
        {
            Console.WriteLine("Extracting chart of accounts...");
            var accounts = new List<AccountData>();

            IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
            request.AppendAccountQueryRq();
            IMsgSetResponse response = sessionManager.DoRequests(request);
            
            IResponse resp = response.ResponseList.GetAt(0);
            if (resp.StatusCode != 0) return accounts;

            IAccountRetList list = resp.Detail as IAccountRetList;
            if (list == null) return accounts;

            for (int i = 0; i < list.Count; i++)
            {
                IAccountRet acct = list.GetAt(i);
                
                var account = new AccountData
                {
                    ListID = acct.ListID.GetValue(),
                    Name = acct.Name.GetValue(),
                    FullName = acct.FullName.GetValue(),
                    AccountType = acct.AccountType.GetValue().ToString(),
                    AccountNumber = acct.AccountNumber?.GetValue() ?? "",
                    Balance = acct.Balance?.GetValue() ?? 0,
                    Description = acct.Desc?.GetValue() ?? "",
                    IsActive = acct.IsActive?.GetValue() ?? true
                };

                accounts.Add(account);
            }

            return accounts;
        }

        private List<ItemData> ExtractItems()
        {
            Console.WriteLine("Extracting items...");
            var items = new List<ItemData>();

            // Service Items
            IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
            request.AppendItemServiceQueryRq();
            IMsgSetResponse response = sessionManager.DoRequests(request);
            
            IResponse resp = response.ResponseList.GetAt(0);
            if (resp.StatusCode == 0)
            {
                IItemServiceRetList list = resp.Detail as IItemServiceRetList;
                if (list != null)
                {
                    for (int i = 0; i < list.Count; i++)
                    {
                        IItemServiceRet item = list.GetAt(i);
                        
                        var itemData = new ItemData
                        {
                            ListID = item.ListID.GetValue(),
                            Name = item.Name.GetValue(),
                            FullName = item.FullName.GetValue(),
                            Type = "Service",
                            SalesPrice = item.ORSalesPurchase.SalesOrPurchase?.Price?.GetValue() ?? 0,
                            IncomeAccountRef = item.ORSalesPurchase.SalesOrPurchase?.AccountRef?.ListID?.GetValue() ?? "",
                            Description = item.ORSalesPurchase.SalesOrPurchase?.Desc?.GetValue() ?? "",
                            IsActive = item.IsActive?.GetValue() ?? true
                        };

                        items.Add(itemData);
                    }
                }
            }

            return items;
        }

        private List<InvoiceData> ExtractInvoices()
        {
            Console.WriteLine("Extracting invoices...");
            var invoices = new List<InvoiceData>();

            IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
            request.AppendInvoiceQueryRq();
            IMsgSetResponse response = sessionManager.DoRequests(request);
            
            IResponse resp = response.ResponseList.GetAt(0);
            if (resp.StatusCode != 0) return invoices;

            IInvoiceRetList list = resp.Detail as IInvoiceRetList;
            if (list == null) return invoices;

            for (int i = 0; i < list.Count; i++)
            {
                IInvoiceRet inv = list.GetAt(i);
                
                var invoice = new InvoiceData
                {
                    TxnID = inv.TxnID.GetValue(),
                    RefNumber = inv.RefNumber?.GetValue() ?? "",
                    TxnDate = inv.TxnDate.GetValue(),
                    CustomerRef = inv.CustomerRef.ListID.GetValue(),
                    Subtotal = inv.Subtotal?.GetValue() ?? 0,
                    TotalAmount = inv.BalanceRemaining?.GetValue() ?? 0,
                    BalanceRemaining = inv.BalanceRemaining?.GetValue() ?? 0,
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
                            
                            var lineData = new InvoiceLineData
                            {
                                ItemRef = line.ItemRef?.ListID?.GetValue() ?? "",
                                Description = line.Desc?.GetValue() ?? "",
                                Quantity = line.Quantity?.GetValue() ?? 0,
                                Rate = line.Rate?.GetValue() ?? 0,
                                Amount = line.Amount?.GetValue() ?? 0
                            };

                            invoice.Lines.Add(lineData);
                        }
                    }
                }

                invoices.Add(invoice);
            }

            return invoices;
        }
    }
}
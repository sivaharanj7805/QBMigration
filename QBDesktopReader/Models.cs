using System;
using System.Collections.Generic;

namespace QBDesktopReader
{
    public class CustomerData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string FirstName { get; set; }
        public string LastName { get; set; }
        public string CompanyName { get; set; }
        public string Phone { get; set; }
        public string Email { get; set; }
        public string Addr1 { get; set; }
        public string Addr2 { get; set; }
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public string Country { get; set; }
        public decimal Balance { get; set; }
    }

    public class VendorData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string CompanyName { get; set; }
        public string Phone { get; set; }
        public string Email { get; set; }
        public string Addr1 { get; set; }
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public decimal Balance { get; set; }
    }

    public class AccountData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string AccountType { get; set; }
        public string AccountNumber { get; set; }
        public decimal Balance { get; set; }
        public string Description { get; set; }
        public bool IsActive { get; set; }
    }

    public class ItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string Type { get; set; }
        public decimal SalesPrice { get; set; }
        public string IncomeAccountRef { get; set; }
        public string Description { get; set; }
        public bool IsActive { get; set; }
    }

    public class InvoiceData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRef { get; set; }
        public decimal Subtotal { get; set; }
        public decimal TotalAmount { get; set; }
        public decimal BalanceRemaining { get; set; }
        public List<InvoiceLineData> Lines { get; set; }
    }

    public class InvoiceLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
    }

    public class ExtractedData
    {
        public List<CustomerData> Customers { get; set; }
        public List<VendorData> Vendors { get; set; }
        public List<AccountData> Accounts { get; set; }
        public List<ItemData> Items { get; set; }
        public List<InvoiceData> Invoices { get; set; }
        public DateTime ExtractedAt { get; set; }
        public string CompanyName { get; set; }
    }
}
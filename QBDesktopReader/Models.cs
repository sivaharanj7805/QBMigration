using System;
using System.Collections.Generic;

namespace QBDesktopReader
{
    // ============================================================
    // COMPLETE DATA MODELS FOR ALL QB DATA TYPES
    // Covers checklist items 3-30
    // CORRECTED VERSION with decimal types and all references
    // ============================================================

    /// <summary>
    /// Main container for all extracted data
    /// </summary>
    public class ExtractedData
    {
        // Metadata
        public DateTime ExtractedAt { get; set; }
        public string CompanyName { get; set; }
        public string QBVersion { get; set; }
        
        // Lists/Master Data
        public List<AccountData> Accounts { get; set; }
        public List<CustomerData> Customers { get; set; }
        public List<VendorData> Vendors { get; set; }
        public List<EmployeeData> Employees { get; set; }
        
        // Items (all types)
        public List<ServiceItemData> ServiceItems { get; set; }
        public List<InventoryItemData> InventoryItems { get; set; }
        public List<NonInventoryItemData> NonInventoryItems { get; set; }
        public List<OtherChargeItemData> OtherChargeItems { get; set; }
        public List<DiscountItemData> DiscountItems { get; set; }
        public List<PaymentItemData> PaymentItems { get; set; }
        public List<SalesTaxItemData> SalesTaxItems { get; set; }
        public List<ItemGroupData> GroupItems { get; set; }
        
        // Configuration
        public List<ClassData> Classes { get; set; }
        public List<TermsData> Terms { get; set; }
        public List<PaymentMethodData> PaymentMethods { get; set; }
        public List<SalesTaxCodeData> SalesTaxCodes { get; set; }
        public List<CustomerTypeData> CustomerTypes { get; set; }
        public List<VendorTypeData> VendorTypes { get; set; }
        public List<JobTypeData> JobTypes { get; set; }
        public List<PriceLevelData> PriceLevels { get; set; }
        
        // Transactions
        public List<InvoiceData> Invoices { get; set; }
        public List<BillData> Bills { get; set; }
        public List<PaymentReceivedData> PaymentsReceived { get; set; }
        public List<BillPaymentData> BillPayments { get; set; }
        public List<CreditMemoData> CreditMemos { get; set; }
        public List<SalesReceiptData> SalesReceipts { get; set; }
        public List<PurchaseOrderData> PurchaseOrders { get; set; }
        public List<EstimateData> Estimates { get; set; }
        public List<DepositData> Deposits { get; set; }
        public List<JournalEntryData> JournalEntries { get; set; }
    }

    // ============================================================
    // CHART OF ACCOUNTS (Item 3)
    // ============================================================
    public class AccountData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string AccountType { get; set; }
        public string AccountNumber { get; set; }
        public decimal Balance { get; set; }  // DECIMAL for money
        public string Description { get; set; }
        public bool IsActive { get; set; }
        public string ParentRef { get; set; }
        public string TaxLineInfo { get; set; }
        public string SpecialAccountType { get; set; }
    }

    // ============================================================
    // CUSTOMERS (Item 4)
    // ============================================================
    public class CustomerData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
        public string CompanyName { get; set; }
        
        // Contact Info
        public string Phone { get; set; }
        public string AltPhone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        public string Website { get; set; }
        
        // Bill Address - FIXED: Added Addr3 and Note
        public string BillAddr1 { get; set; }
        public string BillAddr2 { get; set; }
        public string BillAddr3 { get; set; }  // ADDED
        public string BillAddr4 { get; set; }  // ADDED (some QB versions have 4 lines)
        public string BillAddr5 { get; set; }  // ADDED (some QB versions have 5 lines)
        public string BillCity { get; set; }
        public string BillState { get; set; }
        public string BillPostalCode { get; set; }
        public string BillCountry { get; set; }
        public string BillNote { get; set; }   // ADDED
        
        // Ship Address - FIXED: Added Addr3 and Note
        public string ShipAddr1 { get; set; }
        public string ShipAddr2 { get; set; }
        public string ShipAddr3 { get; set; }  // ADDED
        public string ShipAddr4 { get; set; }  // ADDED
        public string ShipAddr5 { get; set; }  // ADDED
        public string ShipCity { get; set; }
        public string ShipState { get; set; }
        public string ShipPostalCode { get; set; }
        public string ShipCountry { get; set; }
        public string ShipNote { get; set; }   // ADDED
        
        // Financial - DECIMAL for money
        public decimal Balance { get; set; }
        public decimal TotalBalance { get; set; }
        public decimal CreditLimit { get; set; }
        
        // References - FIXED: Actually populated now
        public string CustomerTypeRef { get; set; }
        public string TermsRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        public string PriceLevelRef { get; set; }
        
        // Other
        public string Notes { get; set; }
        public bool IsActive { get; set; }
        public string ParentRef { get; set; } // For sub-customers
        public string JobStatus { get; set; }
        public DateTime? JobStartDate { get; set; }
        public DateTime? JobEndDate { get; set; }
    }

    // ============================================================
    // VENDORS (Item 5)
    // ============================================================
    public class VendorData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string CompanyName { get; set; }
        
        // Contact Info
        public string FirstName { get; set; }
        public string LastName { get; set; }
        public string Phone { get; set; }
        public string AltPhone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        
        // Address - FIXED: Added Addr3
        public string Addr1 { get; set; }
        public string Addr2 { get; set; }
        public string Addr3 { get; set; }  // ADDED
        public string Addr4 { get; set; }  // ADDED
        public string Addr5 { get; set; }  // ADDED
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public string Country { get; set; }
        public string Note { get; set; }    // ADDED
        
        // Financial - DECIMAL for money
        public decimal Balance { get; set; }
        public decimal CreditLimit { get; set; }
        
        // Tax
        public string TaxID { get; set; } // 1099 info
        public bool Is1099Vendor { get; set; }
        
        // References
        public string VendorTypeRef { get; set; }
        public string TermsRef { get; set; }
        
        // Other
        public string Notes { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // ITEMS - SERVICE (Item 6)
    // ============================================================
    public class ServiceItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string Description { get; set; }
        public decimal SalesPrice { get; set; }          // DECIMAL
        public decimal PurchaseCost { get; set; }        // DECIMAL
        public string IncomeAccountRef { get; set; }
        public string ExpenseAccountRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        public string UnitOfMeasureSetRef { get; set; }
        public bool IsActive { get; set; }
        public string ParentRef { get; set; }
    }

    // ============================================================
    // ITEMS - INVENTORY (Item 6)
    // ============================================================
    public class InventoryItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string Description { get; set; }
        
        // Pricing - DECIMAL
        public decimal SalesPrice { get; set; }
        public decimal PurchaseCost { get; set; }
        
        // Inventory - DECIMAL
        public decimal QuantityOnHand { get; set; }
        public decimal ReorderPoint { get; set; }
        public decimal QuantityOnOrder { get; set; }
        public decimal AverageCost { get; set; }
        
        // Accounts
        public string IncomeAccountRef { get; set; }
        public string COGSAccountRef { get; set; }
        public string AssetAccountRef { get; set; }
        
        // Other
        public string SalesTaxCodeRef { get; set; }
        public string UnitOfMeasureSetRef { get; set; }
        public bool IsActive { get; set; }
        public string ParentRef { get; set; }
    }

    // ============================================================
    // ITEMS - NON-INVENTORY (Item 6)
    // ============================================================
    public class NonInventoryItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string Description { get; set; }
        public decimal SalesPrice { get; set; }      // DECIMAL
        public decimal PurchaseCost { get; set; }    // DECIMAL
        public string IncomeAccountRef { get; set; }
        public string ExpenseAccountRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // ITEMS - OTHER CHARGE (Item 6)
    // ============================================================
    public class OtherChargeItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public decimal Rate { get; set; }            // DECIMAL
        public string AccountRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // ITEMS - DISCOUNT (Item 6)
    // ============================================================
    public class DiscountItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public decimal DiscountRate { get; set; }   // DECIMAL
        public string AccountRef { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // ITEMS - PAYMENT (Item 6)
    // ============================================================
    public class PaymentItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public string DepositToAccountRef { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // ITEMS - SALES TAX (Item 6)
    // ============================================================
    public class SalesTaxItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public decimal TaxRate { get; set; }        // DECIMAL
        public string TaxVendorRef { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // ITEMS - GROUP (Item 6)
    // ============================================================
    public class ItemGroupData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public List<ItemGroupLineData> Lines { get; set; }
        public bool IsActive { get; set; }
    }

    public class ItemGroupLineData
    {
        public string ItemRef { get; set; }
        public decimal Quantity { get; set; }       // DECIMAL
    }

    // ============================================================
    // INVOICES (Item 7)
    // ============================================================
    public class InvoiceData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public DateTime? DueDate { get; set; }
        
        // References
        public string CustomerRef { get; set; }
        public string ClassRef { get; set; }
        public string TermsRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        
        // Addresses
        public string BillAddr1 { get; set; }
        public string BillCity { get; set; }
        public string BillState { get; set; }
        public string ShipAddr1 { get; set; }
        public string ShipCity { get; set; }
        
        // Amounts - DECIMAL
        public decimal Subtotal { get; set; }
        public decimal SalesTaxAmount { get; set; }
        public decimal TotalAmount { get; set; }
        public decimal AmountPaid { get; set; }
        public decimal BalanceRemaining { get; set; }
        
        // Other
        public string PONumber { get; set; }
        public string Memo { get; set; }
        public string CustomerMessage { get; set; }
        public bool IsPending { get; set; }
        
        // Line Items
        public List<InvoiceLineData> Lines { get; set; }
    }

    public class InvoiceLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }       // DECIMAL
        public decimal Rate { get; set; }           // DECIMAL
        public decimal Amount { get; set; }         // DECIMAL
        public string ClassRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
    }

    // ============================================================
    // BILLS (Item 8)
    // ============================================================
    public class BillData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public DateTime? DueDate { get; set; }
        
        // References
        public string VendorRef { get; set; }
        public string TermsRef { get; set; }
        
        // Amounts - DECIMAL
        public decimal AmountDue { get; set; }
        public decimal AmountPaid { get; set; }
        public decimal Balance { get; set; }
        
        // Other
        public string Memo { get; set; }
        public bool IsPaid { get; set; }
        
        // Line Items
        public List<BillLineData> Lines { get; set; }
    }

    public class BillLineData
    {
        public string AccountRef { get; set; }
        public string Description { get; set; }
        public decimal Amount { get; set; }         // DECIMAL
        public string ClassRef { get; set; }
    }

    // ============================================================
    // PAYMENTS RECEIVED (Item 9)
    // ============================================================
    public class PaymentReceivedData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        
        // References
        public string CustomerRef { get; set; }
        public string PaymentMethodRef { get; set; }
        public string DepositToAccountRef { get; set; }
        
        // Amount - DECIMAL
        public decimal TotalAmount { get; set; }
        
        // Payment Details
        public string CheckNumber { get; set; }
        public string CreditCardTxnInfo { get; set; }
        
        // Applied To Invoices
        public List<PaymentAppliedToData> AppliedTo { get; set; }
        
        // Other
        public string Memo { get; set; }
        public decimal UnusedPayment { get; set; }  // DECIMAL
    }

    public class PaymentAppliedToData
    {
        public string TxnID { get; set; } // Invoice TxnID
        public decimal PaymentAmount { get; set; }  // DECIMAL
    }

    // ============================================================
    // BILL PAYMENTS (Item 10)
    // ============================================================
    public class BillPaymentData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        
        // References
        public string VendorRef { get; set; }
        public string PaymentMethodRef { get; set; }
        public string BankAccountRef { get; set; }
        
        // Amount - DECIMAL
        public decimal TotalAmount { get; set; }
        
        // Payment Details
        public string CheckNumber { get; set; }
        
        // Applied To Bills
        public List<BillPaymentAppliedToData> AppliedTo { get; set; }
        
        // Other
        public string Memo { get; set; }
    }

    public class BillPaymentAppliedToData
    {
        public string TxnID { get; set; } // Bill TxnID
        public decimal PaymentAmount { get; set; }  // DECIMAL
    }

    // ============================================================
    // EMPLOYEES (Item 11)
    // ============================================================
    public class EmployeeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
        
        // Contact
        public string Phone { get; set; }
        public string Email { get; set; }
        
        // Address
        public string Addr1 { get; set; }
        public string Addr2 { get; set; }  // ADDED
        public string Addr3 { get; set; }  // ADDED
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        
        // Employment
        public DateTime? HireDate { get; set; }
        public DateTime? ReleaseDate { get; set; }
        public string EmployeeType { get; set; }
        
        // Sensitive - MASK THIS!
        public string SSN { get; set; } // Should be masked: XXX-XX-1234
        
        // Other
        public bool IsActive { get; set; }
    }

    // ============================================================
    // SALES TAX CODES (Item 12)
    // ============================================================
    public class SalesTaxCodeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public bool IsTaxable { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // CLASSES (Item 13)
    // ============================================================
    public class ClassData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string ParentRef { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // TERMS (Item 14)
    // ============================================================
    public class TermsData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public int StdDueDays { get; set; }
        public int StdDiscountDays { get; set; }
        public decimal DiscountPct { get; set; }    // DECIMAL
        public bool IsActive { get; set; }
    }

    // ============================================================
    // PAYMENT METHODS (Item 15)
    // ============================================================
    public class PaymentMethodData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string PaymentMethodType { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // CREDIT MEMOS (Item 18)
    // ============================================================
    public class CreditMemoData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRef { get; set; }
        public decimal TotalAmount { get; set; }        // DECIMAL
        public decimal CreditRemaining { get; set; }    // DECIMAL
        public string Memo { get; set; }
        public List<CreditMemoLineData> Lines { get; set; }
    }

    public class CreditMemoLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }          // DECIMAL
        public decimal Rate { get; set; }              // DECIMAL
        public decimal Amount { get; set; }            // DECIMAL
    }

    // ============================================================
    // PURCHASE ORDERS (Item 19)
    // ============================================================
    public class PurchaseOrderData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string VendorRef { get; set; }
        public decimal TotalAmount { get; set; }       // DECIMAL
        public string Memo { get; set; }
        public bool IsManuallyClosed { get; set; }
        public List<PurchaseOrderLineData> Lines { get; set; }
    }

    public class PurchaseOrderLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }          // DECIMAL
        public decimal Rate { get; set; }              // DECIMAL
        public decimal Amount { get; set; }            // DECIMAL
    }

    // ============================================================
    // ESTIMATES (Item 20)
    // ============================================================
    public class EstimateData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRef { get; set; }
        public decimal TotalAmount { get; set; }       // DECIMAL
        public string Memo { get; set; }
        public bool IsActive { get; set; }
        public List<EstimateLineData> Lines { get; set; }
    }

    public class EstimateLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }          // DECIMAL
        public decimal Rate { get; set; }              // DECIMAL
        public decimal Amount { get; set; }            // DECIMAL
    }

    // ============================================================
    // SALES RECEIPTS (Item 21)
    // ============================================================
    public class SalesReceiptData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRef { get; set; }
        public string PaymentMethodRef { get; set; }
        public string DepositToAccountRef { get; set; }
        public decimal TotalAmount { get; set; }       // DECIMAL
        public string Memo { get; set; }
        public List<SalesReceiptLineData> Lines { get; set; }
    }

    public class SalesReceiptLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }          // DECIMAL
        public decimal Rate { get; set; }              // DECIMAL
        public decimal Amount { get; set; }            // DECIMAL
    }

    // ============================================================
    // DEPOSITS (Item 16)
    // ============================================================
    public class DepositData
    {
        public string TxnID { get; set; }
        public DateTime TxnDate { get; set; }
        public string DepositToAccountRef { get; set; }
        public decimal TotalDeposit { get; set; }      // DECIMAL
        public string Memo { get; set; }
        public List<DepositLineData> Lines { get; set; }
    }

    public class DepositLineData
    {
        public string PaymentTxnID { get; set; }
        public string EntityRef { get; set; }
        public decimal Amount { get; set; }            // DECIMAL
    }

    // ============================================================
    // JOURNAL ENTRIES (Item 17)
    // ============================================================
    public class JournalEntryData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string Memo { get; set; }
        public List<JournalEntryLineData> Lines { get; set; }
    }

    public class JournalEntryLineData
    {
        public string Type { get; set; } // "Debit" or "Credit"
        public string AccountRef { get; set; }
        public decimal Amount { get; set; }            // DECIMAL
        public string Memo { get; set; }
        public string EntityRef { get; set; }
        public string ClassRef { get; set; }
    }

    // ============================================================
    // PRICE LEVELS (Item 22)
    // ============================================================
    public class PriceLevelData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string PriceLevelType { get; set; }
        public decimal PriceLevelFixedPercentage { get; set; }  // DECIMAL
        public bool IsActive { get; set; }
    }

    // ============================================================
    // CUSTOMER TYPES (Item 23)
    // ============================================================
    public class CustomerTypeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string ParentRef { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // VENDOR TYPES (Item 24)
    // ============================================================
    public class VendorTypeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string ParentRef { get; set; }
        public bool IsActive { get; set; }
    }

    // ============================================================
    // JOB TYPES (Item 25)
    // ============================================================
    public class JobTypeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string ParentRef { get; set; }
        public bool IsActive { get; set; }
    }
}
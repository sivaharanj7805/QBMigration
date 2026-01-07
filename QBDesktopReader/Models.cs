using System;
using System.Collections.Generic;

namespace QBDesktopReader
{
    // ============================================================
    // ENHANCED DATA MODELS FOR QB DATA EXTRACTION - VERSION 2.0
    // Covers checklist items 3-30 with critical improvements:
    // - Audit metadata (TimeCreated, TimeModified, EditSequence)
    // - LinkedTxn support for transaction relationships
    // - Multi-currency tracking (CurrencyRef, ExchangeRate)
    // - Voided/Pending flags on all transactions
    // - Billable status tracking
    // - Unit of measure support
    // - Sales tax group details
    // - Company preferences (Item 30)
    // - Bank reconciliation support (Item 3)
    // - Job timeline tracking (Item 25)
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
        public string CompanyFile { get; set; }
        
        // Company Preferences (Item 30) - NEW
        public CompanyPreferences Preferences { get; set; }
        
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
        
        // Deleted records tracking (for incremental syncs) - NEW
        public List<DeletedRecord> DeletedRecords { get; set; }
    }

    // ============================================================
    // NEW SUPPORTING CLASSES
    // ============================================================
    
    /// <summary>
    /// Company preferences and settings (Item 30)
    /// </summary>
    public class CompanyPreferences
    {
        public string AccountingMethod { get; set; } // "Accrual" or "Cash"
        public bool UseAccountNumbers { get; set; }
        public bool UseClassTracking { get; set; }
        public string InventoryValuationMethod { get; set; } // "AverageCost" or "FIFO"
        public string FiscalYearStartMonth { get; set; }
        public bool IsMultiCurrencyEnabled { get; set; }
        public string HomeCurrency { get; set; }
    }

    /// <summary>
    /// Deleted record tracking for incremental syncs
    /// </summary>
    public class DeletedRecord
    {
        public string ListID { get; set; }
        public string TxnID { get; set; }
        public string RecordType { get; set; }
        public DateTime? TimeDeleted { get; set; }
    }

    /// <summary>
    /// Linked transaction reference (tracks relationships between transactions)
    /// </summary>
    public class LinkedTxn
    {
        public string TxnID { get; set; }
        public string TxnType { get; set; }
        public DateTime TxnDate { get; set; }
        public string RefNumber { get; set; }
        public decimal Amount { get; set; }
        public string LinkType { get; set; } // e.g., "Payment", "Credit", "Bill"
    }

    /// <summary>
    /// Sales tax group detail (for multi-component tax groups)
    /// </summary>
    public class SalesTaxGroupDetail
    {
        public string TaxItemRef { get; set; }
        public string TaxItemName { get; set; }
        public decimal TaxRate { get; set; }
        public decimal TaxAmount { get; set; }
    }

    // ============================================================
    // CHART OF ACCOUNTS (Item 3) - ENHANCED
    // ============================================================
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
        public string ParentRef { get; set; }
        public string TaxLineInfo { get; set; }
        public string SpecialAccountType { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Bank reconciliation support (Item 3) - NEW
        public decimal? ClearedBalance { get; set; }
        public DateTime? LastReconciledDate { get; set; }
    }

    // ============================================================
    // CUSTOMERS (Item 4) - ENHANCED
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
        
        // Financial
        public decimal Balance { get; set; }
        public decimal TotalBalance { get; set; }
        public decimal CreditLimit { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        
        // References
        public string CustomerTypeRef { get; set; }
        public string TermsRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        public string PriceLevelRef { get; set; }
        
        // Job tracking (Item 25)
        public string Notes { get; set; }
        public bool IsActive { get; set; }
        public string ParentRef { get; set; }
        public string JobStatus { get; set; }
        public DateTime? JobStartDate { get; set; }
        public DateTime? JobProjectedEndDate { get; set; } // NEW - for timeline tracking
        public DateTime? JobEndDate { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // VENDORS (Item 5) - ENHANCED
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
        
        // Address
        public string Addr1 { get; set; }
        public string Addr2 { get; set; }
        public string Addr3 { get; set; }
        public string Addr4 { get; set; }
        public string Addr5 { get; set; }
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public string Country { get; set; }
        public string Note { get; set; }
        
        // Financial
        public decimal Balance { get; set; }
        public decimal CreditLimit { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        
        // Tax
        public string TaxID { get; set; }
        public bool Is1099Vendor { get; set; }
        
        // References
        public string VendorTypeRef { get; set; }
        public string TermsRef { get; set; }
        
        // Other
        public string Notes { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // ITEMS - SERVICE (Item 6) - ENHANCED
    // ============================================================
    public class ServiceItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string Description { get; set; }
        public decimal SalesPrice { get; set; }
        public decimal PurchaseCost { get; set; }
        public string IncomeAccountRef { get; set; }
        public string ExpenseAccountRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        public string UnitOfMeasureSetRef { get; set; }
        public bool IsActive { get; set; }
        public string ParentRef { get; set; }
        
        // Unit of measure - NEW
        public string SalesUnitOfMeasure { get; set; }
        public string PurchaseUnitOfMeasure { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // ITEMS - INVENTORY (Item 6) - ENHANCED
    // ============================================================
    public class InventoryItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string Description { get; set; }
        
        // Pricing
        public decimal SalesPrice { get; set; }
        public decimal PurchaseCost { get; set; }
        
        // Inventory
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
        
        // Unit of measure - NEW
        public string SalesUnitOfMeasure { get; set; }
        public string PurchaseUnitOfMeasure { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // ITEMS - NON-INVENTORY (Item 6) - ENHANCED
    // ============================================================
    public class NonInventoryItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string Description { get; set; }
        public decimal SalesPrice { get; set; }
        public decimal PurchaseCost { get; set; }
        public string IncomeAccountRef { get; set; }
        public string ExpenseAccountRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        public bool IsActive { get; set; }
        
        // Unit of measure - NEW
        public string SalesUnitOfMeasure { get; set; }
        public string PurchaseUnitOfMeasure { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // ITEMS - OTHER CHARGE (Item 6) - ENHANCED
    // ============================================================
    public class OtherChargeItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public decimal Rate { get; set; }
        public string AccountRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // ITEMS - DISCOUNT (Item 6) - ENHANCED
    // ============================================================
    public class DiscountItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public decimal DiscountRate { get; set; }
        public string AccountRef { get; set; }
        public bool IsActive { get; set; }
        
        // Discount type - NEW
        public string DiscountRatePercent { get; set; } // "Percentage" or "FixedAmount"
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // ITEMS - PAYMENT (Item 6) - ENHANCED
    // ============================================================
    public class PaymentItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public string DepositToAccountRef { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // ITEMS - SALES TAX (Item 6) - ENHANCED
    // ============================================================
    public class SalesTaxItemData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public decimal TaxRate { get; set; }
        public string TaxVendorRef { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // ITEMS - GROUP (Item 6) - ENHANCED
    // ============================================================
    public class ItemGroupData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public List<ItemGroupLineData> Lines { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class ItemGroupLineData
    {
        public string ItemRef { get; set; }
        public decimal Quantity { get; set; }
        
        // Unit of measure - NEW
        public string UnitOfMeasure { get; set; }
    }

    // ============================================================
    // INVOICES (Item 7) - ENHANCED
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
        
        // Amounts
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
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
        
        // Sales tax group details - NEW
        public List<SalesTaxGroupDetail> SalesTaxGroupDetails { get; set; }
    }

    public class InvoiceLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        public string ClassRef { get; set; }
        public string SalesTaxCodeRef { get; set; }
        
        // Unit of measure - NEW
        public string UnitOfMeasure { get; set; }
        
        // Billable status - NEW
        public string BillableStatus { get; set; }  // "Billable", "NotBillable", "HasBeenBilled"
        
        // Tax information - NEW
        public bool IsTaxInclusive { get; set; }
    }

    // ============================================================
    // BILLS (Item 8) - ENHANCED
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
        
        // Amounts
        public decimal AmountDue { get; set; }
        public decimal AmountPaid { get; set; }
        public decimal Balance { get; set; }
        
        // Other
        public string Memo { get; set; }
        public bool IsPaid { get; set; }
        
        // Line Items
        public List<BillLineData> Lines { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        public bool IsPending { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
    }

    public class BillLineData
    {
        public string AccountRef { get; set; }
        public string Description { get; set; }
        public decimal Amount { get; set; }
        public string ClassRef { get; set; }
        
        // Billable status - NEW
        public string BillableStatus { get; set; }
        public string CustomerRef { get; set; }  // For billable expenses
    }

    // ============================================================
    // PAYMENTS RECEIVED (Item 9) - ENHANCED
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
        
        // Amount
        public decimal TotalAmount { get; set; }
        
        // Payment Details
        public string CheckNumber { get; set; }
        public string CreditCardTxnInfo { get; set; }
        
        // Applied To Invoices
        public List<PaymentAppliedToData> AppliedTo { get; set; }
        
        // Other
        public string Memo { get; set; }
        public decimal UnusedPayment { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
    }

    public class PaymentAppliedToData
    {
        public string TxnID { get; set; }
        public decimal PaymentAmount { get; set; }
    }

    // ============================================================
    // BILL PAYMENTS (Item 10) - ENHANCED
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
        
        // Amount
        public decimal TotalAmount { get; set; }
        
        // Payment Details
        public string CheckNumber { get; set; }
        
        // Applied To Bills
        public List<BillPaymentAppliedToData> AppliedTo { get; set; }
        
        // Other
        public string Memo { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
    }

    public class BillPaymentAppliedToData
    {
        public string TxnID { get; set; }
        public decimal PaymentAmount { get; set; }
    }

    // ============================================================
    // EMPLOYEES (Item 11) - ENHANCED
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
        public string Addr2 { get; set; }
        public string Addr3 { get; set; }
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
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // SALES TAX CODES (Item 12) - ENHANCED
    // ============================================================
    public class SalesTaxCodeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public bool IsTaxable { get; set; }
        public bool IsActive { get; set; }
        
        // Tax agency reference - NEW
        public string TaxAgencyRef { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // CLASSES (Item 13) - ENHANCED
    // ============================================================
    public class ClassData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string ParentRef { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // TERMS (Item 14) - ENHANCED
    // ============================================================
    public class TermsData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public int StdDueDays { get; set; }
        public int StdDiscountDays { get; set; }
        public decimal DiscountPct { get; set; }
        public bool IsActive { get; set; }
        
        // Date-driven terms support - NEW
        public int? DueDayOfMonth { get; set; }
        public string TermsType { get; set; } // "Standard" or "DateDriven"
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // PAYMENT METHODS (Item 15) - ENHANCED
    // ============================================================
    public class PaymentMethodData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string PaymentMethodType { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // CREDIT MEMOS (Item 18) - ENHANCED
    // ============================================================
    public class CreditMemoData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRef { get; set; }
        public decimal TotalAmount { get; set; }
        public decimal CreditRemaining { get; set; }
        public string Memo { get; set; }
        public List<CreditMemoLineData> Lines { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        public bool IsPending { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
    }

    public class CreditMemoLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        
        // Unit of measure - NEW
        public string UnitOfMeasure { get; set; }
        
        // Tax information - NEW
        public bool IsTaxInclusive { get; set; }
    }

    // ============================================================
    // PURCHASE ORDERS (Item 19) - ENHANCED
    // ============================================================
    public class PurchaseOrderData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string VendorRef { get; set; }
        public decimal TotalAmount { get; set; }
        public string Memo { get; set; }
        public bool IsManuallyClosed { get; set; }
        public List<PurchaseOrderLineData> Lines { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        public bool IsPending { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
    }

    public class PurchaseOrderLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        
        // Unit of measure - NEW
        public string UnitOfMeasure { get; set; }
    }

    // ============================================================
    // ESTIMATES (Item 20) - ENHANCED
    // ============================================================
    public class EstimateData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRef { get; set; }
        public decimal TotalAmount { get; set; }
        public string Memo { get; set; }
        public bool IsActive { get; set; }
        public List<EstimateLineData> Lines { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsPending { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
    }

    public class EstimateLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        
        // Unit of measure - NEW
        public string UnitOfMeasure { get; set; }
        
        // Tax information - NEW
        public bool IsTaxInclusive { get; set; }
    }

    // ============================================================
    // SALES RECEIPTS (Item 21) - ENHANCED
    // ============================================================
    public class SalesReceiptData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRef { get; set; }
        public string PaymentMethodRef { get; set; }
        public string DepositToAccountRef { get; set; }
        public decimal TotalAmount { get; set; }
        public string Memo { get; set; }
        public List<SalesReceiptLineData> Lines { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        public bool IsPending { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
        
        // Sales tax group details - NEW
        public List<SalesTaxGroupDetail> SalesTaxGroupDetails { get; set; }
    }

    public class SalesReceiptLineData
    {
        public string ItemRef { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        
        // Unit of measure - NEW
        public string UnitOfMeasure { get; set; }
        
        // Tax information - NEW
        public bool IsTaxInclusive { get; set; }
    }

    // ============================================================
    // DEPOSITS (Item 16) - ENHANCED
    // ============================================================
    public class DepositData
    {
        public string TxnID { get; set; }
        public DateTime TxnDate { get; set; }
        public string DepositToAccountRef { get; set; }
        public decimal TotalDeposit { get; set; }
        public string Memo { get; set; }
        public List<DepositLineData> Lines { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        // Linked transactions - NEW
        public List<LinkedTxn> LinkedTxns { get; set; }
    }

    public class DepositLineData
    {
        public string PaymentTxnID { get; set; }
        public string EntityRef { get; set; }
        public decimal Amount { get; set; }
    }

    // ============================================================
    // JOURNAL ENTRIES (Item 17) - ENHANCED
    // ============================================================
    public class JournalEntryData
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string Memo { get; set; }
        public List<JournalEntryLineData> Lines { get; set; }
        
        // Multi-currency support - NEW
        public string CurrencyRef { get; set; }
        public decimal? ExchangeRate { get; set; }
        
        // Transaction status - NEW
        public bool IsVoided { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class JournalEntryLineData
    {
        public string Type { get; set; } // "Debit" or "Credit"
        public string AccountRef { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public string EntityRef { get; set; }
        public string ClassRef { get; set; }
        
        // Billable status - NEW
        public string BillableStatus { get; set; }
    }

    // ============================================================
    // PRICE LEVELS (Item 22) - ENHANCED
    // ============================================================
    public class PriceLevelData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string PriceLevelType { get; set; }
        public decimal PriceLevelFixedPercentage { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // CUSTOMER TYPES (Item 23) - ENHANCED
    // ============================================================
    public class CustomerTypeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string ParentRef { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // VENDOR TYPES (Item 24) - ENHANCED
    // ============================================================
    public class VendorTypeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string ParentRef { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // ============================================================
    // JOB TYPES (Item 25) - ENHANCED
    // ============================================================
    public class JobTypeData
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public string ParentRef { get; set; }
        public bool IsActive { get; set; }
        
        // Audit metadata (Item 29) - NEW
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
    }
}
using System;
using System.Collections.Generic;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Main container for all extracted QuickBooks data
    /// </summary>
    public class QBExtractedData
    {
        // Extraction metadata
        public DateTime ExtractedAt { get; set; }
        public string SessionID { get; set; }
        public CompanyInfo Company { get; set; }
        public string QBVersion { get; set; }

        // Chart of Accounts
        public List<QBAccount> Accounts { get; set; } = new List<QBAccount>();

        // Lists/Master Data
        public List<QBCustomer> Customers { get; set; } = new List<QBCustomer>();
        public List<QBVendor> Vendors { get; set; } = new List<QBVendor>();
        public List<QBEmployee> Employees { get; set; } = new List<QBEmployee>();
        public List<QBLead> Leads { get; set; } = new List<QBLead>();
        public List<QBOtherName> OtherNames { get; set; } = new List<QBOtherName>();

        // Items
        public List<QBItem> Items { get; set; } = new List<QBItem>();

        // Configuration Lists
        public List<QBClass> Classes { get; set; } = new List<QBClass>();
        public List<QBPaymentMethod> PaymentMethods { get; set; } = new List<QBPaymentMethod>();
        public List<QBTerms> Terms { get; set; } = new List<QBTerms>();
        public List<QBDateDrivenTerms> DateDrivenTerms { get; set; } = new List<QBDateDrivenTerms>();
        public List<QBSalesTaxCode> SalesTaxCodes { get; set; } = new List<QBSalesTaxCode>();
        public List<QBCustomerType> CustomerTypes { get; set; } = new List<QBCustomerType>();
        public List<QBVendorType> VendorTypes { get; set; } = new List<QBVendorType>();
        public List<QBJobType> JobTypes { get; set; } = new List<QBJobType>();
        public List<QBCurrency> Currencies { get; set; } = new List<QBCurrency>();
        public List<QBCustomerMsg> CustomerMessages { get; set; } = new List<QBCustomerMsg>();

        // Transactions
        public List<QBInvoice> Invoices { get; set; } = new List<QBInvoice>();
        public List<QBPurchaseOrder> PurchaseOrders { get; set; } = new List<QBPurchaseOrder>();
        public List<QBSalesOrder> SalesOrders { get; set; } = new List<QBSalesOrder>();
        public List<QBBill> Bills { get; set; } = new List<QBBill>();
        public List<QBBillPaymentCheck> BillPayments { get; set; } = new List<QBBillPaymentCheck>();
        public List<QBReceivePayment> ReceivePayments { get; set; } = new List<QBReceivePayment>();
        public List<QBCreditMemo> CreditMemos { get; set; } = new List<QBCreditMemo>();
        public List<QBSalesReceipt> SalesReceipts { get; set; } = new List<QBSalesReceipt>();
        public List<QBPurchaseOrder> PurchaseOrders { get; set; } = new List<QBPurchaseOrder>();
        public List<QBEstimate> Estimates { get; set; } = new List<QBEstimate>();
        public List<QBJournalEntry> JournalEntries { get; set; } = new List<QBJournalEntry>();
        public List<QBCheck> Checks { get; set; } = new List<QBCheck>();
        public List<QBCreditCardCharge> CreditCardCharges { get; set; } = new List<QBCreditCardCharge>();
        public List<QBCreditCardCredit> CreditCardCredits { get; set; } = new List<QBCreditCardCredit>();
        public List<QBCharge> Charges { get; set; } = new List<QBCharge>();
        public List<QBDeposit> Deposits { get; set; } = new List<QBDeposit>();
        public List<QBInventoryAdjustment> InventoryAdjustments { get; set; } = new List<QBInventoryAdjustment>();
        public List<QBItemReceipt> ItemReceipts { get; set; } = new List<QBItemReceipt>();
        
        // Build Assemblies
        public List<QBBuildAssembly> BuildAssemblies { get; set; } = new List<QBBuildAssembly>();
        
        // Fund Transfers (between accounts)
        public List<QBTransfer> Transfers { get; set; } = new List<QBTransfer>();
        
        // Inventory Transfers (between locations)
        public List<QBInventoryTransfer> InventoryTransfers { get; set; } = new List<QBInventoryTransfer>();
        
        // Vendor Credits (credits from vendors)
        public List<QBVendorCredit> VendorCredits { get; set; } = new List<QBVendorCredit>();
        
        // AR Refunds (customer refunds via credit card)
        public List<QBARRefundCreditCard> ARRefundCreditCards { get; set; } = new List<QBARRefundCreditCard>();
        
        // Bill Payments - Credit Card
        public List<QBBillPaymentCreditCard> BillPaymentCreditCards { get; set; } = new List<QBBillPaymentCreditCard>();
        
        // Sales Tax Payments
        public List<QBSalesTaxPaymentCheck> SalesTaxPayments { get; set; } = new List<QBSalesTaxPaymentCheck>();
        
        // Sales Tax Groups (multi-jurisdiction)
        public List<QBSalesTaxGroup> SalesTaxGroups { get; set; } = new List<QBSalesTaxGroup>();
        
        // Report Verification
        public QBReportVerification ReportVerification { get; set; }
        
        // Company Preferences
        public QBPreferences Preferences { get; set; }
        
        // Data Extensions (Custom Fields)
        public List<QBDataExtension> DataExtensions { get; set; } = new List<QBDataExtension>();
        
        // Deleted Records (Audit Trail)
        public QBDeletedRecords DeletedRecords { get; set; }
        
        // Inventory Sites (multi-location)
        public List<QBInventorySite> InventorySites { get; set; } = new List<QBInventorySite>();
        
        // Payroll Items
        public List<QBPayrollItemWage> PayrollItemWages { get; set; } = new List<QBPayrollItemWage>();
        public List<QBPayrollItemNonWage> PayrollItemNonWages { get; set; } = new List<QBPayrollItemNonWage>();
        public List<QBWorkersCompCode> WorkersCompCodes { get; set; } = new List<QBWorkersCompCode>();
        public List<QBPriceLevel> PriceLevels { get; set; } = new List<QBPriceLevel>();
        public List<QBSalesRep> SalesReps { get; set; } = new List<QBSalesRep>();
        public List<QBShipMethod> ShipMethods { get; set; } = new List<QBShipMethod>();
        
        // Company Activity
        public QBCompanyActivity CompanyActivity { get; set; }
    }

    // =================================================================
    // LINKED TRANSACTIONS (Payment Application Tracking - CRITICAL!)
    // =================================================================
    /// <summary>
    /// Tracks which payment/credit was applied to which invoice/bill
    /// This is THE most critical piece for accurate AR/AP migration
    /// </summary>
    public class QBLinkedTxn
    {
        public string TxnID { get; set; }
        public string TxnType { get; set; }  // "Invoice", "Bill", "CreditMemo", etc.
        public DateTime TxnDate { get; set; }
        public string RefNumber { get; set; }
        public decimal LinkAmount { get; set; }  // Amount applied to this transaction
    }

    // =================================================================
    // CHART OF ACCOUNTS
    // =================================================================
    public class QBAccount
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool IsActive { get; set; }
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int Sublevel { get; set; }
        public string AccountType { get; set; }
        public string SpecialAccountType { get; set; }
        public bool IsTaxAccount { get; set; }
        public string AccountNumber { get; set; }
        public string BankNumber { get; set; }
        public string Desc { get; set; }
        public decimal Balance { get; set; }
        public decimal TotalBalance { get; set; }
        public string SalesTaxCodeRefListID { get; set; }
        public string SalesTaxCodeRefFullName { get; set; }
        public int TaxLineID { get; set; }
        public string TaxLineName { get; set; }
        public string CashFlowClassification { get; set; }
        public string CurrencyRefListID { get; set; }
        public string CurrencyRefFullName { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // CUSTOMERS
    // =================================================================
    public class QBCustomer
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool IsActive { get; set; }
        public string CompanyName { get; set; }
        public string Salutation { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
        
        // Bill Address
        public string BillAddressAddr1 { get; set; }
        public string BillAddressAddr2 { get; set; }
        public string BillAddressAddr3 { get; set; }
        public string BillAddressAddr4 { get; set; }
        public string BillAddressAddr5 { get; set; }
        public string BillAddressCity { get; set; }
        public string BillAddressState { get; set; }
        public string BillAddressPostalCode { get; set; }
        public string BillAddressCountry { get; set; }
        public string BillAddressNote { get; set; }

        // Ship Address
        public string ShipAddressAddr1 { get; set; }
        public string ShipAddressAddr2 { get; set; }
        public string ShipAddressAddr3 { get; set; }
        public string ShipAddressAddr4 { get; set; }
        public string ShipAddressAddr5 { get; set; }
        public string ShipAddressCity { get; set; }
        public string ShipAddressState { get; set; }
        public string ShipAddressPostalCode { get; set; }
        public string ShipAddressCountry { get; set; }
        public string ShipAddressNote { get; set; }

        // Contact Info
        public string Phone { get; set; }
        public string AltPhone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        public string Contact { get; set; }
        public string AltContact { get; set; }

        // Financial Info
        public string CustomerTypeRefListID { get; set; }
        public string CustomerTypeRefFullName { get; set; }
        public string TermsRefListID { get; set; }
        public string TermsRefFullName { get; set; }
        public string SalesRepRefListID { get; set; }
        public string SalesRepRefFullName { get; set; }
        public decimal Balance { get; set; }
        public decimal TotalBalance { get; set; }
        public string SalesTaxCodeRefListID { get; set; }
        public string SalesTaxCodeRefFullName { get; set; }
        public string ItemSalesTaxRefListID { get; set; }
        public string ItemSalesTaxRefFullName { get; set; }
        public string ResaleNumber { get; set; }
        public string AccountNumber { get; set; }
        public decimal CreditLimit { get; set; }
        public string PrefPaymentMethodRefListID { get; set; }
        public string PrefPaymentMethodRefFullName { get; set; }
        public string CreditCardInfo { get; set; }
        public string JobStatus { get; set; }
        public DateTime JobStartDate { get; set; }
        public DateTime JobProjectedEndDate { get; set; }
        public DateTime JobEndDate { get; set; }
        public string JobDesc { get; set; }
        public string JobTypeRefListID { get; set; }
        public string JobTypeRefFullName { get; set; }
        public string Notes { get; set; }
        public string PriceLevelRefListID { get; set; }
        public string PriceLevelRefFullName { get; set; }

        // Parent/Sub info
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int Sublevel { get; set; }

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // VENDORS
    // =================================================================
    public class QBVendor
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool IsActive { get; set; }
        public string CompanyName { get; set; }
        public string Salutation { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }

        // Vendor Address
        public string VendorAddressAddr1 { get; set; }
        public string VendorAddressAddr2 { get; set; }
        public string VendorAddressAddr3 { get; set; }
        public string VendorAddressAddr4 { get; set; }
        public string VendorAddressAddr5 { get; set; }
        public string VendorAddressCity { get; set; }
        public string VendorAddressState { get; set; }
        public string VendorAddressPostalCode { get; set; }
        public string VendorAddressCountry { get; set; }
        public string VendorAddressNote { get; set; }

        // Contact Info
        public string Phone { get; set; }
        public string AltPhone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        public string Contact { get; set; }
        public string AltContact { get; set; }

        // Financial Info
        public string VendorTypeRefListID { get; set; }
        public string VendorTypeRefFullName { get; set; }
        public string TermsRefListID { get; set; }
        public string TermsRefFullName { get; set; }
        public decimal CreditLimit { get; set; }
        public string VendorTaxIdent { get; set; }
        public bool IsVendorEligibleFor1099 { get; set; }
        public decimal Balance { get; set; }
        public string BillingRateRefListID { get; set; }
        public string BillingRateRefFullName { get; set; }

        // Parent/Sub info
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int Sublevel { get; set; }

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // EMPLOYEES
    // =================================================================
    public class QBEmployee
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string Salutation { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }

        // Employee Address
        public string EmployeeAddressAddr1 { get; set; }
        public string EmployeeAddressAddr2 { get; set; }
        public string EmployeeAddressAddr3 { get; set; }
        public string EmployeeAddressAddr4 { get; set; }
        public string EmployeeAddressAddr5 { get; set; }
        public string EmployeeAddressCity { get; set; }
        public string EmployeeAddressState { get; set; }
        public string EmployeeAddressPostalCode { get; set; }
        public string EmployeeAddressCountry { get; set; }

        // Contact Info
        public string Phone { get; set; }
        public string AltPhone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        public string EmployeeType { get; set; }
        public string Gender { get; set; }
        public DateTime HiredDate { get; set; }
        public DateTime ReleasedDate { get; set; }
        public DateTime BirthDate { get; set; }
        public string AccountNumber { get; set; }
        public string Notes { get; set; }
        public string BillingRateRefListID { get; set; }
        public string BillingRateRefFullName { get; set; }

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // LEADS (Potential Customers)
    // =================================================================
    public class QBLead
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string Salutation { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
        public string CompanyName { get; set; }
        public string JobTitle { get; set; }
        
        // Address
        public string Addr1 { get; set; }
        public string Addr2 { get; set; }
        public string Addr3 { get; set; }
        public string Addr4 { get; set; }
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public string Country { get; set; }
        
        // Contact Info
        public string Phone { get; set; }
        public string AltPhone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        public string Contact { get; set; }
        public string AltContact { get; set; }
        public string Notes { get; set; }
        
        // Lead-specific fields
        public bool IsConverted { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // OTHER NAMES (Contacts that aren't Customers/Vendors/Employees)
    // =================================================================
    public class QBOtherName
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string CompanyName { get; set; }
        public string Salutation { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
        
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
        
        // Contact Info
        public string Phone { get; set; }
        public string AltPhone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        public string Contact { get; set; }
        public string AltContact { get; set; }
        public string AccountNumber { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // ITEMS (All Types Combined)
    // =================================================================
    public class QBItem
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool IsActive { get; set; }
        public string Type { get; set; } // Service, Inventory, NonInventory, OtherCharge, etc.
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int Sublevel { get; set; }
        public string Description { get; set; }
        public decimal Price { get; set; }
        public string PricePercent { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }

        // Inventory-specific
        public string AssetAccountRefListID { get; set; }
        public string AssetAccountRefFullName { get; set; }
        public string COGSAccountRefListID { get; set; }
        public string COGSAccountRefFullName { get; set; }
        public decimal QuantityOnHand { get; set; }
        public decimal AverageCost { get; set; }
        public int QuantityOnOrder { get; set; }
        public int QuantityOnSalesOrder { get; set; }
        public DateTime ReorderPoint { get; set; }
        public string ManufacturerPartNumber { get; set; }

        // Service/Item-specific
        public string SalesOrPurchaseDesc { get; set; }
        public decimal SalesOrPurchasePrice { get; set; }
        public string SalesOrPurchaseAccountRefListID { get; set; }
        public string SalesOrPurchaseAccountRefFullName { get; set; }

        // Sales Tax
        public string SalesTaxCodeRefListID { get; set; }
        public string SalesTaxCodeRefFullName { get; set; }
        public decimal TaxRate { get; set; }
        public string TaxVendorRefListID { get; set; }
        public string TaxVendorRefFullName { get; set; }

        // Assembly Bill of Materials (CRITICAL for manufacturing)
        public List<QBAssemblyComponent> AssemblyComponents { get; set; } = new List<QBAssemblyComponent>();
        
        // Group Item Components (CRITICAL for retail bundles)
        public List<QBGroupItemComponent> GroupComponents { get; set; } = new List<QBGroupItemComponent>();
        
        // Sales Tax Group Components (for multi-jurisdiction tax)
        public List<QBSalesTaxGroupComponent> SalesTaxGroupComponents { get; set; } = new List<QBSalesTaxGroupComponent>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    /// <summary>
    /// Components that make up an Assembly item (Bill of Materials)
    /// </summary>
    public class QBAssemblyComponent
    {
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public decimal Quantity { get; set; }
    }

    /// <summary>
    /// Items within a Group/Bundle
    /// </summary>
    public class QBGroupItemComponent
    {
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public decimal Quantity { get; set; }
        public string UnitOfMeasure { get; set; }
    }

    /// <summary>
    /// Individual tax items within a Sales Tax Group
    /// </summary>
    public class QBSalesTaxGroupComponent
    {
        public string ItemSalesTaxRefListID { get; set; }
        public string ItemSalesTaxRefFullName { get; set; }
    }

    // =================================================================
    // CONFIGURATION LISTS
    // =================================================================
    public class QBClass
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool IsActive { get; set; }
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int Sublevel { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBPaymentMethod
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string PaymentMethodType { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBTerms
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public int StdDueDays { get; set; }
        public int StdDiscountDays { get; set; }
        public decimal DiscountPct { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBSalesTaxCode
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public bool IsTaxable { get; set; }
        public string Desc { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBCustomerType
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool IsActive { get; set; }
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int Sublevel { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBVendorType
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool IsActive { get; set; }
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int Sublevel { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBJobType
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool IsActive { get; set; }
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int Sublevel { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // TRANSACTIONS
    // =================================================================
    public class QBInvoice
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string ARAccountRefListID { get; set; }
        public string ARAccountRefFullName { get; set; }
        public string TermsRefListID { get; set; }
        public string TermsRefFullName { get; set; }
        public DateTime DueDate { get; set; }
        public string SalesRepRefListID { get; set; }
        public string SalesRepRefFullName { get; set; }
        public string PONumber { get; set; }
        public decimal Subtotal { get; set; }
        public decimal SalesTaxPercentage { get; set; }
        public decimal SalesTaxTotal { get; set; }
        public decimal AppliedAmount { get; set; }
        public decimal BalanceRemaining { get; set; }
        public string Memo { get; set; }
        public bool IsPending { get; set; }
        public bool IsPaid { get; set; }
        public string CustomerMsgRefListID { get; set; }
        public string CustomerMsgRefFullName { get; set; }
        public bool IsToBePrinted { get; set; }
        public bool IsToBeEmailed { get; set; }
        public string CustomerSalesTaxCodeRefListID { get; set; }
        public string CustomerSalesTaxCodeRefFullName { get; set; }
        public List<QBInvoiceLine> Lines { get; set; } = new List<QBInvoiceLine>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBInvoiceLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public string UnitOfMeasure { get; set; }
        public decimal Rate { get; set; }
        public decimal RatePercent { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string SalesTaxCodeRefListID { get; set; }
        public string SalesTaxCodeRefFullName { get; set; }
    }

    // =================================================================
    // PURCHASE ORDERS
    // =================================================================
    public class QBPurchaseOrder
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public DateTime ExpectedDate { get; set; }
        public string VendorRefListID { get; set; }
        public string VendorRefFullName { get; set; }
        public string VendorMsg { get; set; }
        public string Memo { get; set; }
        public decimal Subtotal { get; set; }
        public decimal SalesTaxTotal { get; set; }
        public decimal TotalAmount { get; set; }
        public string CurrencyRefListID { get; set; }
        public string CurrencyRefFullName { get; set; }
        public bool IsManuallyClosed { get; set; }
        public bool IsFullyReceived { get; set; }
        
        // Shipping
        public string ShipToEntityRefListID { get; set; }
        public string ShipToEntityRefFullName { get; set; }
        public string ShipAddress { get; set; }
        public string ShipMethodRefListID { get; set; }
        public string ShipMethodRefFullName { get; set; }
        public DateTime ShipDate { get; set; }
        
        public List<QBPurchaseOrderLine> Lines { get; set; } = new List<QBPurchaseOrderLine>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBPurchaseOrderLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public string UnitOfMeasure { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public bool IsManuallyClosed { get; set; }
        public decimal ReceivedQuantity { get; set; }
    }

    // =================================================================
    // SALES ORDERS
    // =================================================================
    public class QBSalesOrder
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public DateTime DueDate { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string TemplateRefListID { get; set; }
        public string TemplateRefFullName { get; set; }
        public string PONumber { get; set; }
        public string Memo { get; set; }
        public string CustomerMsg { get; set; }
        public decimal Subtotal { get; set; }
        public decimal SalesTaxTotal { get; set; }
        public decimal TotalAmount { get; set; }
        public string CurrencyRefListID { get; set; }
        public string CurrencyRefFullName { get; set; }
        public bool IsManuallyClosed { get; set; }
        public bool IsFullyInvoiced { get; set; }
        
        // Billing & Shipping
        public string BillAddress { get; set; }
        public string ShipAddress { get; set; }
        public string ShipMethodRefListID { get; set; }
        public string ShipMethodRefFullName { get; set; }
        public DateTime ShipDate { get; set; }
        
        public List<QBSalesOrderLine> Lines { get; set; } = new List<QBSalesOrderLine>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBSalesOrderLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public string UnitOfMeasure { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string SalesTaxCodeRefListID { get; set; }
        public string SalesTaxCodeRefFullName { get; set; }
        public bool IsManuallyClosed { get; set; }
        public decimal Invoiced { get; set; }
    }

    // =================================================================
    // BILLS
    // =================================================================
    public class QBBill
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public DateTime DueDate { get; set; }
        public string VendorRefListID { get; set; }
        public string VendorRefFullName { get; set; }
        public decimal AmountDue { get; set; }
        public string CurrencyRefListID { get; set; }
        public string CurrencyRefFullName { get; set; }
        public string APAccountRefListID { get; set; }
        public string APAccountRefFullName { get; set; }
        public string Memo { get; set; }
        public bool IsPaid { get; set; }
        public List<QBBillLine> ExpenseLines { get; set; } = new List<QBBillLine>();
        public List<QBBillItemLine> ItemLines { get; set; } = new List<QBBillItemLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBBillLine
    {
        public string TxnLineID { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    public class QBBillItemLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public decimal Cost { get; set; }
        public decimal Amount { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    public class QBBillPaymentCheck
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string VendorRefListID { get; set; }
        public string VendorRefFullName { get; set; }
        public string APAccountRefListID { get; set; }
        public string APAccountRefFullName { get; set; }
        public string BankAccountRefListID { get; set; }
        public string BankAccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public bool IsToBePrinted { get; set; }
        
        // CRITICAL: Track which bills this payment was applied to
        public List<QBLinkedTxn> LinkedTransactions { get; set; } = new List<QBLinkedTxn>();
        
        public List<QBBillPaymentLine> AppliedToTxns { get; set; } = new List<QBBillPaymentLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBBillPaymentLine
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public decimal AppliedAmount { get; set; }
        public decimal BalanceRemaining { get; set; }
    }

    // =================================================================
    // VENDOR CREDITS (Credits from Vendors)
    // =================================================================
    public class QBVendorCredit
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string VendorRefListID { get; set; }
        public string VendorRefFullName { get; set; }
        public string APAccountRefListID { get; set; }
        public string APAccountRefFullName { get; set; }
        public decimal CreditAmount { get; set; }
        public string Memo { get; set; }
        public bool IsPaid { get; set; }
        public decimal CreditRemaining { get; set; }
        
        public List<QBVendorCreditExpenseLine> ExpenseLines { get; set; } = new List<QBVendorCreditExpenseLine>();
        public List<QBVendorCreditItemLine> ItemLines { get; set; } = new List<QBVendorCreditItemLine>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBVendorCreditExpenseLine
    {
        public string TxnLineID { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    public class QBVendorCreditItemLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public string UnitOfMeasure { get; set; }
        public decimal Cost { get; set; }
        public decimal Amount { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    public class QBReceivePayment
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ARAccountRefListID { get; set; }
        public string ARAccountRefFullName { get; set; }
        public decimal TotalAmount { get; set; }
        public string PaymentMethodRefListID { get; set; }
        public string PaymentMethodRefFullName { get; set; }
        public string Memo { get; set; }
        public string DepositToAccountRefListID { get; set; }
        public string DepositToAccountRefFullName { get; set; }
        
        // CRITICAL: Track which invoices this payment was applied to
        public List<QBLinkedTxn> LinkedTransactions { get; set; } = new List<QBLinkedTxn>();
        
        public List<QBReceivePaymentLine> AppliedToTxns { get; set; } = new List<QBReceivePaymentLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBReceivePaymentLine
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public decimal AppliedAmount { get; set; }
        public decimal BalanceRemaining { get; set; }
    }

    public class QBCreditMemo
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string ARAccountRefListID { get; set; }
        public string ARAccountRefFullName { get; set; }
        public decimal Subtotal { get; set; }
        public decimal SalesTaxPercentage { get; set; }
        public decimal SalesTaxTotal { get; set; }
        public decimal TotalAmount { get; set; }
        public decimal CreditRemaining { get; set; }
        public string Memo { get; set; }
        public bool IsPending { get; set; }
        public List<QBCreditMemoLine> Lines { get; set; } = new List<QBCreditMemoLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBCreditMemoLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
    }

    public class QBSalesReceipt
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string DepositToAccountRefListID { get; set; }
        public string DepositToAccountRefFullName { get; set; }
        public string PaymentMethodRefListID { get; set; }
        public string PaymentMethodRefFullName { get; set; }
        public decimal Subtotal { get; set; }
        public decimal SalesTaxPercentage { get; set; }
        public decimal SalesTaxTotal { get; set; }
        public decimal TotalAmount { get; set; }
        public string Memo { get; set; }
        public bool IsPending { get; set; }
        public bool IsToBePrinted { get; set; }
        public List<QBSalesReceiptLine> Lines { get; set; } = new List<QBSalesReceiptLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBSalesReceiptLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
    }

    public class QBPurchaseOrder
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string VendorRefListID { get; set; }
        public string VendorRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public DateTime ExpectedDate { get; set; }
        public string ShipMethodRefListID { get; set; }
        public string ShipMethodRefFullName { get; set; }
        public string FOB { get; set; }
        public decimal TotalAmount { get; set; }
        public bool IsManuallyClosed { get; set; }
        public bool IsFullyReceived { get; set; }
        public string Memo { get; set; }
        public string VendorMsg { get; set; }
        public bool IsToBePrinted { get; set; }
        public bool IsToBeEmailed { get; set; }
        public List<QBPurchaseOrderLine> Lines { get; set; } = new List<QBPurchaseOrderLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBPurchaseOrderLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public bool IsManuallyClosed { get; set; }
    }

    public class QBEstimate
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public decimal Subtotal { get; set; }
        public decimal SalesTaxPercentage { get; set; }
        public decimal SalesTaxTotal { get; set; }
        public decimal TotalAmount { get; set; }
        public bool IsActive { get; set; }
        public string Memo { get; set; }
        public string CustomerMsgRefListID { get; set; }
        public string CustomerMsgRefFullName { get; set; }
        public bool IsToBePrinted { get; set; }
        public bool IsToBeEmailed { get; set; }
        public List<QBEstimateLine> Lines { get; set; } = new List<QBEstimateLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBEstimateLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public decimal MarkupRate { get; set; }
        public decimal MarkupRatePercent { get; set; }
    }

    public class QBJournalEntry
    {
        public string TxnID { get; set; }
        public DateTime TxnDate { get; set; }
        public string RefNumber { get; set; }
        public bool IsAdjustment { get; set; }
        public string Memo { get; set; }
        public List<QBJournalEntryLine> Lines { get; set; } = new List<QBJournalEntryLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBJournalEntryLine
    {
        public string TxnLineID { get; set; }
        public string Type { get; set; } // "Debit" or "Credit"
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public string EntityRefListID { get; set; }
        public string EntityRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    // =================================================================
    // CHECKS
    // =================================================================
    public class QBCheck
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string PayeeEntityRefListID { get; set; }
        public string PayeeEntityRefFullName { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public string Address { get; set; }
        public bool IsToBePrinted { get; set; }
        
        // Bank Reconciliation (CRITICAL for preserving bank rec work)
        public string ClearedStatus { get; set; }  // "NotCleared", "Cleared", "Reconciled"
        
        public List<QBCheckExpenseLine> ExpenseLines { get; set; } = new List<QBCheckExpenseLine>();
        public List<QBCheckItemLine> ItemLines { get; set; } = new List<QBCheckItemLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBCheckExpenseLine
    {
        public string TxnLineID { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    public class QBCheckItemLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public decimal Cost { get; set; }
        public decimal Amount { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    // =================================================================
    // CREDIT CARD CHARGES
    // =================================================================
    public class QBCreditCardCharge
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string PayeeEntityRefListID { get; set; }
        public string PayeeEntityRefFullName { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        
        // Bank Reconciliation
        public string ClearedStatus { get; set; }  // "NotCleared", "Cleared", "Reconciled"
        
        public List<QBCreditCardChargeExpenseLine> ExpenseLines { get; set; } = new List<QBCreditCardChargeExpenseLine>();
        public List<QBCreditCardChargeItemLine> ItemLines { get; set; } = new List<QBCreditCardChargeItemLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBCreditCardChargeExpenseLine
    {
        public string TxnLineID { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    public class QBCreditCardChargeItemLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public decimal Cost { get; set; }
        public decimal Amount { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    // =================================================================
    // CREDIT CARD CREDITS
    // =================================================================
    public class QBCreditCardCredit
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string PayeeEntityRefListID { get; set; }
        public string PayeeEntityRefFullName { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        
        // Bank Reconciliation
        public string ClearedStatus { get; set; }  // "NotCleared", "Cleared", "Reconciled"
        
        public List<QBCreditCardCreditExpenseLine> ExpenseLines { get; set; } = new List<QBCreditCardCreditExpenseLine>();
        public List<QBCreditCardCreditItemLine> ItemLines { get; set; } = new List<QBCreditCardCreditItemLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBCreditCardCreditExpenseLine
    {
        public string TxnLineID { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    public class QBCreditCardCreditItemLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Desc { get; set; }
        public decimal Quantity { get; set; }
        public decimal Cost { get; set; }
        public decimal Amount { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string BillableStatus { get; set; }
    }

    // =================================================================
    // CHARGES
    // =================================================================
    public class QBCharge
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public decimal Quantity { get; set; }
        public decimal Rate { get; set; }
        public decimal Amount { get; set; }
        public string Desc { get; set; }
        public string ARAccountRefListID { get; set; }
        public string ARAccountRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // BUILD ASSEMBLIES
    // =================================================================
    public class QBBuildAssembly
    {
        public string TxnID { get; set; }
        public DateTime TxnDate { get; set; }
        public string RefNumber { get; set; }
        public string ItemInventoryAssemblyRefListID { get; set; }
        public string ItemInventoryAssemblyRefFullName { get; set; }
        public decimal QuantityToBuild { get; set; }
        public decimal QuantityCanBuild { get; set; }
        public decimal QuantityOnHand { get; set; }
        public string Memo { get; set; }
        public bool RemoveFromSite { get; set; }
        public List<QBBuildAssemblyLine> ComponentLines { get; set; } = new List<QBBuildAssemblyLine>();

        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBBuildAssemblyLine
    {
        public string ItemInventoryRefListID { get; set; }
        public string ItemInventoryRefFullName { get; set; }
        public decimal QuantityNeeded { get; set; }
        public decimal QuantityOnHand { get; set; }
    }

    // =================================================================
    // TRANSFERS (Fund Transfers Between Accounts)
    // =================================================================
    public class QBTransfer
    {
        public string TxnID { get; set; }
        public DateTime TxnDate { get; set; }
        public string TransferFromAccountRefListID { get; set; }
        public string TransferFromAccountRefFullName { get; set; }
        public decimal FromAccountBalance { get; set; }
        public string TransferToAccountRefListID { get; set; }
        public string TransferToAccountRefFullName { get; set; }
        public decimal ToAccountBalance { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        
        // Bank Reconciliation
        public string ClearedStatus { get; set; }  // "NotCleared", "Cleared", "Reconciled"
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // INVENTORY TRANSFERS (Between Locations)
    // =================================================================
    public class QBInventoryTransfer
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string InventorySiteFromRefListID { get; set; }
        public string InventorySiteFromRefFullName { get; set; }
        public string InventorySiteToRefListID { get; set; }
        public string InventorySiteToRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string Memo { get; set; }
        
        public List<QBInventoryTransferLine> Lines { get; set; } = new List<QBInventoryTransferLine>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBInventoryTransferLine
    {
        public string TxnLineID { get; set; }
        public string ItemInventoryRefListID { get; set; }
        public string ItemInventoryRefFullName { get; set; }
        public decimal QuantityTransferred { get; set; }
        public string SerialNumber { get; set; }
        public string LotNumber { get; set; }
    }

    // =================================================================
    // COMPANY ACTIVITY
    // =================================================================
    public class QBCompanyActivity
    {
        public DateTime LastRestoreTime { get; set; }
        public DateTime LastCondenseTime { get; set; }
    }

    // =================================================================
    // CURRENCY (Multi-Currency Support)
    // =================================================================
    public class QBCurrency
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string CurrencyCode { get; set; }
        public bool IsUserDefinedCurrency { get; set; }
        public double ExchangeRate { get; set; }
        public DateTime AsOfDate { get; set; }
        
        // Currency Format
        public string ThousandSeparator { get; set; }
        public string ThousandSeparatorGrouping { get; set; }
        public string DecimalPlaces { get; set; }
        public string DecimalSeparator { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // CUSTOMER MESSAGES
    // =================================================================
    public class QBCustomerMsg
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // DATE-DRIVEN TERMS (Alternative Payment Terms)
    // =================================================================
    public class QBDateDrivenTerms
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public int DayOfMonthDue { get; set; }
        public int DueNextMonthDays { get; set; }
        public int DiscountDayOfMonth { get; set; }
        public decimal DiscountPct { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // DEPOSITS (Bank Deposits)
    // =================================================================
    public class QBDeposit
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string DepositToAccountRefListID { get; set; }
        public string DepositToAccountRefFullName { get; set; }
        public decimal DepositTotal { get; set; }
        public string Memo { get; set; }
        public string CurrencyRefListID { get; set; }
        public string CurrencyRefFullName { get; set; }
        
        // Bank Reconciliation
        public string ClearedStatus { get; set; }  // "NotCleared", "Cleared", "Reconciled"
        
        public List<QBDepositLine> DepositLines { get; set; } = new List<QBDepositLine>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBDepositLine
    {
        public string TxnLineID { get; set; }
        
        // CRITICAL: Track which payment/receipt is in this deposit
        public string LinkedTxnType { get; set; }  // "ReceivePayment", "SalesReceipt"
        public string LinkedTxnID { get; set; }
        
        public string PaymentMethod { get; set; }
        public string PaymentTxnID { get; set; }
        public string PaymentTxnLineID { get; set; }
        public string EntityRefListID { get; set; }
        public string EntityRefFullName { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public string Memo { get; set; }
        public string CheckNumber { get; set; }
        public string PaymentMethodRefListID { get; set; }
        public string PaymentMethodRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public decimal Amount { get; set; }
    }

    // =================================================================
    // INVENTORY ADJUSTMENTS
    // =================================================================
    public class QBInventoryAdjustment
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public string InventorySiteRefListID { get; set; }
        public string InventorySiteRefFullName { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string Memo { get; set; }
        public List<QBInventoryAdjustmentLine> Lines { get; set; } = new List<QBInventoryAdjustmentLine>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBInventoryAdjustmentLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public decimal QuantityDifference { get; set; }
        public decimal ValueDifference { get; set; }
        public decimal NewQuantity { get; set; }
        public decimal NewValue { get; set; }
        public string SerialNumber { get; set; }
        public string LotNumber { get; set; }
    }

    // =================================================================
    // INVENTORY SITES (Multi-Location Inventory)
    // =================================================================
    public class QBInventorySite
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string Description { get; set; }
        public string Email { get; set; }
        public string Contact { get; set; }
        public string Phone { get; set; }
        public string Fax { get; set; }
        
        // Address
        public string Addr1 { get; set; }
        public string Addr2 { get; set; }
        public string Addr3 { get; set; }
        public string Addr4 { get; set; }
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public string Country { get; set; }
        public string Note { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // PAYROLL ITEMS - WAGE (Salaries, Hourly, Bonuses, etc.)
    // =================================================================
    public class QBPayrollItemWage
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string WageType { get; set; }
        public string ExpenseAccountRefListID { get; set; }
        public string ExpenseAccountRefFullName { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // PAYROLL ITEMS - NON-WAGE (Benefits, Deductions, Taxes, etc.)
    // =================================================================
    public class QBPayrollItemNonWage
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string NonWageType { get; set; }
        public string ExpenseAccountRefListID { get; set; }
        public string ExpenseAccountRefFullName { get; set; }
        public string LiabilityAccountRefListID { get; set; }
        public string LiabilityAccountRefFullName { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // WORKERS COMP CODES (Workers Compensation Insurance)
    // =================================================================
    public class QBWorkersCompCode
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string Desc { get; set; }
        public decimal CurrentRate { get; set; }
        public DateTime CurrentEffectiveDate { get; set; }
        public decimal NextRate { get; set; }
        public DateTime NextEffectiveDate { get; set; }
        
        public List<QBWorkersCompRateHistory> RateHistory { get; set; } = new List<QBWorkersCompRateHistory>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBWorkersCompRateHistory
    {
        public decimal Rate { get; set; }
        public DateTime EffectiveDate { get; set; }
    }

    // =================================================================
    // PRICE LEVELS (Customer Pricing Tiers)
    // =================================================================
    public class QBPriceLevel
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        public string PriceLevelType { get; set; }
        public decimal FixedPercentage { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // SALES REPS (Sales Representative Tracking)
    // =================================================================
    public class QBSalesRep
    {
        public string ListID { get; set; }
        public string Initial { get; set; }
        public bool IsActive { get; set; }
        public string SalesRepEntityRefListID { get; set; }
        public string SalesRepEntityRefFullName { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // SHIP METHODS (Shipping/Delivery Methods)
    // =================================================================
    public class QBShipMethod
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public bool IsActive { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // ITEM RECEIPTS (Receive Inventory from Vendors)
    // =================================================================
    public class QBItemReceipt
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string VendorRefListID { get; set; }
        public string VendorRefFullName { get; set; }
        public string APAccountRefListID { get; set; }
        public string APAccountRefFullName { get; set; }
        public string Memo { get; set; }
        public decimal Subtotal { get; set; }
        public decimal SalesTaxTotal { get; set; }
        public decimal TotalAmount { get; set; }
        public string LinkToTxnID { get; set; }  // Links to PO
        public List<QBItemReceiptLine> ExpenseLines { get; set; } = new List<QBItemReceiptLine>();
        public List<QBItemReceiptLine> ItemLines { get; set; } = new List<QBItemReceiptLine>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBItemReceiptLine
    {
        public string TxnLineID { get; set; }
        public string ItemRefListID { get; set; }
        public string ItemRefFullName { get; set; }
        public string Description { get; set; }
        public decimal Quantity { get; set; }
        public string UnitOfMeasure { get; set; }
        public decimal Cost { get; set; }
        public decimal Amount { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ClassRefListID { get; set; }
        public string ClassRefFullName { get; set; }
        public string AccountRefListID { get; set; }
        public string AccountRefFullName { get; set; }
        public string BillableStatus { get; set; }
        public string LotNumber { get; set; }
        public string SerialNumber { get; set; }
    }

    // =================================================================
    // PREFERENCES (Company Settings)
    // =================================================================
    public class QBPreferences
    {
        // Accounting Preferences
        public DateTime FirstMonthFiscalYear { get; set; }
        public DateTime FirstMonthIncomeTaxYear { get; set; }
        public string TaxForm { get; set; }
        public bool IsUsingClassTracking { get; set; }
        public bool IsUsingAuditTrail { get; set; }
        public bool IsRequiringAccounts { get; set; }
        public bool IsUsingInventory { get; set; }
        public bool IsUsingMultiCurrency { get; set; }
        
        // Sales & Customers  
        public string DefaultMarkup { get; set; }
        public bool IsTrackingReimbursedExpensesAsIncome { get; set; }
        public bool IsAutoApplyingPayments { get; set; }
        
        // Bills
        public bool IsAgingFromDueDate { get; set; }
        public bool IsAgingFromTransactionDate { get; set; }
        
        // Sales Tax
        public string DefaultItemSalesTaxRefListID { get; set; }
        public string DefaultItemSalesTaxRefFullName { get; set; }
        public bool IsPayingSalesTax { get; set; }
        
        // Time & Expenses
        public bool IsUsingJobTracking { get; set; }
        public bool IsUsingEstimates { get; set; }
        public bool IsUsingSalesOrders { get; set; }
        public bool IsUsingTimeTracking { get; set; }
        
        // Payroll
        public bool IsUsingPayroll { get; set; }
        
        // Company Info
        public string CompanyName { get; set; }
        public string LegalCompanyName { get; set; }
        public string CompanyType { get; set; }
        public string FederalEmployerID { get; set; }
        public string CompanyAddress { get; set; }
        public string CompanyCity { get; set; }
        public string CompanyState { get; set; }
        public string CompanyPostalCode { get; set; }
        public string CompanyCountry { get; set; }
        public string CompanyPhone { get; set; }
        public string CompanyFax { get; set; }
        public string CompanyEmail { get; set; }
        public string CompanyWebsite { get; set; }
    }

    // =================================================================
    // DATA EXTENSIONS (Custom Fields)
    // =================================================================
    public class QBDataExtension
    {
        public string OwnerID { get; set; }
        public string DataExtName { get; set; }
        public string DataExtValue { get; set; }
        public string DataExtType { get; set; }
        
        // Which entity this extension belongs to
        public string EntityType { get; set; }  // "Customer", "Vendor", "Item", etc.
        public string EntityRefListID { get; set; }
        public string EntityRefFullName { get; set; }
        
        // Definition info
        public string DataExtDefRefListID { get; set; }
        public bool IsRequired { get; set; }
        public bool IsHidden { get; set; }
    }

    // =================================================================
    // DELETED RECORDS (Audit Trail)
    // =================================================================
    public class QBDeletedRecords
    {
        public List<QBDeletedList> DeletedLists { get; set; } = new List<QBDeletedList>();
        public List<QBDeletedTxn> DeletedTransactions { get; set; } = new List<QBDeletedTxn>();
    }

    public class QBDeletedList
    {
        public string ListDelType { get; set; }  // "Account", "Customer", "Vendor", etc.
        public string ListID { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeDeleted { get; set; }
        public string FullName { get; set; }
    }

    public class QBDeletedTxn
    {
        public string TxnDelType { get; set; }  // "Invoice", "Bill", "Check", etc.
        public string TxnID { get; set; }
        public DateTime TimeCreated { get; set; }
        public DateTime TimeDeleted { get; set; }
        public string RefNumber { get; set; }
    }

    // =================================================================
    // AR REFUND CREDIT CARD (Customer Refunds)
    // =================================================================
    public class QBARRefundCreditCard
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string CustomerRefListID { get; set; }
        public string CustomerRefFullName { get; set; }
        public string ARAccountRefListID { get; set; }
        public string ARAccountRefFullName { get; set; }
        public decimal RefundAmount { get; set; }
        public string Memo { get; set; }
        public string PaymentMethodRefListID { get; set; }
        public string PaymentMethodRefFullName { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // BILL PAYMENT CREDIT CARD (Pay Vendors via Credit Card)
    // =================================================================
    public class QBBillPaymentCreditCard
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string VendorRefListID { get; set; }
        public string VendorRefFullName { get; set; }
        public string APAccountRefListID { get; set; }
        public string APAccountRefFullName { get; set; }
        public string CreditCardAccountRefListID { get; set; }
        public string CreditCardAccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        
        // CRITICAL: Track which bills this payment was applied to
        public List<QBLinkedTxn> LinkedTransactions { get; set; } = new List<QBLinkedTxn>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // SALES TAX PAYMENT CHECK (Pay Tax Authorities)
    // =================================================================
    public class QBSalesTaxPaymentCheck
    {
        public string TxnID { get; set; }
        public string RefNumber { get; set; }
        public DateTime TxnDate { get; set; }
        public string PayeeEntityRefListID { get; set; }
        public string PayeeEntityRefFullName { get; set; }
        public string APAccountRefListID { get; set; }
        public string APAccountRefFullName { get; set; }
        public string BankAccountRefListID { get; set; }
        public string BankAccountRefFullName { get; set; }
        public decimal Amount { get; set; }
        public string Memo { get; set; }
        public bool IsToBePrinted { get; set; }
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    // =================================================================
    // SALES TAX GROUP (Multi-jurisdiction Tax)
    // =================================================================
    public class QBSalesTaxGroup
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string Description { get; set; }
        public bool IsActive { get; set; }
        
        // Individual tax items that make up this group
        public List<QBSalesTaxGroupItem> TaxItems { get; set; } = new List<QBSalesTaxGroupItem>();
        
        // Audit fields
        public DateTime TimeCreated { get; set; }
        public DateTime TimeModified { get; set; }
        public string EditSequence { get; set; }
    }

    public class QBSalesTaxGroupItem
    {
        public string ItemSalesTaxRefListID { get; set; }
        public string ItemSalesTaxRefFullName { get; set; }
    }

    // =================================================================
    // REPORT VERIFICATION (Mathematical Proof of Accuracy - THE KILLER FEATURE)
    // =================================================================
    public class QBReportVerification
    {
        public DateTime VerificationDate { get; set; }
        public QBTrialBalance TrialBalance { get; set; }
        public QBBalanceSheet BalanceSheet { get; set; }
        public bool IsBalanced { get; set; }
        public string ValidationMessage { get; set; }
    }

    public class QBTrialBalance
    {
        public DateTime AsOfDate { get; set; }
        public List<QBTrialBalanceLine> Lines { get; set; } = new List<QBTrialBalanceLine>();
        public decimal TotalDebits { get; set; }
        public decimal TotalCredits { get; set; }
    }

    public class QBTrialBalanceLine
    {
        public string AccountName { get; set; }
        public string AccountType { get; set; }
        public decimal DebitBalance { get; set; }
        public decimal CreditBalance { get; set; }
    }

    public class QBBalanceSheet
    {
        public DateTime AsOfDate { get; set; }
        public decimal TotalAssets { get; set; }
        public decimal TotalLiabilities { get; set; }
        public decimal TotalEquity { get; set; }
    }
}
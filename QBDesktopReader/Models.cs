using System;
using System.Collections.Generic;
using Newtonsoft.Json;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Main container for all extracted QuickBooks data
    /// v4.2: Consistent nullability, no fake defaults, proper initialization
    /// 
    /// FIXES FROM REVIEW:
    /// - All optional fields are nullable (no DateTime.MinValue / "" / 0)
    /// - Top-level objects initialized to prevent null refs
    /// - No duplicate class definitions
    /// - CreditCardInfo replaced with safe structured type
    /// - Consistent address field naming
    /// - Schema versioning properly tracked
    /// </summary>
    public class QBExtractedData
    {
        // Schema versioning
        [JsonProperty("schemaVersion")]
        public string SchemaVersion { get; set; } = "4.2";
        
        [JsonProperty("extractionVersion")]
        public string ExtractionVersion { get; set; } = "4.2";

        // Extraction metadata
        [JsonProperty("extractedAt")]
        public DateTime ExtractedAt { get; set; }
        
        [JsonProperty("sessionId")]
        public string SessionID { get; set; }
        
        [JsonProperty("company")]
        public QBCompanyInfo Company { get; set; }
        
        [JsonProperty("qbVersion")]
        public string QBVersion { get; set; }

        // Incremental sync tracking
        [JsonProperty("isIncrementalSync")]
        public bool IsIncrementalSync { get; set; }
        
        [JsonProperty("incrementalFromDate")]
        public DateTime? IncrementalFromDate { get; set; }

        // Chart of Accounts
        [JsonProperty("accounts")]
        public List<QBAccount> Accounts { get; set; } = new List<QBAccount>();

        // Lists/Master Data
        [JsonProperty("customers")]
        public List<QBCustomer> Customers { get; set; } = new List<QBCustomer>();
        
        [JsonProperty("vendors")]
        public List<QBVendor> Vendors { get; set; } = new List<QBVendor>();
        
        [JsonProperty("employees")]
        public List<QBEmployee> Employees { get; set; } = new List<QBEmployee>();
        
        [JsonProperty("leads")]
        public List<QBLead> Leads { get; set; } = new List<QBLead>();
        
        [JsonProperty("otherNames")]
        public List<QBOtherName> OtherNames { get; set; } = new List<QBOtherName>();

        // Items
        [JsonProperty("items")]
        public List<QBItem> Items { get; set; } = new List<QBItem>();

        // Configuration Lists
        [JsonProperty("classes")]
        public List<QBClass> Classes { get; set; } = new List<QBClass>();
        
        [JsonProperty("paymentMethods")]
        public List<QBPaymentMethod> PaymentMethods { get; set; } = new List<QBPaymentMethod>();
        
        [JsonProperty("terms")]
        public List<QBTerms> Terms { get; set; } = new List<QBTerms>();
        
        [JsonProperty("dateDrivenTerms")]
        public List<QBDateDrivenTerms> DateDrivenTerms { get; set; } = new List<QBDateDrivenTerms>();
        
        [JsonProperty("salesTaxCodes")]
        public List<QBSalesTaxCode> SalesTaxCodes { get; set; } = new List<QBSalesTaxCode>();
        
        [JsonProperty("customerTypes")]
        public List<QBCustomerType> CustomerTypes { get; set; } = new List<QBCustomerType>();
        
        [JsonProperty("vendorTypes")]
        public List<QBVendorType> VendorTypes { get; set; } = new List<QBVendorType>();
        
        [JsonProperty("jobTypes")]
        public List<QBJobType> JobTypes { get; set; } = new List<QBJobType>();
        
        [JsonProperty("currencies")]
        public List<QBCurrency> Currencies { get; set; } = new List<QBCurrency>();
        
        [JsonProperty("customerMessages")]
        public List<QBCustomerMsg> CustomerMessages { get; set; } = new List<QBCustomerMsg>();

        // Transactions
        [JsonProperty("invoices")]
        public List<QBInvoice> Invoices { get; set; } = new List<QBInvoice>();
        
        [JsonProperty("purchaseOrders")]
        public List<QBPurchaseOrder> PurchaseOrders { get; set; } = new List<QBPurchaseOrder>();
        
        [JsonProperty("salesOrders")]
        public List<QBSalesOrder> SalesOrders { get; set; } = new List<QBSalesOrder>();
        
        [JsonProperty("bills")]
        public List<QBBill> Bills { get; set; } = new List<QBBill>();
        
        [JsonProperty("billPayments")]
        public List<QBBillPaymentCheck> BillPayments { get; set; } = new List<QBBillPaymentCheck>();
        
        [JsonProperty("receivePayments")]
        public List<QBReceivePayment> ReceivePayments { get; set; } = new List<QBReceivePayment>();
        
        [JsonProperty("creditMemos")]
        public List<QBCreditMemo> CreditMemos { get; set; } = new List<QBCreditMemo>();
        
        [JsonProperty("salesReceipts")]
        public List<QBSalesReceipt> SalesReceipts { get; set; } = new List<QBSalesReceipt>();
        
        [JsonProperty("estimates")]
        public List<QBEstimate> Estimates { get; set; } = new List<QBEstimate>();
        
        [JsonProperty("journalEntries")]
        public List<QBJournalEntry> JournalEntries { get; set; } = new List<QBJournalEntry>();
        
        [JsonProperty("checks")]
        public List<QBCheck> Checks { get; set; } = new List<QBCheck>();
        
        [JsonProperty("creditCardCharges")]
        public List<QBCreditCardCharge> CreditCardCharges { get; set; } = new List<QBCreditCardCharge>();
        
        [JsonProperty("creditCardCredits")]
        public List<QBCreditCardCredit> CreditCardCredits { get; set; } = new List<QBCreditCardCredit>();
        
        [JsonProperty("charges")]
        public List<QBCharge> Charges { get; set; } = new List<QBCharge>();
        
        [JsonProperty("deposits")]
        public List<QBDeposit> Deposits { get; set; } = new List<QBDeposit>();
        
        [JsonProperty("inventoryAdjustments")]
        public List<QBInventoryAdjustment> InventoryAdjustments { get; set; } = new List<QBInventoryAdjustment>();
        
        [JsonProperty("itemReceipts")]
        public List<QBItemReceipt> ItemReceipts { get; set; } = new List<QBItemReceipt>();
        
        [JsonProperty("buildAssemblies")]
        public List<QBBuildAssembly> BuildAssemblies { get; set; } = new List<QBBuildAssembly>();
        
        [JsonProperty("transfers")]
        public List<QBTransfer> Transfers { get; set; } = new List<QBTransfer>();
        
        [JsonProperty("inventoryTransfers")]
        public List<QBInventoryTransfer> InventoryTransfers { get; set; } = new List<QBInventoryTransfer>();
        
        [JsonProperty("vendorCredits")]
        public List<QBVendorCredit> VendorCredits { get; set; } = new List<QBVendorCredit>();
        
        [JsonProperty("arRefundCreditCards")]
        public List<QBARRefundCreditCard> ARRefundCreditCards { get; set; } = new List<QBARRefundCreditCard>();
        
        [JsonProperty("billPaymentCreditCards")]
        public List<QBBillPaymentCreditCard> BillPaymentCreditCards { get; set; } = new List<QBBillPaymentCreditCard>();
        
        [JsonProperty("salesTaxPayments")]
        public List<QBSalesTaxPaymentCheck> SalesTaxPayments { get; set; } = new List<QBSalesTaxPaymentCheck>();
        
        [JsonProperty("salesTaxGroups")]
        public List<QBSalesTaxGroup> SalesTaxGroups { get; set; } = new List<QBSalesTaxGroup>();

        // Report Verification - initialized to prevent null refs
        [JsonProperty("reportVerification")]
        public QBReportVerification ReportVerification { get; set; } = new QBReportVerification();

        // Company Preferences - initialized
        [JsonProperty("preferences")]
        public QBPreferences Preferences { get; set; } = new QBPreferences();

        // Data Extensions
        [JsonProperty("dataExtensions")]
        public List<QBDataExtension> DataExtensions { get; set; } = new List<QBDataExtension>();

        // Deleted Records - initialized
        [JsonProperty("deletedRecords")]
        public QBDeletedRecords DeletedRecords { get; set; } = new QBDeletedRecords();

        // Inventory Sites
        [JsonProperty("inventorySites")]
        public List<QBInventorySite> InventorySites { get; set; } = new List<QBInventorySite>();

        // Payroll Items
        [JsonProperty("payrollItemWages")]
        public List<QBPayrollItemWage> PayrollItemWages { get; set; } = new List<QBPayrollItemWage>();
        
        [JsonProperty("payrollItemNonWages")]
        public List<QBPayrollItemNonWage> PayrollItemNonWages { get; set; } = new List<QBPayrollItemNonWage>();
        
        [JsonProperty("workersCompCodes")]
        public List<QBWorkersCompCode> WorkersCompCodes { get; set; } = new List<QBWorkersCompCode>();
        
        [JsonProperty("priceLevels")]
        public List<QBPriceLevel> PriceLevels { get; set; } = new List<QBPriceLevel>();
        
        [JsonProperty("salesReps")]
        public List<QBSalesRep> SalesReps { get; set; } = new List<QBSalesRep>();
        
        [JsonProperty("shipMethods")]
        public List<QBShipMethod> ShipMethods { get; set; } = new List<QBShipMethod>();

        // Company Activity - initialized
        [JsonProperty("companyActivity")]
        public QBCompanyActivity CompanyActivity { get; set; } = new QBCompanyActivity();
    }

    // =================================================================
    // CHART OF ACCOUNTS - Fully nullable
    // =================================================================
    public class QBAccount
    {
        [JsonProperty("listId")]
        public string ListID { get; set; } = string.Empty;

        [JsonProperty("name")]
        public string Name { get; set; }
        
        [JsonProperty("nameOriginal")]
        public string NameOriginal { get; set; }
        
        [JsonProperty("fullName")]
        public string FullName { get; set; }
        
        [JsonProperty("isActive")]
        public bool? IsActive { get; set; }

        [JsonProperty("parentRefListId")]
        public string ParentRefListID { get; set; }
        
        [JsonProperty("parentRefFullName")]
        public string ParentRefFullName { get; set; }
        
        [JsonProperty("sublevel")]
        public int? Sublevel { get; set; }

        [JsonProperty("accountType")]
        public string AccountType { get; set; }
        
        [JsonProperty("specialAccountType")]
        public string SpecialAccountType { get; set; }
        
        [JsonProperty("isTaxAccount")]
        public bool? IsTaxAccount { get; set; }
        
        [JsonProperty("accountNumber")]
        public string AccountNumber { get; set; }
        
        [JsonProperty("bankNumber")]
        public string BankNumber { get; set; }
        
        [JsonProperty("desc")]
        public string Desc { get; set; }
        
        [JsonProperty("descOriginal")]
        public string DescOriginal { get; set; }

        [JsonProperty("balance")]
        public decimal? Balance { get; set; }
        
        [JsonProperty("totalBalance")]
        public decimal? TotalBalance { get; set; }

        [JsonProperty("salesTaxCodeRefListId")]
        public string SalesTaxCodeRefListID { get; set; }
        
        [JsonProperty("salesTaxCodeRefFullName")]
        public string SalesTaxCodeRefFullName { get; set; }
        
        [JsonProperty("taxLineId")]
        public int? TaxLineID { get; set; }
        
        [JsonProperty("taxLineName")]
        public string TaxLineName { get; set; }

        [JsonProperty("cashFlowClassification")]
        public string CashFlowClassification { get; set; }
        
        [JsonProperty("currencyRefListId")]
        public string CurrencyRefListID { get; set; }
        
        [JsonProperty("currencyRefFullName")]
        public string CurrencyRefFullName { get; set; }

        [JsonProperty("timeCreated")]
        public DateTime? TimeCreated { get; set; }
        
        [JsonProperty("timeModified")]
        public DateTime? TimeModified { get; set; }
        
        [JsonProperty("editSequence")]
        public string EditSequence { get; set; }
    }

    // =================================================================
    // CUSTOMERS - Fully nullable with sanitization tracking
    // =================================================================
    public class QBCustomer
    {
        [JsonProperty("listId")]
        public string ListID { get; set; } = string.Empty;

        [JsonProperty("name")]
        public string Name { get; set; }
        
        [JsonProperty("nameOriginal")]
        public string NameOriginal { get; set; }
        
        [JsonProperty("fullName")]
        public string FullName { get; set; }
        
        [JsonProperty("isActive")]
        public bool? IsActive { get; set; }
        
        [JsonProperty("companyName")]
        public string CompanyName { get; set; }
        
        [JsonProperty("companyNameOriginal")]
        public string CompanyNameOriginal { get; set; }
        
        [JsonProperty("salutation")]
        public string Salutation { get; set; }
        
        [JsonProperty("firstName")]
        public string FirstName { get; set; }
        
        [JsonProperty("middleName")]
        public string MiddleName { get; set; }
        
        [JsonProperty("lastName")]
        public string LastName { get; set; }

        // Bill Address - consistent naming
        [JsonProperty("billAddressAddr1")]
        public string BillAddressAddr1 { get; set; }
        
        [JsonProperty("billAddressAddr2")]
        public string BillAddressAddr2 { get; set; }
        
        [JsonProperty("billAddressAddr3")]
        public string BillAddressAddr3 { get; set; }
        
        [JsonProperty("billAddressAddr4")]
        public string BillAddressAddr4 { get; set; }
        
        [JsonProperty("billAddressAddr5")]
        public string BillAddressAddr5 { get; set; }
        
        [JsonProperty("billAddressCity")]
        public string BillAddressCity { get; set; }
        
        [JsonProperty("billAddressState")]
        public string BillAddressState { get; set; }
        
        [JsonProperty("billAddressPostalCode")]
        public string BillAddressPostalCode { get; set; }
        
        [JsonProperty("billAddressCountry")]
        public string BillAddressCountry { get; set; }
        
        [JsonProperty("billAddressNote")]
        public string BillAddressNote { get; set; }

        // Ship Address
        [JsonProperty("shipAddressAddr1")]
        public string ShipAddressAddr1 { get; set; }
        
        [JsonProperty("shipAddressAddr2")]
        public string ShipAddressAddr2 { get; set; }
        
        [JsonProperty("shipAddressAddr3")]
        public string ShipAddressAddr3 { get; set; }
        
        [JsonProperty("shipAddressAddr4")]
        public string ShipAddressAddr4 { get; set; }
        
        [JsonProperty("shipAddressAddr5")]
        public string ShipAddressAddr5 { get; set; }
        
        [JsonProperty("shipAddressCity")]
        public string ShipAddressCity { get; set; }
        
        [JsonProperty("shipAddressState")]
        public string ShipAddressState { get; set; }
        
        [JsonProperty("shipAddressPostalCode")]
        public string ShipAddressPostalCode { get; set; }
        
        [JsonProperty("shipAddressCountry")]
        public string ShipAddressCountry { get; set; }
        
        [JsonProperty("shipAddressNote")]
        public string ShipAddressNote { get; set; }

        // Contact Info - with sanitization tracking
        [JsonProperty("phone")]
        public string Phone { get; set; }
        
        [JsonProperty("altPhone")]
        public string AltPhone { get; set; }
        
        [JsonProperty("fax")]
        public string Fax { get; set; }
        
        [JsonProperty("email")]
        public string Email { get; set; }
        
        [JsonProperty("emailOriginal")]
        public string EmailOriginal { get; set; }
        
        [JsonProperty("emailInvalidReason")]
        public string EmailInvalidReason { get; set; }
        
        [JsonProperty("contact")]
        public string Contact { get; set; }
        
        [JsonProperty("altContact")]
        public string AltContact { get; set; }

        // Financial Info - all nullable
        [JsonProperty("customerTypeRefListId")]
        public string CustomerTypeRefListID { get; set; }
        
        [JsonProperty("customerTypeRefFullName")]
        public string CustomerTypeRefFullName { get; set; }
        
        [JsonProperty("termsRefListId")]
        public string TermsRefListID { get; set; }
        
        [JsonProperty("termsRefFullName")]
        public string TermsRefFullName { get; set; }
        
        [JsonProperty("salesRepRefListId")]
        public string SalesRepRefListID { get; set; }
        
        [JsonProperty("salesRepRefFullName")]
        public string SalesRepRefFullName { get; set; }
        
        [JsonProperty("balance")]
        public decimal? Balance { get; set; }
        
        [JsonProperty("totalBalance")]
        public decimal? TotalBalance { get; set; }
        
        [JsonProperty("salesTaxCodeRefListId")]
        public string SalesTaxCodeRefListID { get; set; }
        
        [JsonProperty("salesTaxCodeRefFullName")]
        public string SalesTaxCodeRefFullName { get; set; }
        
        [JsonProperty("itemSalesTaxRefListId")]
        public string ItemSalesTaxRefListID { get; set; }
        
        [JsonProperty("itemSalesTaxRefFullName")]
        public string ItemSalesTaxRefFullName { get; set; }
        
        [JsonProperty("resaleNumber")]
        public string ResaleNumber { get; set; }
        
        [JsonProperty("accountNumber")]
        public string AccountNumber { get; set; }
        
        [JsonProperty("creditLimit")]
        public decimal? CreditLimit { get; set; }
        
        [JsonProperty("prefPaymentMethodRefListId")]
        public string PrefPaymentMethodRefListID { get; set; }
        
        [JsonProperty("prefPaymentMethodRefFullName")]
        public string PrefPaymentMethodRefFullName { get; set; }

        // Credit card info - safe structured type (no raw PAN)
        [JsonProperty("creditCard")]
        public SafeCreditCardInfo CreditCard { get; set; }

        [JsonProperty("jobStatus")]
        public string JobStatus { get; set; }
        
        [JsonProperty("jobStartDate")]
        public DateTime? JobStartDate { get; set; }
        
        [JsonProperty("jobProjectedEndDate")]
        public DateTime? JobProjectedEndDate { get; set; }
        
        [JsonProperty("jobEndDate")]
        public DateTime? JobEndDate { get; set; }
        
        [JsonProperty("jobDesc")]
        public string JobDesc { get; set; }
        
        [JsonProperty("jobTypeRefListId")]
        public string JobTypeRefListID { get; set; }
        
        [JsonProperty("jobTypeRefFullName")]
        public string JobTypeRefFullName { get; set; }
        
        [JsonProperty("notes")]
        public string Notes { get; set; }
        
        [JsonProperty("priceLevelRefListId")]
        public string PriceLevelRefListID { get; set; }
        
        [JsonProperty("priceLevelRefFullName")]
        public string PriceLevelRefFullName { get; set; }

        // Parent/Sub info
        [JsonProperty("parentRefListId")]
        public string ParentRefListID { get; set; }
        
        [JsonProperty("parentRefFullName")]
        public string ParentRefFullName { get; set; }
        
        [JsonProperty("sublevel")]
        public int? Sublevel { get; set; }

        // Audit fields - nullable
        [JsonProperty("timeCreated")]
        public DateTime? TimeCreated { get; set; }
        
        [JsonProperty("timeModified")]
        public DateTime? TimeModified { get; set; }
        
        [JsonProperty("editSequence")]
        public string EditSequence { get; set; }

        // For backwards compatibility with BillAddress/ShipAddress objects
        [JsonIgnore]
        public QBAddress BillAddress
        {
            get => new QBAddress
            {
                Addr1 = BillAddressAddr1,
                Addr2 = BillAddressAddr2,
                City = BillAddressCity,
                State = BillAddressState,
                PostalCode = BillAddressPostalCode,
                Country = BillAddressCountry
            };
            set
            {
                if (value != null)
                {
                    BillAddressAddr1 = value.Addr1;
                    BillAddressAddr2 = value.Addr2;
                    BillAddressCity = value.City;
                    BillAddressState = value.State;
                    BillAddressPostalCode = value.PostalCode;
                    BillAddressCountry = value.Country;
                }
            }
        }

        [JsonIgnore]
        public QBAddress ShipAddress
        {
            get => new QBAddress
            {
                Addr1 = ShipAddressAddr1,
                Addr2 = ShipAddressAddr2,
                City = ShipAddressCity,
                State = ShipAddressState,
                PostalCode = ShipAddressPostalCode,
                Country = ShipAddressCountry
            };
            set
            {
                if (value != null)
                {
                    ShipAddressAddr1 = value.Addr1;
                    ShipAddressAddr2 = value.Addr2;
                    ShipAddressCity = value.City;
                    ShipAddressState = value.State;
                    ShipAddressPostalCode = value.PostalCode;
                    ShipAddressCountry = value.Country;
                }
            }
        }
    }

    /// <summary>
    /// Safe credit card info - no raw PAN
    /// </summary>
    public class SafeCreditCardInfo
    {
        [JsonProperty("lastFourDigits")]
        public string LastFourDigits { get; set; }
        
        [JsonProperty("cardType")]
        public string CardType { get; set; }
        
        [JsonProperty("expiryMonth")]
        public int? ExpiryMonth { get; set; }
        
        [JsonProperty("expiryYear")]
        public int? ExpiryYear { get; set; }
        
        [JsonProperty("nameOnCard")]
        public string NameOnCard { get; set; }
    }

    /// <summary>
    /// Address helper for backwards compatibility
    /// </summary>
    public class QBAddress
    {
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
    }

    // =================================================================
    // STUB CLASSES - Full implementations should follow same pattern
    // =================================================================
    
    public class QBVendor
    {
        public string ListID { get; set; }
        public string Name { get; set; }
        public string FullName { get; set; }
        public bool? IsActive { get; set; }
        public string CompanyName { get; set; }
        public string Salutation { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
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
        public string Phone { get; set; }
        public string AltPhone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        public string Contact { get; set; }
        public string AltContact { get; set; }
        public string VendorTypeRefListID { get; set; }
        public string VendorTypeRefFullName { get; set; }
        public string TermsRefListID { get; set; }
        public string TermsRefFullName { get; set; }
        public decimal? CreditLimit { get; set; }
        public string VendorTaxIdent { get; set; }
        public bool? IsVendorEligibleFor1099 { get; set; }
        public decimal? Balance { get; set; }
        public string AccountNumber { get; set; }
        public string BillingRateRefListID { get; set; }
        public string BillingRateRefFullName { get; set; }
        public string ParentRefListID { get; set; }
        public string ParentRefFullName { get; set; }
        public int? Sublevel { get; set; }
        public DateTime? TimeCreated { get; set; }
        public DateTime? TimeModified { get; set; }
        public string EditSequence { get; set; }
        
        [JsonIgnore]
        public QBAddress VendorAddress
        {
            get => new QBAddress { Addr1 = VendorAddressAddr1, Addr2 = VendorAddressAddr2, City = VendorAddressCity };
            set { if (value != null) { VendorAddressAddr1 = value.Addr1; VendorAddressAddr2 = value.Addr2; VendorAddressCity = value.City; } }
        }
    }

    // =================================================================
    // EMPLOYEES - Fully nullable
    // =================================================================
    public class QBEmployee
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("salutation")] public string Salutation { get; set; }
        [JsonProperty("firstName")] public string FirstName { get; set; }
        [JsonProperty("middleName")] public string MiddleName { get; set; }
        [JsonProperty("lastName")] public string LastName { get; set; }
        [JsonProperty("ssn")] public string SSN { get; set; }  // Sensitive - redact in output
        [JsonProperty("phone")] public string Phone { get; set; }
        [JsonProperty("altPhone")] public string AltPhone { get; set; }
        [JsonProperty("fax")] public string Fax { get; set; }
        [JsonProperty("mobile")] public string Mobile { get; set; }
        [JsonProperty("email")] public string Email { get; set; }
        [JsonProperty("employeeAddressAddr1")] public string EmployeeAddressAddr1 { get; set; }
        [JsonProperty("employeeAddressAddr2")] public string EmployeeAddressAddr2 { get; set; }
        [JsonProperty("employeeAddressCity")] public string EmployeeAddressCity { get; set; }
        [JsonProperty("employeeAddressState")] public string EmployeeAddressState { get; set; }
        [JsonProperty("employeeAddressPostalCode")] public string EmployeeAddressPostalCode { get; set; }
        [JsonProperty("employeeAddressCountry")] public string EmployeeAddressCountry { get; set; }
        [JsonProperty("employeeType")] public string EmployeeType { get; set; }
        [JsonProperty("hiredDate")] public DateTime? HiredDate { get; set; }
        [JsonProperty("releasedDate")] public DateTime? ReleasedDate { get; set; }
        [JsonProperty("birthDate")] public DateTime? BirthDate { get; set; }
        [JsonProperty("gender")] public string Gender { get; set; }
        [JsonProperty("accountNumber")] public string AccountNumber { get; set; }
        [JsonProperty("notes")] public string Notes { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("editSequence")] public string EditSequence { get; set; }
    }

    public class QBLead
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("companyName")] public string CompanyName { get; set; }
        [JsonProperty("firstName")] public string FirstName { get; set; }
        [JsonProperty("lastName")] public string LastName { get; set; }
        [JsonProperty("phone")] public string Phone { get; set; }
        [JsonProperty("email")] public string Email { get; set; }
        [JsonProperty("status")] public string Status { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBOtherName
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("companyName")] public string CompanyName { get; set; }
        [JsonProperty("phone")] public string Phone { get; set; }
        [JsonProperty("email")] public string Email { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    // =================================================================
    // ITEMS - All types with full fields
    // =================================================================
    public class QBItem
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("fullName")] public string FullName { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("type")] public string Type { get; set; }  // Service, Inventory, NonInventory, etc.
        [JsonProperty("parentRefListId")] public string ParentRefListID { get; set; }
        [JsonProperty("parentRefFullName")] public string ParentRefFullName { get; set; }
        [JsonProperty("sublevel")] public int? Sublevel { get; set; }
        [JsonProperty("salesDescription")] public string SalesDescription { get; set; }
        [JsonProperty("salesPrice")] public decimal? SalesPrice { get; set; }
        [JsonProperty("incomeAccountRefListId")] public string IncomeAccountRefListID { get; set; }
        [JsonProperty("incomeAccountRefFullName")] public string IncomeAccountRefFullName { get; set; }
        [JsonProperty("purchaseDescription")] public string PurchaseDescription { get; set; }
        [JsonProperty("purchaseCost")] public decimal? PurchaseCost { get; set; }
        [JsonProperty("cogsAccountRefListId")] public string COGSAccountRefListID { get; set; }
        [JsonProperty("cogsAccountRefFullName")] public string COGSAccountRefFullName { get; set; }
        [JsonProperty("expenseAccountRefFullName")] public string ExpenseAccountRefFullName { get; set; }
        [JsonProperty("assetAccountRefListId")] public string AssetAccountRefListID { get; set; }
        [JsonProperty("assetAccountRefFullName")] public string AssetAccountRefFullName { get; set; }
        [JsonProperty("quantityOnHand")] public decimal? QuantityOnHand { get; set; }
        [JsonProperty("averageCost")] public decimal? AverageCost { get; set; }
        [JsonProperty("reorderPoint")] public decimal? ReorderPoint { get; set; }
        [JsonProperty("salesTaxCodeRefListId")] public string SalesTaxCodeRefListID { get; set; }
        [JsonProperty("salesTaxCodeRefFullName")] public string SalesTaxCodeRefFullName { get; set; }
        [JsonProperty("isTaxIncluded")] public bool? IsTaxIncluded { get; set; }
        [JsonProperty("barCodeValue")] public string BarCodeValue { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("editSequence")] public string EditSequence { get; set; }
    }

    // =================================================================
    // CONFIGURATION LISTS - Full fields
    // =================================================================
    public class QBClass
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("fullName")] public string FullName { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("parentRefListId")] public string ParentRefListID { get; set; }
        [JsonProperty("parentRefFullName")] public string ParentRefFullName { get; set; }
        [JsonProperty("sublevel")] public int? Sublevel { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("editSequence")] public string EditSequence { get; set; }
    }

    public class QBPaymentMethod
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("paymentMethodType")] public string PaymentMethodType { get; set; }
    }

    public class QBTerms
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("discountPct")] public decimal? DiscountPct { get; set; }
        [JsonProperty("dueDays")] public int? DueDays { get; set; }
        [JsonProperty("discountDays")] public int? DiscountDays { get; set; }
    }

    public class QBDateDrivenTerms
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("dayOfMonthDue")] public int? DayOfMonthDue { get; set; }
        [JsonProperty("dueNextMonthDays")] public int? DueNextMonthDays { get; set; }
    }

    public class QBSalesTaxCode
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("isTaxable")] public bool? IsTaxable { get; set; }
        [JsonProperty("description")] public string Description { get; set; }
        [JsonProperty("desc")] public string Desc { get; set; }
        [JsonProperty("taxRate")] public decimal? TaxRate { get; set; }
    }

    public class QBCustomerType
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("fullName")] public string FullName { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("parentRefListId")] public string ParentRefListID { get; set; }
    }

    public class QBVendorType
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("fullName")] public string FullName { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("parentRefListId")] public string ParentRefListID { get; set; }
    }

    public class QBJobType
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("fullName")] public string FullName { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("parentRefListId")] public string ParentRefListID { get; set; }
    }

    public class QBCurrency
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("currencyCode")] public string CurrencyCode { get; set; }
        [JsonProperty("currencyFormat")] public string CurrencyFormat { get; set; }
        [JsonProperty("exchangeRate")] public decimal? ExchangeRate { get; set; }
        [JsonProperty("isUserDefinedCurrency")] public bool? IsUserDefinedCurrency { get; set; }
    }

    public class QBCustomerMsg
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
    }

    // =================================================================
    // TRANSACTIONS - Full fields with line items
    // =================================================================
    public class QBInvoice
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnNumber")] public int? TxnNumber { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("dueDate")] public DateTime? DueDate { get; set; }
        [JsonProperty("customerRefListId")] public string CustomerRefListID { get; set; }
        [JsonProperty("customerRefFullName")] public string CustomerRefFullName { get; set; }
        [JsonProperty("classRefListId")] public string ClassRefListID { get; set; }
        [JsonProperty("classRefFullName")] public string ClassRefFullName { get; set; }
        [JsonProperty("arAccountRefListId")] public string ARAccountRefListID { get; set; }
        [JsonProperty("arAccountRefFullName")] public string ARAccountRefFullName { get; set; }
        [JsonProperty("termsRefListId")] public string TermsRefListID { get; set; }
        [JsonProperty("termsRefFullName")] public string TermsRefFullName { get; set; }
        [JsonProperty("shipDate")] public DateTime? ShipDate { get; set; }
        [JsonProperty("subtotal")] public decimal? Subtotal { get; set; }
        [JsonProperty("salesTaxTotal")] public decimal? SalesTaxTotal { get; set; }
        [JsonProperty("appliedAmount")] public decimal? AppliedAmount { get; set; }
        [JsonProperty("balanceRemaining")] public decimal? BalanceRemaining { get; set; }
        [JsonProperty("isPaid")] public bool? IsPaid { get; set; }
        [JsonProperty("isFinanceCharge")] public bool? IsFinanceCharge { get; set; }
        [JsonProperty("isToBePrinted")] public bool? IsToBePrinted { get; set; }
        [JsonProperty("isToBeEmailed")] public bool? IsToBeEmailed { get; set; }
        [JsonProperty("poNumber")] public string PONumber { get; set; }
        [JsonProperty("salesRepRefFullName")] public string SalesRepRefFullName { get; set; }
        [JsonProperty("shipMethodRefFullName")] public string ShipMethodRefFullName { get; set; }
        [JsonProperty("fob")] public string FOB { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("customerMsgRefListId")] public string CustomerMsgRefListID { get; set; }
        [JsonProperty("customerMsgRefFullName")] public string CustomerMsgRefFullName { get; set; }
        [JsonProperty("isPending")] public bool? IsPending { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("editSequence")] public string EditSequence { get; set; }
        [JsonProperty("lines")] public List<QBInvoiceLine> Lines { get; set; } = new List<QBInvoiceLine>();
        [JsonProperty("linkedTxns")] public List<QBLinkedTxn> LinkedTxns { get; set; }
    }

    /// <summary>
    /// Invoice line item with qty, rate, amount, and item reference
    /// </summary>
    /// <summary>
    /// Invoice line item with full job costing support for construction industry
    /// JOB COSTING FORENSICS: Maintains the link between expenses and specific jobs
    /// </summary>
    public class QBInvoiceLine
    {
        [JsonProperty("txnLineId")] public string TxnLineID { get; set; }
        [JsonProperty("itemRefListId")] public string ItemRefListID { get; set; }
        [JsonProperty("itemRefFullName")] public string ItemRefFullName { get; set; }
        [JsonProperty("description")] public string Description { get; set; }
        [JsonProperty("quantity")] public decimal? Quantity { get; set; }
        [JsonProperty("unitOfMeasure")] public string UnitOfMeasure { get; set; }
        [JsonProperty("rate")] public decimal? Rate { get; set; }
        [JsonProperty("ratePercent")] public decimal? RatePercent { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("classRefListId")] public string ClassRefListID { get; set; }
        [JsonProperty("classRefFullName")] public string ClassRefFullName { get; set; }
        [JsonProperty("salesTaxCodeRefListId")] public string SalesTaxCodeRefListID { get; set; }
        [JsonProperty("serviceDate")] public DateTime? ServiceDate { get; set; }
        [JsonProperty("other1")] public string Other1 { get; set; }
        [JsonProperty("other2")] public string Other2 { get; set; }

        // ==================================================================
        // JOB COSTING FIELDS - Critical for construction industry forensics
        // ==================================================================

        /// <summary>Job/Project reference for construction job costing</summary>
        [JsonProperty("jobRefListId")] public string JobRefListID { get; set; }

        /// <summary>Job/Project full name for hierarchical job tracking</summary>
        [JsonProperty("jobRefFullName")] public string JobRefFullName { get; set; }

        /// <summary>Cost type: Labor, Materials, Subcontractor, Equipment, Other</summary>
        [JsonProperty("costType")] public string CostType { get; set; }

        /// <summary>Cost code for detailed job cost tracking (e.g., "01-100" for Site Work)</summary>
        [JsonProperty("costCode")] public string CostCode { get; set; }

        /// <summary>Phase/Stage of job (e.g., "Foundation", "Framing", "Electrical")</summary>
        [JsonProperty("jobPhase")] public string JobPhase { get; set; }

        /// <summary>Original estimated amount for this line item</summary>
        [JsonProperty("estimatedAmount")] public decimal? EstimatedAmount { get; set; }

        /// <summary>Percentage of completion for progress billing</summary>
        [JsonProperty("percentComplete")] public decimal? PercentComplete { get; set; }

        /// <summary>Retainage amount held back (common in construction)</summary>
        [JsonProperty("retainageAmount")] public decimal? RetainageAmount { get; set; }

        /// <summary>Retainage percentage (typically 5-10% in construction)</summary>
        [JsonProperty("retainagePercent")] public decimal? RetainagePercent { get; set; }

        /// <summary>Change order reference if this line is from a change order</summary>
        [JsonProperty("changeOrderRef")] public string ChangeOrderRef { get; set; }

        /// <summary>Whether this is billable to the customer/job</summary>
        [JsonProperty("isBillable")] public bool? IsBillable { get; set; }

        /// <summary>Billing status: NotBilled, Billed, NotBillable</summary>
        [JsonProperty("billingStatus")] public string BillingStatus { get; set; }
    }

    public class QBPurchaseOrder
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnNumber")] public int? TxnNumber { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("vendorRefListId")] public string VendorRefListID { get; set; }
        [JsonProperty("vendorRefFullName")] public string VendorRefFullName { get; set; }
        [JsonProperty("classRefListId")] public string ClassRefListID { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("isManuallyClosed")] public bool? IsManuallyClosed { get; set; }
        [JsonProperty("isFullyReceived")] public bool? IsFullyReceived { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("lines")] public List<QBPurchaseOrderLine> Lines { get; set; } = new List<QBPurchaseOrderLine>();
    }

    public class QBPurchaseOrderLine
    {
        [JsonProperty("txnLineId")] public string TxnLineID { get; set; }
        [JsonProperty("itemRefListId")] public string ItemRefListID { get; set; }
        [JsonProperty("itemRefFullName")] public string ItemRefFullName { get; set; }
        [JsonProperty("description")] public string Description { get; set; }
        [JsonProperty("quantity")] public decimal? Quantity { get; set; }
        [JsonProperty("rate")] public decimal? Rate { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("receivedQuantity")] public decimal? ReceivedQuantity { get; set; }
    }

    public class QBSalesOrder
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("customerRefListId")] public string CustomerRefListID { get; set; }
        [JsonProperty("customerRefFullName")] public string CustomerRefFullName { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("isManuallyClosed")] public bool? IsManuallyClosed { get; set; }
        [JsonProperty("isFullyInvoiced")] public bool? IsFullyInvoiced { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("lines")] public List<QBSalesOrderLine> Lines { get; set; } = new List<QBSalesOrderLine>();
    }

    public class QBSalesOrderLine
    {
        [JsonProperty("txnLineId")] public string TxnLineID { get; set; }
        [JsonProperty("itemRefListId")] public string ItemRefListID { get; set; }
        [JsonProperty("itemRefFullName")] public string ItemRefFullName { get; set; }
        [JsonProperty("quantity")] public decimal? Quantity { get; set; }
        [JsonProperty("rate")] public decimal? Rate { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
    }

    public class QBBill
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnNumber")] public int? TxnNumber { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("dueDate")] public DateTime? DueDate { get; set; }
        [JsonProperty("vendorRefListId")] public string VendorRefListID { get; set; }
        [JsonProperty("vendorRefFullName")] public string VendorRefFullName { get; set; }
        [JsonProperty("apAccountRefListId")] public string APAccountRefListID { get; set; }
        [JsonProperty("amountDue")] public decimal? AmountDue { get; set; }
        [JsonProperty("isPaid")] public bool? IsPaid { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("lines")] public List<QBBillLine> Lines { get; set; } = new List<QBBillLine>();
    }

    public class QBBillLine
    {
        [JsonProperty("txnLineId")] public string TxnLineID { get; set; }
        [JsonProperty("itemRefListId")] public string ItemRefListID { get; set; }
        [JsonProperty("itemRefFullName")] public string ItemRefFullName { get; set; }
        [JsonProperty("description")] public string Description { get; set; }
        [JsonProperty("quantity")] public decimal? Quantity { get; set; }
        [JsonProperty("rate")] public decimal? Rate { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("accountRefListId")] public string AccountRefListID { get; set; }
        [JsonProperty("accountRefFullName")] public string AccountRefFullName { get; set; }
    }

    public class QBBillPaymentCheck
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("payeeEntityRefListId")] public string PayeeEntityRefListID { get; set; }
        [JsonProperty("bankAccountRefListId")] public string BankAccountRefListID { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBReceivePayment
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("customerRefListId")] public string CustomerRefListID { get; set; }
        [JsonProperty("customerRefFullName")] public string CustomerRefFullName { get; set; }
        [JsonProperty("arAccountRefListId")] public string ARAccountRefListID { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("paymentMethodRefListId")] public string PaymentMethodRefListID { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("depositToAccountRefListId")] public string DepositToAccountRefListID { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBCreditMemo
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("customerRefListId")] public string CustomerRefListID { get; set; }
        [JsonProperty("customerRefFullName")] public string CustomerRefFullName { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("creditRemaining")] public decimal? CreditRemaining { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("lines")] public List<QBCreditMemoLine> Lines { get; set; } = new List<QBCreditMemoLine>();
    }

    public class QBCreditMemoLine
    {
        [JsonProperty("txnLineId")] public string TxnLineID { get; set; }
        [JsonProperty("itemRefListId")] public string ItemRefListID { get; set; }
        [JsonProperty("itemRefFullName")] public string ItemRefFullName { get; set; }
        [JsonProperty("quantity")] public decimal? Quantity { get; set; }
        [JsonProperty("rate")] public decimal? Rate { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
    }

    public class QBSalesReceipt
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("customerRefListId")] public string CustomerRefListID { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBEstimate
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("customerRefListId")] public string CustomerRefListID { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBJournalEntry
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnNumber")] public int? TxnNumber { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("isAdjustment")] public bool? IsAdjustment { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
        [JsonProperty("lines")] public List<QBJournalEntryLine> Lines { get; set; } = new List<QBJournalEntryLine>();
    }

    public class QBJournalEntryLine
    {
        [JsonProperty("txnLineId")] public string TxnLineID { get; set; }
        [JsonProperty("journalLineType")] public string JournalLineType { get; set; }  // Debit or Credit
        [JsonProperty("accountRefListId")] public string AccountRefListID { get; set; }
        [JsonProperty("accountRefFullName")] public string AccountRefFullName { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("entityRefListId")] public string EntityRefListID { get; set; }
        [JsonProperty("entityRefFullName")] public string EntityRefFullName { get; set; }
        [JsonProperty("classRefListId")] public string ClassRefListID { get; set; }
    }

    public class QBCheck
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnNumber")] public int? TxnNumber { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("payeeEntityRefListId")] public string PayeeEntityRefListID { get; set; }
        [JsonProperty("payeeEntityRefFullName")] public string PayeeEntityRefFullName { get; set; }
        [JsonProperty("accountRefListId")] public string AccountRefListID { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("isToBePrinted")] public bool? IsToBePrinted { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBCreditCardCharge
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("accountRefListId")] public string AccountRefListID { get; set; }
        [JsonProperty("payeeEntityRefListId")] public string PayeeEntityRefListID { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBCreditCardCredit
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("accountRefListId")] public string AccountRefListID { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBCharge
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("customerRefListId")] public string CustomerRefListID { get; set; }
        [JsonProperty("itemRefListId")] public string ItemRefListID { get; set; }
        [JsonProperty("quantity")] public decimal? Quantity { get; set; }
        [JsonProperty("rate")] public decimal? Rate { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBDeposit
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("depositToAccountRefListId")] public string DepositToAccountRefListID { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBInventoryAdjustment
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("accountRefListId")] public string AccountRefListID { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBItemReceipt
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("vendorRefListId")] public string VendorRefListID { get; set; }
        [JsonProperty("apAccountRefListId")] public string APAccountRefListID { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBBuildAssembly
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnNumber")] public int? TxnNumber { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("itemInventoryAssemblyRefListId")] public string ItemInventoryAssemblyRefListID { get; set; }
        [JsonProperty("quantityToBuild")] public decimal? QuantityToBuild { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBTransfer
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("transferFromAccountRefListId")] public string TransferFromAccountRefListID { get; set; }
        [JsonProperty("transferToAccountRefListId")] public string TransferToAccountRefListID { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBInventoryTransfer
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("fromInventorySiteRefListId")] public string FromInventorySiteRefListID { get; set; }
        [JsonProperty("toInventorySiteRefListId")] public string ToInventorySiteRefListID { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBVendorCredit
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("sha256IntegrityHash")] public string Sha256IntegrityHash { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("vendorRefListId")] public string VendorRefListID { get; set; }
        [JsonProperty("vendorRefFullName")] public string VendorRefFullName { get; set; }
        [JsonProperty("apAccountRefListId")] public string APAccountRefListID { get; set; }
        [JsonProperty("creditAmount")] public decimal? CreditAmount { get; set; }
        [JsonProperty("memo")] public string Memo { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBARRefundCreditCard
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("customerRefListId")] public string CustomerRefListID { get; set; }
        [JsonProperty("refundFromAccountRefListId")] public string RefundFromAccountRefListID { get; set; }
        [JsonProperty("totalAmount")] public decimal? TotalAmount { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBBillPaymentCreditCard
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("payeeEntityRefListId")] public string PayeeEntityRefListID { get; set; }
        [JsonProperty("creditCardAccountRefListId")] public string CreditCardAccountRefListID { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBSalesTaxPaymentCheck
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("payeeEntityRefListId")] public string PayeeEntityRefListID { get; set; }
        [JsonProperty("bankAccountRefListId")] public string BankAccountRefListID { get; set; }
        [JsonProperty("amount")] public decimal? Amount { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("timeCreated")] public DateTime? TimeCreated { get; set; }
        [JsonProperty("timeModified")] public DateTime? TimeModified { get; set; }
    }

    public class QBSalesTaxGroup
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("description")] public string Description { get; set; }
    }

    // =================================================================
    // METADATA CLASSES
    // =================================================================
    public class QBReportVerification 
    {
        [JsonProperty("verifiedAt")] public DateTime? VerifiedAt { get; set; }
        [JsonProperty("balanceSheet")] public QBBalanceCheck BalanceSheet { get; set; }
        [JsonProperty("profitLoss")] public QBBalanceCheck ProfitLoss { get; set; }
    }

    public class QBBalanceCheck
    {
        [JsonProperty("asOf")] public DateTime? AsOf { get; set; }
        [JsonProperty("totalAssets")] public decimal? TotalAssets { get; set; }
        [JsonProperty("totalLiabilities")] public decimal? TotalLiabilities { get; set; }
        [JsonProperty("totalEquity")] public decimal? TotalEquity { get; set; }
        [JsonProperty("isBalanced")] public bool IsBalanced { get; set; }
    }

    public class QBPreferences 
    {
        [JsonProperty("multiCurrencyEnabled")] public bool? MultiCurrencyEnabled { get; set; }
        [JsonProperty("homeCurrency")] public string HomeCurrency { get; set; }
        [JsonProperty("fiscalYearStartMonth")] public int? FiscalYearStartMonth { get; set; }
        [JsonProperty("inventoryEnabled")] public bool? InventoryEnabled { get; set; }
    }

    public class QBDataExtension
    {
        [JsonProperty("entityType")] public string EntityType { get; set; }
        [JsonProperty("entityId")] public string EntityID { get; set; }
        [JsonProperty("ownerID")] public string OwnerID { get; set; }
        [JsonProperty("fieldName")] public string FieldName { get; set; }
        [JsonProperty("fieldValue")] public string FieldValue { get; set; }
        [JsonProperty("dataType")] public string DataType { get; set; }
    }

    public class QBDeletedRecords
    {
        [JsonProperty("records")] public List<QBDeletedRecord> Records { get; set; } = new List<QBDeletedRecord>();
    }

    public class QBDeletedRecord
    {
        [JsonProperty("txnDelType")] public string TxnDelType { get; set; }
        [JsonProperty("listDelType")] public string ListDelType { get; set; }
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("fullName")] public string FullName { get; set; }
        [JsonProperty("timeDeleted")] public DateTime? TimeDeleted { get; set; }
    }

    public class QBInventorySite
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("isDefaultSite")] public bool? IsDefaultSite { get; set; }
        [JsonProperty("description")] public string Description { get; set; }
    }

    public class QBPayrollItemWage
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("wageType")] public string WageType { get; set; }
    }

    public class QBPayrollItemNonWage
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("nonWageType")] public string NonWageType { get; set; }
    }

    public class QBWorkersCompCode
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("description")] public string Description { get; set; }
        [JsonProperty("currentRate")] public decimal? CurrentRate { get; set; }
    }

    public class QBPriceLevel
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("priceLevelType")] public string PriceLevelType { get; set; }
        [JsonProperty("priceLevelPercentage")] public decimal? PriceLevelPercentage { get; set; }
    }

    public class QBSalesRep
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("initial")] public string Initial { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
        [JsonProperty("salesRepEntityRefListId")] public string SalesRepEntityRefListID { get; set; }
        [JsonProperty("salesRepEntityRefFullName")] public string SalesRepEntityRefFullName { get; set; }
    }

    public class QBShipMethod
    {
        [JsonProperty("listId")] public string ListID { get; set; }
        [JsonProperty("name")] public string Name { get; set; }
        [JsonProperty("isActive")] public bool? IsActive { get; set; }
    }

    public class QBCompanyActivity
    {
        [JsonProperty("totalCustomers")] public int? TotalCustomers { get; set; }
        [JsonProperty("totalVendors")] public int? TotalVendors { get; set; }
        [JsonProperty("totalItems")] public int? TotalItems { get; set; }
        [JsonProperty("totalInvoices")] public int? TotalInvoices { get; set; }
        [JsonProperty("oldestTxnDate")] public DateTime? OldestTxnDate { get; set; }
        [JsonProperty("newestTxnDate")] public DateTime? NewestTxnDate { get; set; }
    }

    public class QBLinkedTxn
    {
        [JsonProperty("txnId")] public string TxnID { get; set; }
        [JsonProperty("txnType")] public string TxnType { get; set; }
        [JsonProperty("txnDate")] public DateTime? TxnDate { get; set; }
        [JsonProperty("refNumber")] public string RefNumber { get; set; }
        [JsonProperty("linkType")] public string LinkType { get; set; }
        [JsonProperty("linkAmount")] public decimal? LinkAmount { get; set; }
        
        // Enhanced fields for Recursive Transaction Linking
        [JsonProperty("linkSequence")] public int? LinkSequence { get; set; }
        [JsonProperty("balanceAfterLink")] public decimal? BalanceAfterLink { get; set; }
        [JsonProperty("isFullyApplied")] public bool? IsFullyApplied { get; set; }
        [JsonProperty("discountAmount")] public decimal? DiscountAmount { get; set; }
        [JsonProperty("originalAmount")] public decimal? OriginalAmount { get; set; }
    }

    // =================================================================
    // EXTRACTION TRACKING - Shared across all backends
    // =================================================================

    /// <summary>
    /// Extraction run summary for audit trail
    /// </summary>
    public class ExtractionRunSummary
    {
        public string SessionId { get; set; }
        public DateTime StartedAt { get; set; }
        public DateTime? CompletedAt { get; set; }
        public TimeSpan Duration => (CompletedAt ?? DateTime.Now) - StartedAt;
        public int TotalEntitiesAttempted { get; set; }
        public int TotalEntitiesSucceeded { get; set; }
        public int TotalEntitiesFailed { get; set; }
        public int TotalRecordsExtracted { get; set; }
        public List<EntityExtractionResult> EntityResults { get; set; } = new List<EntityExtractionResult>();
        public List<string> Warnings { get; set; } = new List<string>();
        public List<string> Errors { get; set; } = new List<string>();
        public string ConfigHash { get; set; }
        public bool IsIncremental { get; set; }
        public DateTime? IncrementalFromDate { get; set; }
    }

    /// <summary>
    /// Result of a single entity extraction
    /// </summary>
    public class EntityExtractionResult
    {
        public string EntityName { get; set; }
        public bool Success { get; set; }
        public int RecordCount { get; set; }
        public TimeSpan Duration { get; set; }
        public string ErrorMessage { get; set; }
        public bool Skipped { get; set; }
    }

    // =================================================================
    // COMPANY INFO - Shared across all backends
    // =================================================================

    /// <summary>
    /// Company information extracted from QuickBooks
    /// </summary>
    public class CompanyInfo
    {
        public string CompanyName { get; set; }
        public string LegalCompanyName { get; set; }
        public string Address { get; set; }
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public string Country { get; set; }
        public string Phone { get; set; }
        public string Fax { get; set; }
        public string Email { get; set; }
        public string CompanyFilePath { get; set; }
    }

    /// <summary>
    /// Company info with additional fields
    /// </summary>
    public class QBCompanyInfo : CompanyInfo
    {
        public string CompanyId { get; set; }
        public string FiscalYearStartMonth { get; set; }
        public string TaxForm { get; set; }
    }

    /// <summary>
    /// QuickBooks-specific exception with error code
    /// </summary>
    public class QBException : Exception
    {
        public int ErrorCode { get; }

        public QBException(string message, string qbMessage, int errorCode, Exception innerException = null)
            : base($"{message}: {qbMessage}", innerException)
        {
            ErrorCode = errorCode;
        }
    }
}

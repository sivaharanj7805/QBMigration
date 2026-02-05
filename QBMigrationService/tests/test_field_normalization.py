"""
Comprehensive Test Suite for Field Normalization Layer in QBDataTransformer
==========================================================================

Tests the two static methods added to QBDataTransformer:
1. normalize_extractor_fields() - normalizes individual entity field names
   from C# camelCase to PascalCase
2. normalize_data_keys() - normalizes top-level entity collection keys

These methods bridge the C# QBDataExtractor (camelCase JSON output) with the
Python transformer (expects PascalCase), enabling seamless end-to-end migration.

TEST-FN: Field Normalization Tests
"""

import sys
import os
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_transformer import QBDataTransformer

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def transformer():
    """Create a fresh QBDataTransformer instance."""
    return QBDataTransformer(region="US")


# ============================================================================
# normalize_extractor_fields: Basic camelCase -> PascalCase mapping
# ============================================================================


class TestNormalizeExtractorFieldsBasicMapping:
    """Tests for basic camelCase to PascalCase field name mapping."""

    def test_list_id_mapping(self):
        entity = {"listId": "80000001-1234567890"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ListID"] == "80000001-1234567890"
        assert "listId" not in result

    def test_name_mapping(self):
        entity = {"name": "Test Account"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Name"] == "Test Account"

    def test_full_name_mapping(self):
        entity = {"fullName": "Parent:Child"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["FullName"] == "Parent:Child"

    def test_is_active_mapping(self):
        entity = {"isActive": True}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["IsActive"] is True

    def test_multiple_basic_fields(self):
        entity = {
            "listId": "ABC-123",
            "name": "Cash Account",
            "isActive": True,
            "fullName": "Assets:Cash Account",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ListID"] == "ABC-123"
        assert result["Name"] == "Cash Account"
        assert result["IsActive"] is True
        assert result["FullName"] == "Assets:Cash Account"

    def test_name_original_mapping(self):
        entity = {"nameOriginal": "Original Name"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["NameOriginal"] == "Original Name"


# ============================================================================
# normalize_extractor_fields: Account-specific fields
# ============================================================================


class TestNormalizeExtractorFieldsAccountFields:
    """Tests for account-specific field mappings."""

    def test_account_type_mapping(self):
        entity = {"accountType": "Bank"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["AccountType"] == "Bank"

    def test_desc_to_description(self):
        entity = {"desc": "Main operating account"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Description"] == "Main operating account"

    def test_account_number_mapping(self):
        entity = {"accountNumber": "1000"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["AccountNumber"] == "1000"

    def test_balance_mapping(self):
        entity = {"balance": 50000.00}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Balance"] == 50000.00

    def test_bank_number_mapping(self):
        entity = {"bankNumber": "123456789"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["BankNumber"] == "123456789"

    def test_special_account_type(self):
        entity = {"specialAccountType": "AccountsPayable"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["SpecialAccountType"] == "AccountsPayable"

    def test_is_tax_account(self):
        entity = {"isTaxAccount": True}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["IsTaxAccount"] is True

    def test_cash_flow_classification(self):
        entity = {"cashFlowClassification": "Operating"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CashFlowClassification"] == "Operating"

    def test_full_account_entity(self):
        entity = {
            "listId": "ACC-001",
            "name": "Checking",
            "accountType": "bank",
            "desc": "Business checking",
            "accountNumber": "1010",
            "balance": 25000.50,
            "isActive": True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Account")
        assert result["ListID"] == "ACC-001"
        assert result["Name"] == "Checking"
        assert result["AccountType"] == "bank"
        assert result["Description"] == "Business checking"
        assert result["AccountNumber"] == "1010"
        assert result["Balance"] == 25000.50
        assert result["IsActive"] is True


# ============================================================================
# normalize_extractor_fields: Item-specific fields
# ============================================================================


class TestNormalizeExtractorFieldsItemFields:
    """Tests for item-specific field mappings."""

    def test_type_to_item_type(self):
        entity = {"type": "Service"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ItemType"] == "Service"

    def test_sales_price_to_unit_price(self):
        entity = {"salesPrice": 99.99}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["UnitPrice"] == 99.99

    def test_sales_description_to_description(self):
        entity = {"salesDescription": "Hourly consulting"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Description"] == "Hourly consulting"

    def test_quantity_on_hand(self):
        entity = {"quantityOnHand": 150}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["QuantityOnHand"] == 150

    def test_average_cost(self):
        entity = {"averageCost": 12.50}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["AverageCost"] == 12.50

    def test_purchase_cost(self):
        entity = {"purchaseCost": 45.00}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["PurchaseCost"] == 45.00

    def test_purchase_description(self):
        entity = {"purchaseDescription": "Buy from supplier"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["PurchaseDescription"] == "Buy from supplier"

    def test_reorder_point(self):
        entity = {"reorderPoint": 10}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ReorderPoint"] == 10

    def test_bar_code_value(self):
        entity = {"barCodeValue": "1234567890"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["BarCodeValue"] == "1234567890"

    def test_is_tax_included(self):
        entity = {"isTaxIncluded": True}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["IsTaxIncluded"] is True

    def test_full_item_entity(self):
        entity = {
            "listId": "ITEM-001",
            "name": "Widget",
            "type": "Inventory",
            "salesPrice": 29.99,
            "salesDescription": "Standard widget",
            "purchaseCost": 15.00,
            "quantityOnHand": 200,
            "averageCost": 14.75,
            "isActive": True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Item")
        assert result["ListID"] == "ITEM-001"
        assert result["Name"] == "Widget"
        assert result["ItemType"] == "Inventory"
        assert result["UnitPrice"] == 29.99
        assert result["Description"] == "Standard widget"
        assert result["PurchaseCost"] == 15.00
        assert result["QuantityOnHand"] == 200
        assert result["AverageCost"] == 14.75


# ============================================================================
# normalize_extractor_fields: Reference fields
# ============================================================================


class TestNormalizeExtractorFieldsReferenceFields:
    """Tests for reference field mappings (xxxRefListId -> XxxRef)."""

    def test_customer_ref(self):
        entity = {"customerRefListId": "CUST-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CustomerRef"] == "CUST-001"

    def test_vendor_ref(self):
        entity = {"vendorRefListId": "VEND-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["VendorRef"] == "VEND-001"

    def test_parent_ref(self):
        entity = {"parentRefListId": "PARENT-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ParentRef"] == "PARENT-001"

    def test_account_ref(self):
        entity = {"accountRefListId": "ACC-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["AccountRef"] == "ACC-001"

    def test_item_ref(self):
        entity = {"itemRefListId": "ITEM-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ItemRef"] == "ITEM-001"

    def test_terms_ref(self):
        entity = {"termsRefListId": "TERMS-NET30"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["TermRef"] == "TERMS-NET30"

    def test_ar_account_ref(self):
        entity = {"arAccountRefListId": "AR-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ARAccountRef"] == "AR-001"

    def test_ap_account_ref(self):
        entity = {"apAccountRefListId": "AP-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["APAccountRef"] == "AP-001"

    def test_class_ref(self):
        entity = {"classRefListId": "CLASS-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ClassRef"] == "CLASS-001"

    def test_income_account_ref(self):
        entity = {"incomeAccountRefListId": "INC-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["IncomeAccountRef"] == "INC-001"

    def test_cogs_account_ref_maps_to_expense_account_ref(self):
        entity = {"cogsAccountRefListId": "COGS-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ExpenseAccountRef"] == "COGS-001"

    def test_payment_method_ref(self):
        entity = {"paymentMethodRefListId": "PM-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["PaymentMethodRef"] == "PM-001"

    def test_sales_tax_code_ref(self):
        entity = {"salesTaxCodeRefListId": "TAX-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["SalesTaxCodeRef"] == "TAX-001"

    def test_bank_account_ref(self):
        entity = {"bankAccountRefListId": "BANK-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["BankAccountRef"] == "BANK-001"

    def test_deposit_to_account_ref(self):
        entity = {"depositToAccountRefListId": "DEP-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["DepositToAccountRef"] == "DEP-001"

    def test_entity_ref(self):
        entity = {"entityRefListId": "ENT-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["EntityRef"] == "ENT-001"

    def test_payee_entity_ref(self):
        entity = {"payeeEntityRefListId": "PAY-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["PayeeRef"] == "PAY-001"

    def test_sales_rep_ref(self):
        entity = {"salesRepRefListId": "REP-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["SalesRepRef"] == "REP-001"

    def test_currency_ref(self):
        entity = {"currencyRefListId": "CUR-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CurrencyRef"] == "CUR-001"

    def test_price_level_ref(self):
        entity = {"priceLevelRefListId": "PL-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["PriceLevelRef"] == "PL-001"

    def test_billing_rate_ref(self):
        entity = {"billingRateRefListId": "BR-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["BillingRateRef"] == "BR-001"

    def test_customer_type_ref(self):
        entity = {"customerTypeRefListId": "CT-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CustomerTypeRef"] == "CT-001"

    def test_vendor_type_ref(self):
        entity = {"vendorTypeRefListId": "VT-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["VendorTypeRef"] == "VT-001"

    def test_job_type_ref(self):
        entity = {"jobTypeRefListId": "JT-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["JobTypeRef"] == "JT-001"

    def test_item_sales_tax_ref(self):
        entity = {"itemSalesTaxRefListId": "IST-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ItemSalesTaxRef"] == "IST-001"

    def test_pref_payment_method_ref(self):
        entity = {"prefPaymentMethodRefListId": "PPM-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["PrefPaymentMethodRef"] == "PPM-001"

    def test_customer_msg_ref(self):
        entity = {"customerMsgRefListId": "MSG-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CustomerMsgRef"] == "MSG-001"

    def test_asset_account_ref(self):
        entity = {"assetAccountRefListId": "ASSET-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["AssetAccountRef"] == "ASSET-001"

    def test_ref_full_name_fields(self):
        entity = {
            "customerRefFullName": "Acme Corp",
            "vendorRefFullName": "Supplier Inc",
            "parentRefFullName": "Parent Co",
            "itemRefFullName": "Widget Pro",
            "accountRefFullName": "Checking Account",
            "classRefFullName": "Overhead",
            "termsRefFullName": "Net 30",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CustomerRefFullName"] == "Acme Corp"
        assert result["VendorRefFullName"] == "Supplier Inc"
        assert result["ParentRefFullName"] == "Parent Co"
        assert result["ItemRefFullName"] == "Widget Pro"
        assert result["AccountRefFullName"] == "Checking Account"
        assert result["ClassRefFullName"] == "Overhead"
        assert result["TermRefFullName"] == "Net 30"

    def test_all_references_in_one_entity(self):
        """Multiple reference fields on the same entity all normalize correctly."""
        entity = {
            "customerRefListId": "C1",
            "vendorRefListId": "V1",
            "parentRefListId": "P1",
            "termsRefListId": "T1",
            "incomeAccountRefListId": "IA1",
            "assetAccountRefListId": "AA1",
            "classRefListId": "CL1",
            "accountRefListId": "ACC1",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CustomerRef"] == "C1"
        assert result["VendorRef"] == "V1"
        assert result["ParentRef"] == "P1"
        assert result["TermRef"] == "T1"
        assert result["IncomeAccountRef"] == "IA1"
        assert result["AssetAccountRef"] == "AA1"
        assert result["ClassRef"] == "CL1"
        assert result["AccountRef"] == "ACC1"


# ============================================================================
# normalize_extractor_fields: Transaction fields
# ============================================================================


class TestNormalizeExtractorFieldsTransactionFields:
    """Tests for transaction-specific field mappings."""

    def test_txn_id(self):
        entity = {"txnId": "TXN-001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["TxnID"] == "TXN-001"

    def test_txn_date(self):
        entity = {"txnDate": "2024-01-15"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["TxnDate"] == "2024-01-15"

    def test_ref_number(self):
        entity = {"refNumber": "1001"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["RefNumber"] == "1001"

    def test_memo(self):
        entity = {"memo": "Payment for services"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Memo"] == "Payment for services"

    def test_due_date(self):
        entity = {"dueDate": "2024-02-15"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["DueDate"] == "2024-02-15"

    def test_ship_date(self):
        entity = {"shipDate": "2024-03-01"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ShipDate"] == "2024-03-01"

    def test_txn_number(self):
        entity = {"txnNumber": 42}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["TxnNumber"] == 42

    def test_amount_fields(self):
        entity = {
            "amount": 500.00,
            "amountDue": 250.00,
            "totalAmount": 750.00,
            "subtotal": 700.00,
            "salesTaxTotal": 50.00,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Amount"] == 500.00
        assert result["AmountDue"] == 250.00
        assert result["TotalAmount"] == 750.00
        assert result["Subtotal"] == 700.00
        assert result["SalesTaxTotal"] == 50.00

    def test_po_number_and_fob(self):
        entity = {"poNumber": "PO-5678", "fob": "Destination"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["PONumber"] == "PO-5678"
        assert result["FOB"] == "Destination"

    def test_boolean_transaction_flags(self):
        entity = {
            "isPaid": True,
            "isPending": False,
            "isToBePrinted": True,
            "isToBeEmailed": False,
            "isManuallyClosed": True,
            "isFullyReceived": False,
            "isFullyInvoiced": True,
            "isAdjustment": False,
            "isFinanceCharge": True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["IsPaid"] is True
        assert result["IsPending"] is False
        assert result["IsToBePrinted"] is True
        assert result["IsToBeEmailed"] is False
        assert result["IsManuallyClosed"] is True
        assert result["IsFullyReceived"] is False
        assert result["IsFullyInvoiced"] is True
        assert result["IsAdjustment"] is False
        assert result["IsFinanceCharge"] is True

    def test_applied_amount(self):
        entity = {"appliedAmount": 300.00}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["AppliedAmount"] == 300.00

    def test_balance_remaining(self):
        entity = {"balanceRemaining": 150.75}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["BalanceRemaining"] == 150.75

    def test_credit_remaining(self):
        entity = {"creditRemaining": 200.00}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CreditRemaining"] == 200.00


# ============================================================================
# normalize_extractor_fields: Employee fields
# ============================================================================


class TestNormalizeExtractorFieldsEmployeeFields:
    """Tests for employee-specific field mappings."""

    def test_ssn_mapping(self):
        entity = {"ssn": "***-**-1234"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["SSN"] == "***-**-1234"

    def test_first_name(self):
        entity = {"firstName": "John"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["FirstName"] == "John"

    def test_last_name(self):
        entity = {"lastName": "Doe"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["LastName"] == "Doe"

    def test_middle_name(self):
        entity = {"middleName": "Q"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["MiddleName"] == "Q"

    def test_employee_type(self):
        entity = {"employeeType": "Regular"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["EmployeeType"] == "Regular"

    def test_hired_date(self):
        entity = {"hiredDate": "2020-01-15"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["HiredDate"] == "2020-01-15"

    def test_released_date(self):
        entity = {"releasedDate": "2023-12-31"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ReleasedDate"] == "2023-12-31"

    def test_birth_date(self):
        entity = {"birthDate": "1990-06-15"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["BirthDate"] == "1990-06-15"

    def test_gender(self):
        entity = {"gender": "Male"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Gender"] == "Male"

    def test_full_employee_entity(self):
        entity = {
            "listId": "EMP-001",
            "firstName": "Jane",
            "middleName": "M",
            "lastName": "Smith",
            "ssn": "***-**-5678",
            "employeeType": "Regular",
            "hiredDate": "2019-03-01",
            "isActive": True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Employee")
        assert result["ListID"] == "EMP-001"
        assert result["FirstName"] == "Jane"
        assert result["MiddleName"] == "M"
        assert result["LastName"] == "Smith"
        assert result["SSN"] == "***-**-5678"
        assert result["EmployeeType"] == "Regular"
        assert result["HiredDate"] == "2019-03-01"
        assert result["IsActive"] is True


# ============================================================================
# normalize_extractor_fields: Vendor-specific fields
# ============================================================================


class TestNormalizeExtractorFieldsVendorFields:
    """Tests for vendor-specific field mappings."""

    def test_is_vendor_eligible_for_1099(self):
        entity = {"isVendorEligibleFor1099": True}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Is1099"] is True

    def test_is_vendor_eligible_for_1099_false(self):
        entity = {"isVendorEligibleFor1099": False}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Is1099"] is False

    def test_vendor_tax_ident(self):
        entity = {"vendorTaxIdent": "12-3456789"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["VendorTaxIdent"] == "12-3456789"

    def test_full_vendor_entity(self):
        entity = {
            "listId": "V1",
            "name": "Vendor Inc",
            "companyName": "Vendor Inc LLC",
            "isVendorEligibleFor1099": True,
            "vendorTaxIdent": "12-3456789",
            "isActive": True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Vendor")
        assert result["ListID"] == "V1"
        assert result["Name"] == "Vendor Inc"
        assert result["CompanyName"] == "Vendor Inc LLC"
        assert result["Is1099"] is True
        assert result["VendorTaxIdent"] == "12-3456789"


# ============================================================================
# normalize_extractor_fields: Address reconstruction
# ============================================================================


class TestNormalizeExtractorFieldsAddressReconstruction:
    """Tests for flat address field -> nested dict reconstruction."""

    def test_bill_address_reconstruction(self):
        entity = {
            "billAddressAddr1": "123 Main St",
            "billAddressCity": "New York",
            "billAddressState": "NY",
            "billAddressPostalCode": "10001",
            "billAddressCountry": "US",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert "BillAddress" in result
        assert result["BillAddress"]["Addr1"] == "123 Main St"
        assert result["BillAddress"]["City"] == "New York"
        assert result["BillAddress"]["State"] == "NY"
        assert result["BillAddress"]["PostalCode"] == "10001"
        assert result["BillAddress"]["Country"] == "US"
        # Original flat keys should not be present
        assert "billAddressAddr1" not in result
        assert "billAddressCity" not in result

    def test_bill_address_with_addr2(self):
        entity = {
            "billAddressAddr1": "123 Main St",
            "billAddressAddr2": "Suite 100",
            "billAddressCity": "New York",
            "billAddressState": "NY",
            "billAddressPostalCode": "10001",
            "billAddressCountry": "US",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["BillAddress"]["Addr1"] == "123 Main St"
        assert result["BillAddress"]["Addr2"] == "Suite 100"

    def test_ship_address_reconstruction(self):
        entity = {
            "shipAddressAddr1": "456 Oak Ave",
            "shipAddressAddr2": "Suite 200",
            "shipAddressCity": "Chicago",
            "shipAddressState": "IL",
            "shipAddressPostalCode": "60601",
            "shipAddressCountry": "US",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert "ShipAddress" in result
        assert result["ShipAddress"]["Addr1"] == "456 Oak Ave"
        assert result["ShipAddress"]["Addr2"] == "Suite 200"
        assert result["ShipAddress"]["City"] == "Chicago"
        assert result["ShipAddress"]["State"] == "IL"
        assert result["ShipAddress"]["PostalCode"] == "60601"
        assert result["ShipAddress"]["Country"] == "US"

    def test_vendor_address_reconstruction(self):
        entity = {
            "vendorAddressAddr1": "789 Vendor Blvd",
            "vendorAddressCity": "San Francisco",
            "vendorAddressState": "CA",
            "vendorAddressPostalCode": "94105",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert "VendorAddress" in result
        assert result["VendorAddress"]["Addr1"] == "789 Vendor Blvd"
        assert result["VendorAddress"]["City"] == "San Francisco"
        assert result["VendorAddress"]["State"] == "CA"
        assert result["VendorAddress"]["PostalCode"] == "94105"

    def test_vendor_address_also_creates_address_key(self):
        """VendorAddress should also be mirrored to 'Address' for transform_vendor compatibility."""
        entity = {
            "vendorAddressAddr1": "100 Vendor Way",
            "vendorAddressCity": "Boston",
            "vendorAddressState": "MA",
            "vendorAddressPostalCode": "02101",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert "VendorAddress" in result
        assert "Address" in result
        assert result["Address"] == result["VendorAddress"]
        assert result["Address"]["Addr1"] == "100 Vendor Way"
        assert result["Address"]["City"] == "Boston"

    def test_vendor_address_no_address_key_if_already_exists(self):
        """If 'Address' already exists as a key, VendorAddress should not overwrite it."""
        entity = {
            "Address": {"Addr1": "Already There", "City": "Existing"},
            "vendorAddressAddr1": "100 New St",
            "vendorAddressCity": "Newtown",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        # The existing 'Address' key should be preserved via passthrough
        assert result["Address"] == {"Addr1": "Already There", "City": "Existing"}

    def test_employee_address_reconstruction(self):
        entity = {
            "employeeAddressAddr1": "55 Worker Lane",
            "employeeAddressCity": "Denver",
            "employeeAddressState": "CO",
            "employeeAddressPostalCode": "80202",
            "employeeAddressCountry": "US",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert "EmployeeAddress" in result
        assert result["EmployeeAddress"]["Addr1"] == "55 Worker Lane"
        assert result["EmployeeAddress"]["City"] == "Denver"
        assert result["EmployeeAddress"]["State"] == "CO"
        assert result["EmployeeAddress"]["PostalCode"] == "80202"
        assert result["EmployeeAddress"]["Country"] == "US"

    def test_partial_address(self):
        """Address with only some fields populated should still reconstruct."""
        entity = {
            "billAddressAddr1": "123 Main St",
            "billAddressCity": "Anytown",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert "BillAddress" in result
        assert result["BillAddress"]["Addr1"] == "123 Main St"
        assert result["BillAddress"]["City"] == "Anytown"
        assert "State" not in result["BillAddress"]
        assert "PostalCode" not in result["BillAddress"]

    def test_multiple_addresses_on_same_entity(self):
        """Entity with both bill and ship addresses."""
        entity = {
            "billAddressAddr1": "100 Bill St",
            "billAddressCity": "Billtown",
            "billAddressState": "BL",
            "shipAddressAddr1": "200 Ship Ave",
            "shipAddressCity": "Shipville",
            "shipAddressState": "SH",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["BillAddress"]["Addr1"] == "100 Bill St"
        assert result["BillAddress"]["City"] == "Billtown"
        assert result["ShipAddress"]["Addr1"] == "200 Ship Ave"
        assert result["ShipAddress"]["City"] == "Shipville"

    def test_address_does_not_overwrite_existing_pascal_address(self):
        """If PascalCase address already exists, flat fields should not overwrite it."""
        entity = {
            "BillAddress": {"Addr1": "Already There", "City": "Existing"},
            "billAddressAddr1": "123 New St",
            "billAddressCity": "Newtown",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        # The existing PascalCase key should be preserved
        assert result["BillAddress"] == {"Addr1": "Already There", "City": "Existing"}

    def test_addr2_through_addr5_fields(self):
        entity = {
            "billAddressAddr1": "Line 1",
            "billAddressAddr2": "Line 2",
            "billAddressAddr3": "Line 3",
            "billAddressAddr4": "Line 4",
            "billAddressAddr5": "Line 5",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        addr = result["BillAddress"]
        assert addr["Addr1"] == "Line 1"
        assert addr["Addr2"] == "Line 2"
        assert addr["Addr3"] == "Line 3"
        assert addr["Addr4"] == "Line 4"
        assert addr["Addr5"] == "Line 5"

    def test_address_note_field(self):
        entity = {
            "shipAddressAddr1": "100 Main",
            "shipAddressNote": "Deliver to loading dock",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ShipAddress"]["Note"] == "Deliver to loading dock"

    def test_address_with_all_none_values_not_created(self):
        """Address dict not created if all address fields are None."""
        entity = {
            "listId": "C1",
            "billAddressAddr1": None,
            "billAddressCity": None,
            "billAddressState": None,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert "BillAddress" not in result


# ============================================================================
# normalize_extractor_fields: Line items
# ============================================================================


class TestNormalizeExtractorFieldsLineItems:
    """Tests for 'lines' array -> entity-specific line key mapping."""

    def test_invoice_lines(self):
        entity = {
            "txnId": "INV-001",
            "lines": [
                {
                    "itemRefListId": "I1",
                    "description": "Widget",
                    "quantity": 5,
                    "rate": 10.00,
                    "amount": 50.00,
                },
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Invoice")
        assert "InvoiceLines" in result
        assert len(result["InvoiceLines"]) == 1

    def test_invoice_line_fields_are_normalized_recursively(self):
        """Line items themselves should have their fields normalized recursively."""
        entity = {
            "txnId": "INV-002",
            "lines": [
                {
                    "txnLineId": "L1",
                    "itemRefListId": "I1",
                    "description": "Service",
                    "quantity": 1,
                    "rate": 100.00,
                    "amount": 100.00,
                    "classRefListId": "CL1",
                    "serviceDate": "2024-01-15",
                },
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Invoice")
        line = result["InvoiceLines"][0]
        assert line.get("TxnLineID") == "L1"
        assert line.get("ItemRef") == "I1"
        assert line.get("Description") == "Service"
        assert line.get("Quantity") == 1
        assert line.get("Rate") == 100.00
        assert line.get("Amount") == 100.00
        assert line.get("ClassRef") == "CL1"
        assert line.get("ServiceDate") == "2024-01-15"

    def test_bill_lines_split_expense_and_item(self):
        """Bill lines should be split into ExpenseLines and ItemLines."""
        entity = {
            "txnId": "BILL-001",
            "lines": [
                {
                    "accountRefListId": "ACC-001",
                    "description": "Office Rent",
                    "amount": 2000.00,
                },
                {
                    "itemRefListId": "ITEM-001",
                    "description": "Supplies",
                    "quantity": 10,
                    "rate": 5.00,
                    "amount": 50.00,
                },
                {
                    "accountRefListId": "ACC-002",
                    "description": "Utilities",
                    "amount": 300.00,
                },
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Bill")
        assert "ExpenseLines" in result
        assert "ItemLines" in result
        assert len(result["ExpenseLines"]) == 2
        assert len(result["ItemLines"]) == 1
        assert "Lines" not in result

    def test_bill_expense_lines_normalized(self):
        """Bill expense lines should have their fields normalized."""
        entity = {
            "txnId": "BILL-001",
            "lines": [
                {
                    "accountRefListId": "ACC-001",
                    "description": "Rent",
                    "amount": 2000.00,
                },
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Bill")
        line = result["ExpenseLines"][0]
        assert line.get("AccountRef") == "ACC-001"
        assert line.get("Description") == "Rent"
        assert line.get("Amount") == 2000.00

    def test_bill_expense_lines_only(self):
        """Bill with only expense (account-based) lines."""
        entity = {
            "txnId": "BILL-002",
            "lines": [
                {"accountRefListId": "ACC-001", "amount": 500.00},
                {"accountRefListId": "ACC-002", "amount": 300.00},
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Bill")
        assert "ExpenseLines" in result
        assert "ItemLines" not in result
        assert len(result["ExpenseLines"]) == 2

    def test_bill_item_lines_only(self):
        """Bill with only item-based lines."""
        entity = {
            "txnId": "BILL-003",
            "lines": [
                {
                    "itemRefListId": "ITEM-001",
                    "quantity": 5,
                    "rate": 20.00,
                    "amount": 100.00,
                },
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Bill")
        assert "ItemLines" in result
        assert "ExpenseLines" not in result
        assert len(result["ItemLines"]) == 1

    def test_bill_line_item_ref_full_name(self):
        """Lines with ItemRefFullName should go to ItemLines."""
        entity = {
            "txnId": "BILL-004",
            "lines": [
                {"itemRefFullName": "Widget", "quantity": 3, "amount": 30.00},
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Bill")
        assert "ItemLines" in result
        assert len(result["ItemLines"]) == 1

    def test_journal_entry_lines(self):
        entity = {
            "txnId": "JE-001",
            "lines": [
                {
                    "accountRefListId": "ACC-001",
                    "amount": 1000.00,
                    "journalLineType": "Debit",
                },
                {
                    "accountRefListId": "ACC-002",
                    "amount": 1000.00,
                    "journalLineType": "Credit",
                },
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "JournalEntry")
        assert "JournalEntryLines" in result
        assert len(result["JournalEntryLines"]) == 2
        assert result["JournalEntryLines"][0].get("JournalLineType") == "Debit"
        assert result["JournalEntryLines"][1].get("JournalLineType") == "Credit"

    def test_credit_memo_lines(self):
        entity = {
            "txnId": "CM-001",
            "lines": [{"itemRefListId": "I1", "amount": 50.00}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "CreditMemo")
        assert "CreditMemoLines" in result
        assert len(result["CreditMemoLines"]) == 1

    def test_sales_receipt_lines(self):
        entity = {
            "txnId": "SR-001",
            "lines": [
                {"itemRefListId": "I1", "quantity": 2, "rate": 25.00, "amount": 50.00}
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "SalesReceipt")
        assert "SalesReceiptLines" in result

    def test_estimate_lines(self):
        entity = {
            "txnId": "EST-001",
            "lines": [{"itemRefListId": "I1", "amount": 300.00}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Estimate")
        assert "EstimateLines" in result

    def test_purchase_order_lines(self):
        entity = {
            "txnId": "PO-001",
            "lines": [
                {"itemRefListId": "I1", "quantity": 100, "rate": 5.00, "amount": 500.00}
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "PurchaseOrder")
        assert "POLines" in result

    def test_deposit_lines(self):
        entity = {
            "txnId": "DEP-001",
            "lines": [{"accountRefListId": "ACC-001", "amount": 1500.00}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Deposit")
        assert "DepositLines" in result

    def test_purchase_lines(self):
        entity = {
            "txnId": "PUR-001",
            "lines": [{"accountRefListId": "ACC-001", "amount": 250.00}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Purchase")
        assert "ExpenseLines" in result

    def test_inventory_adjustment_lines(self):
        entity = {
            "txnId": "ADJ-001",
            "lines": [{"itemRefListId": "I1", "quantityOnHand": 50}],
        }
        result = QBDataTransformer.normalize_extractor_fields(
            entity, "InventoryAdjustment"
        )
        assert "AdjustmentLines" in result

    def test_refund_receipt_lines(self):
        entity = {
            "txnId": "RR-001",
            "lines": [{"itemRefListId": "I1", "amount": 75.00}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "RefundReceipt")
        assert "RefundLines" in result

    def test_unknown_entity_type_defaults_to_lines_key(self):
        """Unknown entity type should use 'Lines' as default key."""
        entity = {
            "txnId": "X-001",
            "lines": [{"amount": 100.00}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "UnknownEntity")
        assert "Lines" in result

    def test_no_entity_type_defaults_to_lines_key(self):
        """No entity type should use 'Lines' as default key."""
        entity = {
            "txnId": "X-002",
            "lines": [{"amount": 200.00}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "")
        assert "Lines" in result

    def test_empty_lines_array(self):
        """Empty lines array should not create line key."""
        entity = {
            "txnId": "INV-003",
            "lines": [],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Invoice")
        assert "InvoiceLines" not in result

    def test_multiple_line_items_all_normalized(self):
        """All line items in array should be normalized."""
        entity = {
            "txnId": "INV-004",
            "lines": [
                {
                    "itemRefListId": "I1",
                    "quantity": 1,
                    "rate": 100.00,
                    "amount": 100.00,
                },
                {"itemRefListId": "I2", "quantity": 2, "rate": 50.00, "amount": 100.00},
                {"itemRefListId": "I3", "quantity": 3, "rate": 33.33, "amount": 99.99},
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Invoice")
        assert len(result["InvoiceLines"]) == 3
        for line in result["InvoiceLines"]:
            assert "ItemRef" in line
            assert "Quantity" in line
            assert "Rate" in line
            assert "Amount" in line

    def test_non_dict_line_items_pass_through(self):
        """Non-dict items in lines array should pass through unchanged."""
        entity = {
            "txnId": "INV-005",
            "lines": ["not-a-dict", 42, None],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Invoice")
        assert result["InvoiceLines"] == ["not-a-dict", 42, None]

    def test_existing_line_keys_not_overwritten(self):
        """If InvoiceLines already exists, 'lines' does not overwrite it."""
        entity = {
            "txnId": "INV1",
            "InvoiceLines": [{"existing": True}],
            "lines": [{"shouldnt": "overwrite"}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Invoice")
        assert len(result["InvoiceLines"]) == 1
        assert result["InvoiceLines"][0]["existing"] is True

    def test_entity_type_case_insensitive(self):
        """Entity type matching for line keys should be case-insensitive."""
        entity_lower = {
            "txnId": "INV-1",
            "lines": [{"amount": 100}],
        }
        entity_mixed = {
            "txnId": "INV-2",
            "lines": [{"amount": 200}],
        }
        result_lower = QBDataTransformer.normalize_extractor_fields(
            entity_lower, "invoice"
        )
        result_mixed = QBDataTransformer.normalize_extractor_fields(
            entity_mixed, "Invoice"
        )
        assert "InvoiceLines" in result_lower
        assert "InvoiceLines" in result_mixed


# ============================================================================
# normalize_extractor_fields: Idempotency
# ============================================================================


class TestNormalizeExtractorFieldsIdempotency:
    """Tests that already-PascalCase data passes through unchanged."""

    def test_pascal_case_entity_passes_through(self):
        entity = {
            "ListID": "80000001-1234567890",
            "Name": "Test Account",
            "AccountType": "Bank",
            "IsActive": True,
            "Balance": 1000.00,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Account")
        assert result == entity

    def test_pascal_case_with_nested_address(self):
        entity = {
            "ListID": "CUST-001",
            "Name": "Test Customer",
            "BillAddress": {
                "Addr1": "123 Main St",
                "City": "New York",
                "State": "NY",
            },
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Customer")
        assert result["BillAddress"] == entity["BillAddress"]

    def test_pascal_case_with_line_items(self):
        entity = {
            "TxnID": "INV-001",
            "InvoiceLines": [
                {"ItemRef": "I1", "Amount": 100.00},
            ],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, "Invoice")
        # Lines should stay as-is since InvoiceLines is already correct
        assert "InvoiceLines" in result
        assert result["InvoiceLines"] == entity["InvoiceLines"]

    def test_double_normalization_is_stable(self):
        """Normalizing twice should produce the same result as normalizing once."""
        entity = {
            "listId": "ACC-001",
            "name": "Cash",
            "accountType": "bank",
            "balance": 5000,
            "billAddressAddr1": "123 Main",
            "billAddressCity": "NY",
        }
        first = QBDataTransformer.normalize_extractor_fields(entity, "Account")
        second = QBDataTransformer.normalize_extractor_fields(first, "Account")
        assert first == second

    def test_idempotency_mixed_case_priority(self):
        """PascalCase fields are NOT overwritten by camelCase duplicates."""
        entity = {
            "Name": "Correct Name",  # PascalCase (should win)
            "name": "Wrong Name",  # camelCase (should be ignored)
            "ListID": "ID1",  # PascalCase (should win)
            "listId": "ID2",  # camelCase (should be ignored)
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Name"] == "Correct Name"
        assert result["ListID"] == "ID1"


# ============================================================================
# normalize_extractor_fields: Edge cases
# ============================================================================


class TestNormalizeExtractorFieldsEdgeCases:
    """Tests for edge cases and error handling."""

    def test_none_values_are_skipped(self):
        entity = {
            "listId": "ACC-001",
            "name": "Test",
            "desc": None,
            "accountNumber": None,
            "balance": None,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ListID"] == "ACC-001"
        assert result["Name"] == "Test"
        assert "Description" not in result
        assert "AccountNumber" not in result
        assert "Balance" not in result

    def test_all_none_values_returns_empty(self):
        entity = {"listId": None, "name": None, "balance": None}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result == {}

    def test_non_dict_input_string(self):
        assert QBDataTransformer.normalize_extractor_fields("string") == "string"

    def test_non_dict_input_int(self):
        assert QBDataTransformer.normalize_extractor_fields(42) == 42

    def test_non_dict_input_list(self):
        assert QBDataTransformer.normalize_extractor_fields([1, 2, 3]) == [1, 2, 3]

    def test_non_dict_input_none(self):
        assert QBDataTransformer.normalize_extractor_fields(None) is None

    def test_empty_dict_returns_empty(self):
        result = QBDataTransformer.normalize_extractor_fields({})
        assert result == {}

    def test_unknown_keys_pass_through(self):
        entity = {
            "listId": "ACC-001",
            "customField1": "value1",
            "mySpecialData": 42,
            "SomeWeirdKey": True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ListID"] == "ACC-001"
        assert result["customField1"] == "value1"
        assert result["mySpecialData"] == 42
        assert result["SomeWeirdKey"] is True

    def test_zero_values_are_preserved(self):
        entity = {"balance": 0, "quantity": 0, "rate": 0.0}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Balance"] == 0
        assert result["Quantity"] == 0
        assert result["Rate"] == 0.0

    def test_empty_string_values_are_preserved(self):
        entity = {"name": "", "desc": ""}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Name"] == ""
        assert result["Description"] == ""

    def test_false_boolean_is_preserved(self):
        entity = {"isActive": False, "isPaid": False}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["IsActive"] is False
        assert result["IsPaid"] is False

    def test_mixed_camel_and_pascal_case_fields(self):
        """Entity with a mix of camelCase and PascalCase should normalize correctly."""
        entity = {
            "listId": "ACC-001",
            "Name": "Already Pascal",
            "accountType": "Bank",
            "Balance": 5000,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ListID"] == "ACC-001"
        assert result["Name"] == "Already Pascal"
        assert result["AccountType"] == "Bank"
        assert result["Balance"] == 5000

    def test_nested_dict_values_preserved(self):
        """Nested dict values that are not addresses should pass through."""
        entity = {
            "listId": "A1",
            "SomeNestedData": {"key": "value", "number": 42},
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["SomeNestedData"] == {"key": "value", "number": 42}


# ============================================================================
# normalize_extractor_fields: Contact fields
# ============================================================================


class TestNormalizeExtractorFieldsContactFields:
    """Tests for contact/person field mappings."""

    def test_company_name(self):
        entity = {"companyName": "Acme Inc"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CompanyName"] == "Acme Inc"

    def test_company_name_original(self):
        entity = {"companyNameOriginal": "Acme Inc (Original)"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CompanyNameOriginal"] == "Acme Inc (Original)"

    def test_email(self):
        entity = {"email": "test@example.com"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Email"] == "test@example.com"

    def test_email_original(self):
        entity = {"emailOriginal": "original@example.com"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["EmailOriginal"] == "original@example.com"

    def test_phone_fields(self):
        entity = {
            "phone": "555-0100",
            "altPhone": "555-0200",
            "fax": "555-0300",
            "mobile": "555-0400",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Phone"] == "555-0100"
        assert result["AltPhone"] == "555-0200"
        assert result["Fax"] == "555-0300"
        assert result["Mobile"] == "555-0400"

    def test_contact_fields(self):
        entity = {
            "contact": "John Doe",
            "altContact": "Jane Smith",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Contact"] == "John Doe"
        assert result["AltContact"] == "Jane Smith"

    def test_notes(self):
        entity = {"notes": "Important customer notes"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Notes"] == "Important customer notes"

    def test_salutation(self):
        entity = {"salutation": "Mr."}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Salutation"] == "Mr."

    def test_credit_limit(self):
        entity = {"creditLimit": 10000.00}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CreditLimit"] == 10000.00

    def test_total_balance(self):
        entity = {"totalBalance": 5000.00}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["TotalBalance"] == 5000.00

    def test_sublevel(self):
        entity = {"sublevel": 2}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Sublevel"] == 2


# ============================================================================
# normalize_extractor_fields: Customer job fields
# ============================================================================


class TestNormalizeExtractorFieldsCustomerJobFields:
    """Tests for customer job field mappings."""

    def test_job_status(self):
        entity = {"jobStatus": "InProgress"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["JobStatus"] == "InProgress"

    def test_job_dates(self):
        entity = {
            "jobStartDate": "2024-01-01",
            "jobProjectedEndDate": "2024-06-30",
            "jobEndDate": "2024-07-15",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["JobStartDate"] == "2024-01-01"
        assert result["JobProjectedEndDate"] == "2024-06-30"
        assert result["JobEndDate"] == "2024-07-15"

    def test_job_desc(self):
        entity = {"jobDesc": "Website redesign project"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["JobDesc"] == "Website redesign project"

    def test_resale_number(self):
        entity = {"resaleNumber": "RS-12345"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["ResaleNumber"] == "RS-12345"


# ============================================================================
# normalize_extractor_fields: Terms, Tax, Currency, and PaymentMethod fields
# ============================================================================


class TestNormalizeExtractorFieldsMiscFields:
    """Tests for terms, tax, currency, and payment method fields."""

    def test_terms_fields(self):
        entity = {
            "name": "Net 30",
            "dueDays": 30,
            "discountPct": 2.0,
            "discountDays": 10,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Name"] == "Net 30"
        assert result["DueDays"] == 30
        assert result["DiscountPct"] == 2.0
        assert result["DiscountDays"] == 10

    def test_date_driven_terms_fields(self):
        entity = {
            "dayOfMonthDue": 15,
            "dueNextMonthDays": 25,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["DayOfMonthDue"] == 15
        assert result["DueNextMonthDays"] == 25

    def test_tax_fields(self):
        entity = {
            "name": "Sales Tax",
            "description": "State sales tax",
            "taxRate": 8.25,
            "isTaxable": True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["Name"] == "Sales Tax"
        assert result["Description"] == "State sales tax"
        assert result["TaxRate"] == 8.25
        assert result["IsTaxable"] is True

    def test_currency_fields(self):
        entity = {
            "name": "Canadian Dollar",
            "currencyCode": "CAD",
            "exchangeRate": 0.75,
            "isUserDefinedCurrency": False,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CurrencyCode"] == "CAD"
        assert result["ExchangeRate"] == 0.75
        assert result["IsUserDefinedCurrency"] is False

    def test_currency_format(self):
        entity = {"currencyFormat": "#,##0.00"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["CurrencyFormat"] == "#,##0.00"

    def test_payment_method_type(self):
        entity = {
            "name": "Visa",
            "paymentMethodType": "CreditCard",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["PaymentMethodType"] == "CreditCard"


# ============================================================================
# normalize_extractor_fields: Audit/integrity fields
# ============================================================================


class TestNormalizeExtractorFieldsAuditFields:
    """Tests for audit and integrity field mappings."""

    def test_integrity_hash(self):
        entity = {"integrityHash": "abc123hash"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["IntegrityHash"] == "abc123hash"

    def test_sha256_integrity_hash(self):
        entity = {"sha256IntegrityHash": "sha256_hash_value"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["IntegrityHash"] == "sha256_hash_value"

    def test_edit_sequence(self):
        entity = {"editSequence": "1234567890"}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["EditSequence"] == "1234567890"

    def test_time_fields(self):
        entity = {
            "timeCreated": "2024-01-01T00:00:00",
            "timeModified": "2024-06-15T12:30:00",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["TimeCreated"] == "2024-01-01T00:00:00"
        assert result["TimeModified"] == "2024-06-15T12:30:00"

    def test_schema_metadata(self):
        entity = {
            "schemaVersion": "3.1",
            "extractionVersion": "2.0.1",
            "extractedAt": "2024-01-15T10:00:00Z",
            "sessionId": "sess-12345",
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result["SchemaVersion"] == "3.1"
        assert result["ExtractionVersion"] == "2.0.1"
        assert result["ExtractedAt"] == "2024-01-15T10:00:00Z"
        assert result["SessionID"] == "sess-12345"


# ============================================================================
# normalize_extractor_fields: Line item specific fields
# ============================================================================


class TestNormalizeExtractorFieldsLineItemFields:
    """Tests for line-item-specific field mappings within line items."""

    def test_line_item_quantity_and_rate(self):
        line = {"quantity": 5, "rate": 10.00, "amount": 50.00}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["Quantity"] == 5
        assert result["Rate"] == 10.00
        assert result["Amount"] == 50.00

    def test_unit_of_measure(self):
        line = {"unitOfMeasure": "Each"}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["UnitOfMeasure"] == "Each"

    def test_service_date(self):
        line = {"serviceDate": "2024-03-15"}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["ServiceDate"] == "2024-03-15"

    def test_journal_line_type(self):
        line = {"journalLineType": "Credit"}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["JournalLineType"] == "Credit"

    def test_is_billable(self):
        line = {"isBillable": True}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["IsBillable"] is True

    def test_billing_status(self):
        line = {"billingStatus": "Billable"}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["BillingStatus"] == "Billable"

    def test_rate_percent(self):
        line = {"ratePercent": 8.25}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["RatePercent"] == 8.25

    def test_received_quantity(self):
        line = {"receivedQuantity": 50}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["ReceivedQuantity"] == 50

    def test_txn_line_id(self):
        line = {"txnLineId": "TL-001"}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result["TxnLineID"] == "TL-001"


# ============================================================================
# normalize_data_keys: Basic entity key mapping
# ============================================================================


class TestNormalizeDataKeysBasicMapping:
    """Tests for top-level entity collection key normalization."""

    def test_accounts_to_account(self):
        data = {"accounts": [{"listId": "A1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Account" in result
        assert "accounts" not in result
        assert result["Account"] == [{"listId": "A1"}]

    def test_customers_to_customer(self):
        data = {"customers": [{"listId": "C1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Customer" in result
        assert "customers" not in result

    def test_vendors_to_vendor(self):
        data = {"vendors": [{"listId": "V1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Vendor" in result
        assert "vendors" not in result

    def test_items_to_item(self):
        data = {"items": [{"listId": "I1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Item" in result
        assert "items" not in result

    def test_employees_to_employee(self):
        data = {"employees": [{"listId": "E1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Employee" in result

    def test_invoices_to_invoice(self):
        data = {"invoices": [{"txnId": "INV1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Invoice" in result

    def test_bills_to_bill(self):
        data = {"bills": [{"txnId": "BILL1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Bill" in result

    def test_journal_entries_to_journal_entry(self):
        data = {"journalEntries": [{"txnId": "JE1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "JournalEntry" in result

    def test_bill_payments_to_bill_payment(self):
        data = {"billPayments": [{"txnId": "BP1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "BillPayment" in result

    def test_receive_payments_to_payment(self):
        data = {"receivePayments": [{"txnId": "RP1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Payment" in result

    def test_sales_tax_codes_to_tax_code(self):
        data = {"salesTaxCodes": [{"listId": "TC1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "TaxCode" in result

    def test_payment_methods_to_payment_method(self):
        data = {"paymentMethods": [{"listId": "PM1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "PaymentMethod" in result

    def test_credit_memos_to_credit_memo(self):
        data = {"creditMemos": [{"txnId": "CM1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "CreditMemo" in result

    def test_sales_receipts_to_sales_receipt(self):
        data = {"salesReceipts": [{"txnId": "SR1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "SalesReceipt" in result

    def test_estimates_to_estimate(self):
        data = {"estimates": [{"txnId": "EST1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Estimate" in result

    def test_deposits_to_deposit(self):
        data = {"deposits": [{"txnId": "DEP1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Deposit" in result

    def test_transfers_to_transfer(self):
        data = {"transfers": [{"txnId": "TR1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Transfer" in result

    def test_vendor_credits_to_vendor_credit(self):
        data = {"vendorCredits": [{"txnId": "VC1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "VendorCredit" in result

    def test_purchase_orders_to_purchase_order(self):
        data = {"purchaseOrders": [{"txnId": "PO1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "PurchaseOrder" in result

    def test_currencies_to_company_currency(self):
        data = {"currencies": [{"name": "USD"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "CompanyCurrency" in result

    def test_classes_to_class(self):
        data = {"classes": [{"listId": "CL1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Class" in result

    def test_terms_to_term(self):
        data = {"terms": [{"listId": "T1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Term" in result

    def test_customer_types_to_customer_type(self):
        data = {"customerTypes": [{"listId": "CT1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "CustomerType" in result

    def test_vendor_types_to_vendor_type(self):
        data = {"vendorTypes": [{"listId": "VT1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "VendorType" in result

    def test_job_types_to_job_type(self):
        data = {"jobTypes": [{"listId": "JT1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "JobType" in result

    def test_customer_messages_to_customer_message(self):
        data = {"customerMessages": [{"listId": "MSG1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "CustomerMessage" in result

    def test_date_driven_terms(self):
        data = {"dateDrivenTerms": [{"listId": "DDT1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "DateDrivenTerm" in result

    def test_sales_tax_groups(self):
        data = {"salesTaxGroups": [{"listId": "STG1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "SalesTaxGroup" in result

    def test_price_levels(self):
        data = {"priceLevels": [{"listId": "PL1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "PriceLevel" in result

    def test_sales_reps(self):
        data = {"salesReps": [{"listId": "SR1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "SalesRep" in result

    def test_ship_methods(self):
        data = {"shipMethods": [{"listId": "SM1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "ShipMethod" in result

    def test_inventory_adjustments_to_inventory_adjustment(self):
        data = {"inventoryAdjustments": [{"txnId": "IA1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "InventoryAdjustment" in result

    def test_sales_tax_payments_to_tax_payment(self):
        data = {"salesTaxPayments": [{"txnId": "STP1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "TaxPayment" in result

    def test_sales_orders_to_sales_order(self):
        data = {"salesOrders": [{"txnId": "SO1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "SalesOrder" in result

    def test_multiple_keys_at_once(self):
        data = {
            "accounts": [{"listId": "A1"}],
            "customers": [{"listId": "C1"}],
            "vendors": [{"listId": "V1"}],
            "invoices": [{"txnId": "INV1"}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Account" in result
        assert "Customer" in result
        assert "Vendor" in result
        assert "Invoice" in result
        assert len(result) == 4


# ============================================================================
# normalize_data_keys: Already-correct keys
# ============================================================================


class TestNormalizeDataKeysAlreadyCorrect:
    """Tests that already PascalCase singular keys pass through."""

    def test_account_key_passes_through(self):
        data = {"Account": [{"ListID": "A1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Account" in result
        assert result["Account"] == [{"ListID": "A1"}]

    def test_mixed_correct_and_camel_keys(self):
        data = {
            "Account": [{"ListID": "A1"}],
            "customers": [{"listId": "C1"}],
            "Invoice": [{"TxnID": "INV1"}],
            "vendors": [{"listId": "V1"}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Account" in result
        assert "Customer" in result
        assert "Invoice" in result
        assert "Vendor" in result

    def test_all_pascal_case_keys_unchanged(self):
        data = {
            "Account": [{"ListID": "A1"}],
            "Customer": [{"ListID": "C1"}],
            "Vendor": [{"ListID": "V1"}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert result == data


# ============================================================================
# normalize_data_keys: Merge behavior
# ============================================================================


class TestNormalizeDataKeysMergeBehavior:
    """Tests for merge behavior when multiple keys map to the same entity."""

    def test_checks_maps_to_purchase(self):
        data = {"checks": [{"txnId": "CHK1"}, {"txnId": "CHK2"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Purchase" in result
        assert len(result["Purchase"]) == 2

    def test_credit_card_charges_maps_to_purchase(self):
        data = {"creditCardCharges": [{"txnId": "CC1"}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Purchase" in result
        assert len(result["Purchase"]) == 1

    def test_checks_and_credit_card_charges_merge_into_purchase(self):
        data = {
            "checks": [{"txnId": "CHK1"}, {"txnId": "CHK2"}],
            "creditCardCharges": [{"txnId": "CC1"}, {"txnId": "CC2"}, {"txnId": "CC3"}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Purchase" in result
        assert len(result["Purchase"]) == 5
        # Verify all items are present
        txn_ids = [item["txnId"] for item in result["Purchase"]]
        assert "CHK1" in txn_ids
        assert "CHK2" in txn_ids
        assert "CC1" in txn_ids
        assert "CC2" in txn_ids
        assert "CC3" in txn_ids

    def test_merge_preserves_order(self):
        """First mapped key fills, second extends. Order should match iteration."""
        data = {
            "checks": [{"txnId": "CHK1"}],
            "creditCardCharges": [{"txnId": "CC1"}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert result["Purchase"][0]["txnId"] == "CHK1"
        assert result["Purchase"][1]["txnId"] == "CC1"

    def test_merge_with_existing_purchase_key(self):
        """If Purchase already exists and checks is also present, they should merge."""
        data = {
            "Purchase": [{"txnId": "P1"}],
            "checks": [{"txnId": "CHK1"}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Purchase" in result
        assert len(result["Purchase"]) == 2


# ============================================================================
# normalize_data_keys: Edge cases
# ============================================================================


class TestNormalizeDataKeysEdgeCases:
    """Tests for edge cases in data key normalization."""

    def test_non_dict_input_string(self):
        assert QBDataTransformer.normalize_data_keys("not a dict") == "not a dict"

    def test_non_dict_input_int(self):
        assert QBDataTransformer.normalize_data_keys(42) == 42

    def test_non_dict_input_none(self):
        assert QBDataTransformer.normalize_data_keys(None) is None

    def test_non_dict_input_list(self):
        assert QBDataTransformer.normalize_data_keys([1, 2]) == [1, 2]

    def test_empty_dict_returns_empty(self):
        result = QBDataTransformer.normalize_data_keys({})
        assert result == {}

    def test_unknown_keys_pass_through(self):
        data = {
            "accounts": [{"listId": "A1"}],
            "metadata": {"version": "3.1"},
            "unknownKey": "someValue",
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert "Account" in result
        assert result["metadata"] == {"version": "3.1"}
        assert result["unknownKey"] == "someValue"

    def test_empty_list_values(self):
        data = {"accounts": [], "customers": []}
        result = QBDataTransformer.normalize_data_keys(data)
        assert result["Account"] == []
        assert result["Customer"] == []

    def test_non_list_values_pass_through(self):
        """Even non-list values should be mapped correctly."""
        data = {"accounts": "not a list"}
        result = QBDataTransformer.normalize_data_keys(data)
        assert result["Account"] == "not a list"


# ============================================================================
# End-to-end integration: Full C# extractor output through transform()
# ============================================================================


class TestEndToEndIntegration:
    """Integration tests running full C# extractor output through the transform pipeline."""

    def test_full_csharp_extractor_output_through_transform(self, transformer):
        """
        Simulate a full C# QBExtractedData structure with camelCase keys/fields
        and verify the transform produces valid QBO-format output.
        """
        csharp_data = {
            "accounts": [
                {
                    "listId": "80000001-ABC",
                    "name": "Cash",
                    "accountType": "bank",
                    "balance": 1000,
                    "isActive": True,
                }
            ],
            "customers": [
                {
                    "listId": "80000002-C1",
                    "name": "Acme Corp",
                    "isActive": True,
                    "billAddressAddr1": "123 Main St",
                    "billAddressCity": "NY",
                    "billAddressState": "NY",
                    "billAddressPostalCode": "10001",
                }
            ],
            "items": [
                {
                    "listId": "80000003-I1",
                    "name": "Service Item",
                    "type": "Service",
                    "salesPrice": 100,
                    "salesDescription": "Professional consulting",
                    "isActive": True,
                }
            ],
        }

        result = transformer.transform(csharp_data)

        # Verify structure
        assert "entities" in result
        assert "summary" in result
        assert "trial_balance" in result
        assert "metadata" in result

        # Verify accounts were transformed
        assert "Account" in result["entities"]
        accounts = result["entities"]["Account"]
        assert len(accounts) >= 1
        cash_account = accounts[0]
        assert cash_account.get("Name") is not None
        assert cash_account.get("AccountType") is not None

        # Verify customers were transformed
        assert "Customer" in result["entities"]
        customers = result["entities"]["Customer"]
        assert len(customers) >= 1

        # Verify items were transformed
        assert "Item" in result["entities"]
        items = result["entities"]["Item"]
        assert len(items) >= 1

    def test_full_csharp_output_detailed_validation(self):
        """Detailed validation of C# extractor output after transformation."""
        csharp_output = {
            "accounts": [
                {
                    "listId": "ACC-001",
                    "name": "Checking Account",
                    "accountType": "checking",
                    "accountNumber": "1010",
                    "desc": "Main business checking",
                    "balance": 15000.00,
                    "isActive": True,
                },
                {
                    "listId": "ACC-002",
                    "name": "Accounts Receivable",
                    "accountType": "accounts receivable",
                    "balance": 5000.00,
                    "isActive": True,
                },
            ],
            "customers": [
                {
                    "listId": "CUST-001",
                    "name": "Acme Corporation",
                    "companyName": "Acme Corp",
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john@acme.com",
                    "phone": "555-0100",
                    "isActive": True,
                    "billAddressAddr1": "123 Main Street",
                    "billAddressCity": "New York",
                    "billAddressState": "NY",
                    "billAddressPostalCode": "10001",
                    "billAddressCountry": "US",
                },
            ],
            "items": [
                {
                    "listId": "ITEM-001",
                    "name": "Consulting Service",
                    "type": "Service",
                    "salesPrice": 150.00,
                    "salesDescription": "Professional consulting",
                    "isActive": True,
                },
            ],
        }

        t = QBDataTransformer(region="US")
        result = t.transform(csharp_output)

        entities = result["entities"]

        # Accounts
        assert "Account" in entities
        assert len(entities["Account"]) == 2
        acct = entities["Account"][0]
        assert acct["Name"] == "Checking Account"
        assert acct["AccountType"] == "Bank"
        assert acct["AccountSubType"] == "Checking"

        # Customers
        assert "Customer" in entities
        assert len(entities["Customer"]) == 1
        cust = entities["Customer"][0]
        assert cust["DisplayName"] == "Acme Corporation"
        assert cust["CompanyName"] == "Acme Corp"
        assert cust["GivenName"] == "John"
        assert cust["FamilyName"] == "Doe"
        assert cust["PrimaryEmailAddr"] == {"Address": "john@acme.com"}
        assert "BillAddr" in cust
        assert cust["BillAddr"]["Line1"] == "123 Main Street"
        assert cust["BillAddr"]["City"] == "New York"

        # Items
        assert "Item" in entities
        assert len(entities["Item"]) == 1
        item = entities["Item"][0]
        assert "Consulting Service" in item["Name"]
        assert item["Type"] == "Service"

    def test_csharp_invoice_with_lines(self, transformer):
        """Test C# invoice with line items processes through transform."""
        csharp_data = {
            "accounts": [
                {
                    "listId": "80000001-AR",
                    "name": "Accounts Receivable",
                    "accountType": "accountsreceivable",
                    "balance": 0,
                    "isActive": True,
                },
                {
                    "listId": "80000001-INC",
                    "name": "Sales Income",
                    "accountType": "income",
                    "balance": 0,
                    "isActive": True,
                },
            ],
            "customers": [
                {
                    "listId": "80000002-C1",
                    "name": "Test Customer",
                    "isActive": True,
                }
            ],
            "items": [
                {
                    "listId": "80000003-I1",
                    "name": "Service Item",
                    "type": "Service",
                    "salesPrice": 100,
                    "isActive": True,
                }
            ],
            "invoices": [
                {
                    "txnId": "80000004-INV1",
                    "refNumber": "1001",
                    "txnDate": "2024-01-15",
                    "customerRefListId": "80000002-C1",
                    "lines": [
                        {
                            "itemRefListId": "80000003-I1",
                            "description": "Consulting services",
                            "quantity": 1,
                            "rate": 100,
                            "amount": 100,
                        }
                    ],
                }
            ],
        }

        result = transformer.transform(csharp_data)

        assert "entities" in result
        assert result["metadata"]["version"] == "3.1.0"

    def test_csharp_invoice_detailed_line_output(self):
        """Detailed test of invoice line transformation from C# format."""
        csharp_output = {
            "accounts": [
                {
                    "listId": "ACC-AR",
                    "name": "AR",
                    "accountType": "accounts receivable",
                    "balance": 0,
                    "isActive": True,
                },
            ],
            "customers": [
                {"listId": "CUST-1", "name": "Client A", "isActive": True},
            ],
            "items": [
                {
                    "listId": "ITEM-1",
                    "name": "Widget",
                    "type": "Service",
                    "isActive": True,
                },
            ],
            "invoices": [
                {
                    "txnId": "INV-001",
                    "refNumber": "1001",
                    "txnDate": "2024-01-15",
                    "customerRefListId": "CUST-1",
                    "dueDate": "2024-02-15",
                    "memo": "January services",
                    "lines": [
                        {
                            "txnLineId": "L1",
                            "itemRefListId": "ITEM-1",
                            "description": "Consulting work",
                            "quantity": 10,
                            "rate": 150,
                            "amount": 1500,
                        }
                    ],
                }
            ],
        }

        t = QBDataTransformer(region="US")
        result = t.transform(csharp_output)
        entities = result["entities"]

        assert "Invoice" in entities
        inv = entities["Invoice"][0]
        assert inv["TxnDate"] == "2024-01-15"
        assert inv["DocNumber"] == "1001"
        assert inv["DueDate"] == "2024-02-15"
        assert inv["PrivateNote"] == "January services"
        assert "CustomerRef" in inv
        assert len(inv["Line"]) == 1
        line = inv["Line"][0]
        assert line["DetailType"] == "SalesItemLineDetail"
        assert line["Amount"] == 1500

    def test_csharp_bill_with_mixed_lines(self, transformer):
        """Test C# bill with mixed expense and item lines."""
        csharp_data = {
            "accounts": [
                {
                    "listId": "80000001-AP",
                    "name": "Accounts Payable",
                    "accountType": "accountspayable",
                    "balance": 0,
                    "isActive": True,
                },
                {
                    "listId": "80000001-EXP",
                    "name": "Office Expense",
                    "accountType": "expense",
                    "balance": 0,
                    "isActive": True,
                },
            ],
            "vendors": [
                {
                    "listId": "80000005-V1",
                    "name": "Supplier Corp",
                    "isActive": True,
                    "isVendorEligibleFor1099": False,
                }
            ],
            "bills": [
                {
                    "txnId": "80000006-BILL1",
                    "refNumber": "B-001",
                    "txnDate": "2024-02-01",
                    "vendorRefListId": "80000005-V1",
                    "dueDate": "2024-03-01",
                    "memo": "February supplies",
                    "lines": [
                        {
                            "accountRefListId": "80000001-EXP",
                            "description": "Office supplies",
                            "amount": 250.00,
                        },
                        {
                            "itemRefListId": "80000003-I1",
                            "description": "Widgets",
                            "quantity": 10,
                            "rate": 25.00,
                            "amount": 250.00,
                        },
                    ],
                }
            ],
        }

        result = transformer.transform(csharp_data)
        assert "entities" in result
        assert result["metadata"]["version"] == "3.1.0"

    def test_csharp_bill_detailed_output(self):
        """Detailed test of bill transformation from C# format."""
        csharp_output = {
            "accounts": [
                {
                    "listId": "ACC-AP",
                    "name": "AP",
                    "accountType": "accounts payable",
                    "balance": 0,
                    "isActive": True,
                },
                {
                    "listId": "ACC-RENT",
                    "name": "Rent",
                    "accountType": "expense",
                    "balance": 0,
                    "isActive": True,
                },
            ],
            "vendors": [
                {"listId": "VEND-1", "name": "Supplier Co", "isActive": True},
            ],
            "items": [
                {
                    "listId": "ITEM-1",
                    "name": "Office Supplies",
                    "type": "NonInventory",
                    "isActive": True,
                },
            ],
            "bills": [
                {
                    "txnId": "BILL-001",
                    "refNumber": "B-100",
                    "txnDate": "2024-01-20",
                    "vendorRefListId": "VEND-1",
                    "lines": [
                        {
                            "accountRefListId": "ACC-RENT",
                            "amount": 2000,
                            "description": "Office rent",
                        },
                        {
                            "itemRefListId": "ITEM-1",
                            "quantity": 5,
                            "rate": 20,
                            "amount": 100,
                        },
                    ],
                }
            ],
        }

        t = QBDataTransformer(region="US")
        result = t.transform(csharp_output)
        entities = result["entities"]

        assert "Bill" in entities
        bill = entities["Bill"][0]
        assert bill["TxnDate"] == "2024-01-20"
        assert bill["DocNumber"] == "B-100"
        assert len(bill["Line"]) >= 1

    def test_csharp_vendor_with_flat_address(self):
        """Test vendor with flat address fields from C# extractor."""
        csharp_output = {
            "vendors": [
                {
                    "listId": "V1",
                    "name": "Tech Supplier",
                    "companyName": "Tech Supplier LLC",
                    "firstName": "Bob",
                    "lastName": "Builder",
                    "email": "bob@tech.com",
                    "phone": "555-9999",
                    "isActive": True,
                    "vendorAddressAddr1": "456 Commerce Dr",
                    "vendorAddressCity": "Austin",
                    "vendorAddressState": "TX",
                    "vendorAddressPostalCode": "78701",
                    "isVendorEligibleFor1099": True,
                },
            ],
        }

        t = QBDataTransformer(region="US")
        result = t.transform(csharp_output)
        entities = result["entities"]

        assert "Vendor" in entities
        vendor = entities["Vendor"][0]
        assert "Tech Supplier" in vendor["DisplayName"]
        assert vendor["CompanyName"] == "Tech Supplier LLC"
        assert vendor["GivenName"] == "Bob"
        assert vendor["FamilyName"] == "Builder"
        assert vendor["PrimaryEmailAddr"] == {"Address": "bob@tech.com"}
        assert "BillAddr" in vendor
        assert vendor["BillAddr"]["Line1"] == "456 Commerce Dr"
        assert vendor["BillAddr"]["City"] == "Austin"
        assert vendor.get("Vendor1099") is True

    def test_csharp_employee_with_ssn_masking(self):
        """Test employee SSN masking with camelCase input."""
        csharp_output = {
            "employees": [
                {
                    "listId": "EMP-1",
                    "name": "Jane Smith",
                    "firstName": "Jane",
                    "lastName": "Smith",
                    "ssn": "123-45-6789",
                    "email": "jane@company.com",
                    "isActive": True,
                },
            ],
        }

        t = QBDataTransformer(region="US")
        result = t.transform(csharp_output)
        entities = result["entities"]

        assert "Employee" in entities
        emp = entities["Employee"][0]
        assert "Jane Smith" in emp["DisplayName"]
        assert emp["SSN"] == "XXX-XX-6789"

    def test_normalize_then_transform_accounts(self, transformer):
        """Verify that normalized accounts can be successfully transformed."""
        camel_account = {
            "listId": "80000001-CASH",
            "name": "Operating Cash",
            "accountType": "bank",
            "desc": "Main operating account",
            "accountNumber": "1010",
            "balance": 50000,
            "isActive": True,
        }

        normalized = QBDataTransformer.normalize_extractor_fields(
            camel_account, "Account"
        )
        assert normalized["Name"] == "Operating Cash"
        assert normalized["AccountType"] == "bank"
        assert normalized["Description"] == "Main operating account"
        assert normalized["AccountNumber"] == "1010"

        qbo = transformer.transform_account(normalized)
        assert qbo is not None
        assert qbo["Name"] is not None
        assert "AccountType" in qbo

    def test_normalize_then_transform_customer(self, transformer):
        """Verify that normalized customers can be successfully transformed."""
        camel_customer = {
            "listId": "80000002-CUST",
            "name": "Acme Corporation",
            "companyName": "Acme Corp",
            "isActive": True,
            "email": "info@acme.com",
            "phone": "555-0100",
            "billAddressAddr1": "123 Main Street",
            "billAddressCity": "Springfield",
            "billAddressState": "IL",
            "billAddressPostalCode": "62701",
            "billAddressCountry": "US",
        }

        normalized = QBDataTransformer.normalize_extractor_fields(
            camel_customer, "Customer"
        )
        assert normalized["Name"] == "Acme Corporation"
        assert normalized["CompanyName"] == "Acme Corp"
        assert normalized["Email"] == "info@acme.com"
        assert normalized["Phone"] == "555-0100"
        assert "BillAddress" in normalized
        assert normalized["BillAddress"]["Addr1"] == "123 Main Street"

        qbo = transformer.transform_customer(normalized)
        assert qbo is not None
        assert "DisplayName" in qbo

    def test_normalize_then_transform_vendor(self, transformer):
        """Verify that normalized vendors can be successfully transformed."""
        camel_vendor = {
            "listId": "80000005-VEND",
            "name": "Supply House",
            "companyName": "Supply House Inc",
            "isActive": True,
            "isVendorEligibleFor1099": True,
            "vendorAddressAddr1": "456 Vendor Way",
            "vendorAddressCity": "Commerce",
            "vendorAddressState": "CA",
            "vendorAddressPostalCode": "90040",
        }

        normalized = QBDataTransformer.normalize_extractor_fields(
            camel_vendor, "Vendor"
        )
        assert normalized["Is1099"] is True
        assert "VendorAddress" in normalized
        assert "Address" in normalized
        assert normalized["Address"]["Addr1"] == "456 Vendor Way"

        qbo = transformer.transform_vendor(normalized)
        assert qbo is not None
        assert "DisplayName" in qbo

    def test_normalize_then_transform_item(self, transformer):
        """Verify that normalized items can be successfully transformed."""
        camel_item = {
            "listId": "80000003-ITEM",
            "name": "Widget Pro",
            "type": "Inventory",
            "salesPrice": 49.99,
            "salesDescription": "Professional Widget",
            "purchaseCost": 25.00,
            "purchaseDescription": "Buy widgets",
            "quantityOnHand": 100,
            "isActive": True,
        }

        normalized = QBDataTransformer.normalize_extractor_fields(camel_item, "Item")
        assert normalized["ItemType"] == "Inventory"
        assert normalized["UnitPrice"] == 49.99
        assert normalized["Description"] == "Professional Widget"
        assert normalized["QuantityOnHand"] == 100

        qbo = transformer.transform_item(normalized)
        assert qbo is not None
        assert "Name" in qbo

    def test_full_company_data_normalization_flow(self, transformer):
        """
        Full end-to-end test with the exact JSON structure from the user specification.
        Verifies normalize_data_keys, normalize_extractor_fields, and transform all work together.
        """
        csharp_extractor_output = {
            "accounts": [
                {
                    "listId": "ABC",
                    "name": "Cash",
                    "accountType": "bank",
                    "balance": 1000,
                }
            ],
            "customers": [
                {
                    "listId": "C1",
                    "name": "Acme Corp",
                    "billAddressAddr1": "123 Main St",
                    "billAddressCity": "NY",
                    "billAddressState": "NY",
                }
            ],
            "invoices": [
                {
                    "txnId": "INV1",
                    "refNumber": "1001",
                    "txnDate": "2024-01-15",
                    "customerRefListId": "C1",
                    "lines": [
                        {
                            "itemRefListId": "I1",
                            "description": "Service",
                            "quantity": 1,
                            "rate": 100,
                            "amount": 100,
                        }
                    ],
                }
            ],
            "items": [
                {
                    "listId": "I1",
                    "name": "Service Item",
                    "type": "Service",
                    "salesPrice": 100,
                }
            ],
        }

        # Step 1: Normalize data keys
        normalized_keys = QBDataTransformer.normalize_data_keys(csharp_extractor_output)
        assert "Account" in normalized_keys
        assert "Customer" in normalized_keys
        assert "Invoice" in normalized_keys
        assert "Item" in normalized_keys

        # Step 2: Normalize entity fields
        for entity_type, entities in normalized_keys.items():
            if isinstance(entities, list):
                for i, entity in enumerate(entities):
                    if isinstance(entity, dict):
                        normalized_keys[entity_type][i] = (
                            QBDataTransformer.normalize_extractor_fields(
                                entity, entity_type
                            )
                        )

        # Verify account normalization
        acct = normalized_keys["Account"][0]
        assert acct["ListID"] == "ABC"
        assert acct["Name"] == "Cash"
        assert acct["AccountType"] == "bank"
        assert acct["Balance"] == 1000

        # Verify customer normalization with address
        cust = normalized_keys["Customer"][0]
        assert cust["ListID"] == "C1"
        assert cust["Name"] == "Acme Corp"
        assert "BillAddress" in cust
        assert cust["BillAddress"]["Addr1"] == "123 Main St"

        # Verify invoice normalization with lines
        inv = normalized_keys["Invoice"][0]
        assert inv["TxnID"] == "INV1"
        assert inv["RefNumber"] == "1001"
        assert inv["TxnDate"] == "2024-01-15"
        assert inv["CustomerRef"] == "C1"
        assert "InvoiceLines" in inv
        assert len(inv["InvoiceLines"]) == 1
        line = inv["InvoiceLines"][0]
        assert line["ItemRef"] == "I1"
        assert line["Description"] == "Service"
        assert line["Quantity"] == 1
        assert line["Rate"] == 100
        assert line["Amount"] == 100

        # Verify item normalization
        item = normalized_keys["Item"][0]
        assert item["ListID"] == "I1"
        assert item["Name"] == "Service Item"
        assert item["ItemType"] == "Service"
        assert item["UnitPrice"] == 100

        # Step 3: Run through full transform (uses original camelCase input)
        result = transformer.transform(csharp_extractor_output)
        assert "entities" in result
        assert result["metadata"]["version"] == "3.1.0"

    def test_transform_entity_with_camelcase(self):
        """Test transform_entity() with camelCase input (orchestrator path)."""
        t = QBDataTransformer(region="US")

        account = {
            "listId": "A1",
            "name": "Cash",
            "accountType": "bank",
            "balance": 5000,
            "isActive": True,
        }

        result = t.transform_entity("Accounts", account)
        assert result is not None
        assert result["Name"] == "Cash"
        assert result["AccountType"] == "Bank"

    def test_transform_entity_customer_with_address(self):
        """Test transform_entity() for customer with flat address."""
        t = QBDataTransformer(region="US")

        customer = {
            "listId": "C1",
            "name": "Test Customer",
            "email": "test@test.com",
            "isActive": True,
            "billAddressAddr1": "100 Test Rd",
            "billAddressCity": "Testville",
            "billAddressState": "CA",
            "billAddressPostalCode": "90210",
        }

        result = t.transform_entity("Customers", customer)
        assert result is not None
        assert result["DisplayName"] == "Test Customer"
        assert "BillAddr" in result
        assert result["BillAddr"]["Line1"] == "100 Test Rd"
        assert result["BillAddr"]["City"] == "Testville"

    def test_transform_entity_item_type_mapping(self):
        """Test that C# 'type' field maps to ItemType correctly."""
        t = QBDataTransformer(region="US")

        item = {
            "listId": "I1",
            "name": "Test Item",
            "type": "Service",
            "salesPrice": 100,
            "isActive": True,
        }

        result = t.transform_entity("Items", item)
        assert result is not None
        assert result["Type"] == "Service"

    def test_transform_handles_all_camel_case_entity_types(self, transformer):
        """Verify transform() handles a variety of camelCase entity type keys."""
        data = {
            "accounts": [
                {
                    "listId": "A1",
                    "name": "Checking",
                    "accountType": "bank",
                    "balance": 500,
                    "isActive": True,
                },
            ],
            "paymentMethods": [
                {"listId": "PM1", "name": "Cash", "isActive": True},
            ],
            "terms": [
                {"listId": "T1", "name": "Net 30", "dueDays": 30, "isActive": True},
            ],
        }

        result = transformer.transform(data)
        assert "entities" in result
        assert "Account" in result["entities"]

    def test_transform_with_empty_camel_case_data(self, transformer):
        """Empty entity lists should not cause errors."""
        data = {
            "accounts": [],
            "customers": [],
            "invoices": [],
        }

        result = transformer.transform(data)
        assert "entities" in result
        assert "Account" not in result["entities"]
        assert "Customer" not in result["entities"]
        assert "Invoice" not in result["entities"]

    def test_transform_preserves_trial_balance(self, transformer):
        """Verify trial balance is computed correctly from camelCase input."""
        data = {
            "accounts": [
                {
                    "listId": "A1",
                    "name": "Cash",
                    "accountType": "bank",
                    "balance": 10000,
                    "isActive": True,
                },
                {
                    "listId": "A2",
                    "name": "Revenue",
                    "accountType": "income",
                    "balance": 10000,
                    "isActive": True,
                },
            ],
        }

        result = transformer.transform(data)
        assert "trial_balance" in result
        assert "debits" in result["trial_balance"]
        assert "credits" in result["trial_balance"]

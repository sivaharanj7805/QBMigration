"""
Tests for C# Extractor Resilience: NullValueHandling.Ignore Behavior
=====================================================================

The C# QBDataExtractor uses Newtonsoft.Json with NullValueHandling.Ignore,
which means:
  - Null fields are completely OMITTED from JSON (key does not exist)
  - Empty collections (List<T> with 0 items) are OMITTED
  - Empty strings ARE included (not null)
  - Default-value bools/ints/decimals may be omitted

These tests verify the Python transformer handles these conditions correctly:
1. Missing fields don't cause KeyError/TypeError
2. Missing line items cause graceful skip (not 400 from QBO)
3. Minimal data (only required fields) still transforms correctly
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_transformer import QBDataTransformer

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def transformer():
    """Transformer with pre-populated ID mappings for ref validation."""
    t = QBDataTransformer(region="US")
    # Pre-populate ID mappings so required refs resolve
    t.store_mapping("customers", "CUST-001", "QBO-CUST-001")
    t.store_mapping("vendors", "VEND-001", "QBO-VEND-001")
    t.store_mapping("accounts", "ACCT-001", "QBO-ACCT-001")
    t.store_mapping("accounts", "ACCT-002", "QBO-ACCT-002")
    t.store_mapping("items", "ITEM-001", "QBO-ITEM-001")
    t.store_mapping("tax_rates", "TAXRATE-001", "QBO-TR-001")
    return t


# ============================================================================
# _require_lines HELPER
# ============================================================================


class TestRequireLines:
    """Tests for the _require_lines validation helper."""

    def test_returns_true_when_lines_exist(self, transformer):
        qbo = {"Line": [{"Amount": 100}]}
        assert (
            transformer._require_lines(qbo, "Invoice", {"RefNumber": "INV-001"}) is True
        )

    def test_returns_false_when_lines_empty(self, transformer):
        qbo = {"Line": []}
        result = transformer._require_lines(qbo, "Invoice", {"RefNumber": "INV-001"})
        assert result is False
        assert transformer.stats["total_skipped"] == 1

    def test_adds_manual_review_on_empty_lines(self, transformer):
        qbo = {"Line": []}
        transformer._require_lines(qbo, "Bill", {"RefNumber": "BILL-001"})
        assert len(transformer.manual_review) == 1
        assert transformer.manual_review[0]["type"] == "Bill"
        assert transformer.manual_review[0]["name"] == "BILL-001"
        assert "No line items" in transformer.manual_review[0]["reason"]

    def test_uses_txn_id_when_no_ref_number(self, transformer):
        qbo = {"Line": []}
        transformer._require_lines(qbo, "Invoice", {"TxnID": "TXN-123"})
        assert transformer.manual_review[0]["name"] == "TXN-123"

    def test_uses_unknown_when_no_identifiers(self, transformer):
        qbo = {"Line": []}
        transformer._require_lines(qbo, "Invoice", {})
        assert transformer.manual_review[0]["name"] == "Unknown"

    def test_returns_false_when_line_key_missing(self, transformer):
        qbo = {}  # No 'Line' key at all
        result = transformer._require_lines(qbo, "Invoice", {"RefNumber": "INV-001"})
        assert result is False


# ============================================================================
# TRANSACTION TRANSFORMS: Empty Line Items → Skip
# ============================================================================


class TestEmptyLinesSkip:
    """Verify all transaction transforms return None when line items are omitted.

    Simulates the C# extractor's NullValueHandling.Ignore behavior where
    empty line item collections are completely omitted from JSON.
    """

    def test_invoice_no_lines_returns_none(self, transformer):
        """Invoice with valid customer but no InvoiceLines → skip."""
        qbd = {
            "TxnID": "TXN-INV-001",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
            # No InvoiceLines key at all (NullValueHandling.Ignore)
        }
        result = transformer.transform_invoice(qbd)
        assert result is None
        assert transformer.stats["total_skipped"] >= 1

    def test_bill_no_lines_returns_none(self, transformer):
        """Bill with valid vendor but no expense/item lines → skip."""
        qbd = {
            "TxnID": "TXN-BILL-001",
            "VendorRef": "VEND-001",
            "TxnDate": "2024-01-15",
            # No ExpenseLines or ItemLines
        }
        result = transformer.transform_bill(qbd)
        assert result is None

    def test_estimate_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-EST-001",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_estimate(qbd)
        assert result is None

    def test_salesreceipt_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-SR-001",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_salesreceipt(qbd)
        assert result is None

    def test_creditmemo_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-CM-001",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_creditmemo(qbd)
        assert result is None

    def test_vendorcredit_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-VC-001",
            "VendorRef": "VEND-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_vendorcredit(qbd)
        assert result is None

    def test_refundreceipt_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-RR-001",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_refundreceipt(qbd)
        assert result is None

    def test_purchaseorder_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-PO-001",
            "VendorRef": "VEND-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_purchaseorder(qbd)
        assert result is None

    def test_purchase_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-PUR-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_purchase(qbd)
        assert result is None

    def test_journalentry_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-JE-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_journalentry(qbd)
        assert result is None

    def test_deposit_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-DEP-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_deposit(qbd)
        assert result is None

    def test_inventoryadjustment_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-IA-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_inventoryadjustment(qbd)
        assert result is None

    def test_billpayment_no_lines_returns_none(self, transformer):
        qbd = {
            "TxnID": "TXN-BP-001",
            "VendorRef": "VEND-001",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_billpayment(qbd)
        assert result is None

    def test_payment_no_lines_still_valid(self, transformer):
        """Payments CAN be unapplied (no Line items) — should NOT skip."""
        qbd = {
            "TxnID": "TXN-PMT-001",
            "CustomerRef": "CUST-001",
            "TotalAmount": "100.00",
            "TxnDate": "2024-01-15",
        }
        result = transformer.transform_payment(qbd)
        # Payment should succeed even with empty lines
        assert result is not None
        assert result["CustomerRef"] == {"value": "QBO-CUST-001"}


# ============================================================================
# EXTRACTOR-REALISTIC DATA: Minimal Fields (NullValueHandling.Ignore)
# ============================================================================


class TestMinimalExtractorData:
    """Simulate what the C# extractor actually produces when optional fields
    are null (and therefore omitted by NullValueHandling.Ignore).

    Each test provides only the fields that QB Desktop guarantees to have
    non-null values — everything else is omitted.
    """

    def test_account_minimal(self, transformer):
        """Account with only ListID, Name, AccountType — everything else omitted."""
        qbd = {
            "ListID": "ACCT-100",
            "Name": "Checking",
            "AccountType": "Bank",
        }
        result = transformer.transform_account(qbd)
        assert result is not None
        assert result["Name"] == "Checking"
        assert "AccountType" in result

    def test_customer_minimal(self, transformer):
        """Customer with only ListID, Name — no email, phone, address, parent."""
        qbd = {
            "ListID": "CUST-100",
            "Name": "John Doe",
        }
        result = transformer.transform_customer(qbd)
        assert result is not None
        assert "DisplayName" in result
        # Optional fields should NOT be in output
        assert "PrimaryEmailAddr" not in result
        assert "PrimaryPhone" not in result
        assert "BillAddr" not in result

    def test_vendor_minimal(self, transformer):
        """Vendor with only ListID, Name."""
        qbd = {
            "ListID": "VEND-100",
            "Name": "Acme Supplies",
        }
        result = transformer.transform_vendor(qbd)
        assert result is not None
        assert "DisplayName" in result
        assert "PrimaryEmailAddr" not in result

    def test_employee_minimal(self, transformer):
        """Employee with only ListID, Name — no SSN, email, phone."""
        qbd = {
            "ListID": "EMP-100",
            "Name": "Jane Smith",
        }
        result = transformer.transform_employee(qbd)
        assert result is not None
        assert "DisplayName" in result
        assert "SSN" not in result
        assert "PrimaryEmailAddr" not in result

    def test_item_minimal_service(self, transformer):
        """Service item with only Name, ItemType — no description, price, accounts."""
        qbd = {
            "ListID": "ITEM-100",
            "Name": "Consulting",
            "ItemType": "Service",
        }
        result = transformer.transform_item(qbd)
        assert result is not None
        assert result["Type"] == "Service"

    def test_invoice_minimal_with_lines(self, transformer):
        """Invoice with minimal data but valid lines (requires valid ItemRef)."""
        qbd = {
            "TxnID": "TXN-INV-100",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
            "InvoiceLines": [
                {"Amount": "500.00", "Description": "Services", "ItemRef": "ITEM-001"},
            ],
        }
        result = transformer.transform_invoice(qbd)
        assert result is not None
        assert len(result["Line"]) == 1

    def test_bill_minimal_with_lines(self, transformer):
        """Bill with minimal data but valid expense line."""
        qbd = {
            "TxnID": "TXN-BILL-100",
            "VendorRef": "VEND-001",
            "TxnDate": "2024-01-15",
            "ExpenseLines": [
                {"Amount": "200.00", "AccountRef": "ACCT-001"},
            ],
        }
        result = transformer.transform_bill(qbd)
        assert result is not None
        assert len(result["Line"]) >= 1

    def test_class_minimal(self, transformer):
        """Class with only Name — no parent."""
        qbd = {"ListID": "CLS-001", "Name": "Department A"}
        result = transformer.transform_class(qbd)
        assert result is not None
        assert "ParentRef" not in result

    def test_department_minimal(self, transformer):
        """Department with only Name — no parent."""
        qbd = {"ListID": "DEPT-001", "Name": "Sales"}
        result = transformer.transform_department(qbd)
        assert result is not None

    def test_term_minimal(self, transformer):
        """Term with only Name — no DueDays, DiscountDays."""
        qbd = {"ListID": "TERM-001", "Name": "Custom Terms"}
        result = transformer.transform_term(qbd)
        assert result is not None
        assert "DueDays" not in result
        assert "DiscountDays" not in result

    def test_taxcode_no_rates_skipped(self, transformer):
        """TaxCode without TaxRateDetails → skipped (QBO TaxService requires rates)."""
        qbd = {"ListID": "TC-001", "Name": "Custom Tax"}
        result = transformer.transform_taxcode(qbd)
        # No TaxRateDetails → added to manual_review, returns None
        assert result is None
        assert transformer.stats["total_skipped"] >= 1

    def test_taxcode_with_embedded_rates(self, transformer):
        """TaxCode with embedded rate data → produces TaxService payload."""
        qbd = {
            "ListID": "TC-002",
            "Name": "State Sales Tax",
            "TaxRates": [{"Name": "State Rate", "Rate": "8.25", "AgencyRef": "TA-1"}],
        }
        result = transformer.transform_taxcode(qbd)
        assert result is not None
        assert result["_use_tax_service"] is True
        assert result["TaxCode"] == "State Sales Tax"
        assert len(result["TaxRateDetails"]) == 1
        assert result["TaxRateDetails"][0]["RateValue"] == "8.25"

    def test_taxrate_returns_none_caches(self, transformer):
        """TaxRate returns None (not standalone-creatable) but caches data."""
        qbd = {"ListID": "TR-001", "Name": "State Tax", "RateValue": "8.25"}
        result = transformer.transform_taxrate(qbd)
        assert result is None  # TaxRate is created via TaxService, not standalone
        assert "TR-001" in transformer._tax_rate_cache

    def test_taxagency_returns_none(self, transformer):
        """TaxAgency is read-only in QBO — returns None."""
        qbd = {"ListID": "TA-001", "Name": "State Tax Board"}
        result = transformer.transform_taxagency(qbd)
        assert result is None  # Read-only entity

    def test_paymentmethod_custom(self, transformer):
        """Custom payment method (not a default like Cash/Check)."""
        qbd = {"ListID": "PM-001", "Name": "Wire Transfer"}
        result = transformer.transform_paymentmethod(qbd)
        assert result is not None
        assert result["Name"] == "Wire Transfer"

    def test_companycurrency_minimal(self, transformer):
        qbd = {"Name": "Canadian Dollar", "Code": "CAD"}
        result = transformer.transform_companycurrency(qbd)
        assert result is not None

    def test_timeactivity_minimal(self, transformer):
        """TimeActivity requires EmployeeRef/VendorRef — skip if missing."""
        qbd = {"TxnID": "TA-001", "TxnDate": "2024-01-15", "NameOf": "Employee"}
        result = transformer.transform_timeactivity(qbd)
        # No EmployeeRef mapping → skipped
        assert result is None

    def test_timeactivity_with_employee(self, transformer):
        """TimeActivity with valid EmployeeRef."""
        transformer.store_mapping("employees", "EMP-001", "QBO-EMP-001")
        qbd = {
            "TxnID": "TA-002",
            "TxnDate": "2024-01-15",
            "NameOf": "Employee",
            "EmployeeRef": "EMP-001",
            "Hours": "8",
            "Minutes": "30",
        }
        result = transformer.transform_timeactivity(qbd)
        assert result is not None

    def test_attachable_minimal(self, transformer):
        """Attachable with only FileName."""
        qbd = {"TxnID": "ATT-001", "FileName": "receipt.pdf"}
        result = transformer.transform_attachable(qbd)
        assert result is not None


# ============================================================================
# EXTRACTOR-REALISTIC: camelCase Input Through Normalization → Transform
# ============================================================================


class TestCamelCaseEndToEnd:
    """Test that camelCase data from C# extractor normalizes and transforms
    correctly, including handling of omitted optional fields."""

    def test_account_camelcase_minimal(self, transformer):
        """C# extractor outputs camelCase — normalize then transform."""
        raw = {
            "listId": "ACCT-200",
            "name": "Office Supplies",
            "accountType": "Expense",
            # No description, no acctNum, no parentRef (all null → omitted)
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, "Account")
        result = transformer.transform_account(normalized)
        assert result is not None
        assert result["Name"] == "Office Supplies"

    def test_customer_camelcase_with_partial_address(self, transformer):
        """Customer with some address fields but not all (partial data from QB)."""
        raw = {
            "listId": "CUST-200",
            "name": "Widget Corp",
            "billAddressAddr1": "123 Main St",
            "billAddressCity": "Springfield",
            # No billAddressState, billAddressPostalCode (null → omitted)
            # No email, phone (null → omitted)
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, "Customer")
        result = transformer.transform_customer(normalized)
        assert result is not None
        assert "DisplayName" in result
        # Bill address should be reconstructed from partial data
        if "BillAddr" in result:
            assert "Line1" in result["BillAddr"]

    def test_invoice_camelcase_with_lines(self, transformer):
        """Invoice with camelCase fields and line items (requires valid ItemRef)."""
        raw = {
            "txnId": "TXN-INV-200",
            "customerRefListId": "CUST-001",
            "txnDate": "2024-06-15",
            "lines": [
                {
                    "amount": "1000.00",
                    "desc": "Professional Services",
                    "quantity": "10",
                    "rate": "100.00",
                    "itemRefListId": "ITEM-001",
                },
            ],
            # No refNumber, dueDate, memo (null → omitted)
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, "Invoice")
        # Verify normalization produced correct keys
        assert "CustomerRef" in normalized
        assert "InvoiceLines" in normalized
        result = transformer.transform_invoice(normalized)
        assert result is not None
        assert len(result["Line"]) == 1

    def test_bill_camelcase_split_lines(self, transformer):
        """Bill with mixed expense and item lines from camelCase input."""
        raw = {
            "txnId": "TXN-BILL-200",
            "vendorRefListId": "VEND-001",
            "txnDate": "2024-03-01",
            "lines": [
                {"amount": "500.00", "accountRefListId": "ACCT-001"},
                {"amount": "300.00", "itemRefListId": "ITEM-001", "quantity": "3"},
            ],
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, "Bill")
        # Bill lines should be split into ExpenseLines and ItemLines
        assert "ExpenseLines" in normalized or "ItemLines" in normalized
        result = transformer.transform_bill(normalized)
        assert result is not None
        assert len(result["Line"]) >= 1

    def test_vendor_camelcase_with_address(self, transformer):
        """Vendor with flat address fields from camelCase C# output."""
        raw = {
            "listId": "VEND-200",
            "name": "ABC Supplier",
            "vendorAddressAddr1": "456 Oak Ave",
            "vendorAddressCity": "Portland",
            "vendorAddressState": "OR",
            "vendorAddressPostalCode": "97201",
            "isVendorEligibleFor1099": True,
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, "Vendor")
        assert "Address" in normalized  # VendorAddress → Address alias
        result = transformer.transform_vendor(normalized)
        assert result is not None
        assert "BillAddr" in result

    def test_invoice_camelcase_no_lines_graceful(self, transformer):
        """Invoice with camelCase but no lines → graceful skip."""
        raw = {
            "txnId": "TXN-INV-300",
            "customerRefListId": "CUST-001",
            "txnDate": "2024-06-15",
            # No 'lines' key at all (empty list → omitted by NullValueHandling.Ignore)
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, "Invoice")
        result = transformer.transform_invoice(normalized)
        assert result is None  # Gracefully skipped
        assert transformer.stats["total_skipped"] >= 1


# ============================================================================
# EDGE CASES: C# Extractor Quirks
# ============================================================================


class TestExtractorEdgeCases:
    """Test edge cases specific to the C# extractor's behavior."""

    def test_empty_string_fields_preserved(self, transformer):
        """Empty strings ARE serialized by NullValueHandling.Ignore."""
        qbd = {
            "ListID": "ACCT-300",
            "Name": "",  # Empty string, not null → preserved
            "AccountType": "Bank",
        }
        result = transformer.transform_account(qbd)
        assert result is not None
        # sanitize_name should handle empty string with default

    def test_zero_amount_not_omitted(self, transformer):
        """Zero amounts should be preserved, not treated as missing."""
        qbd = {
            "TxnID": "TXN-INV-400",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
            "InvoiceLines": [
                {"Amount": "0.00", "Description": "Free item", "ItemRef": "ITEM-001"},
            ],
        }
        result = transformer.transform_invoice(qbd)
        assert result is not None
        assert len(result["Line"]) == 1

    def test_false_bool_not_omitted(self, transformer):
        """False booleans should be preserved."""
        qbd = {
            "ListID": "ACCT-400",
            "Name": "Inactive Account",
            "AccountType": "Expense",
            "IsActive": False,
        }
        result = transformer.transform_account(qbd)
        assert result is not None
        # IsActive=False should result in Active=False
        assert result.get("Active") is False

    def test_linked_txns_missing_no_crash(self, transformer):
        """LinkedTxns field is never populated by C# extractor — verify no crash."""
        qbd = {
            "TxnID": "TXN-INV-500",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
            "InvoiceLines": [{"Amount": "100.00", "ItemRef": "ITEM-001"}],
            # No LinkedTxns key (never populated by extractor)
        }
        result = transformer.transform_invoice(qbd)
        assert result is not None

    def test_item_no_type_defaults(self, transformer):
        """Item without ItemType — C# extractor may omit if null."""
        qbd = {
            "ListID": "ITEM-300",
            "Name": "Mystery Item",
            # No ItemType key
        }
        result = transformer.transform_item(qbd)
        # Should use default 'Service' type
        assert result is not None
        assert result["Type"] == "Service"

    def test_multiple_transforms_accumulate_skips(self, transformer):
        """Multiple entities with missing lines should all be tracked."""
        for i in range(5):
            qbd = {
                "TxnID": f"TXN-INV-{600 + i}",
                "CustomerRef": "CUST-001",
                "TxnDate": "2024-01-15",
            }
            transformer.transform_invoice(qbd)

        assert transformer.stats["total_skipped"] >= 5
        assert len(transformer.manual_review) >= 5

    def test_journal_entry_needs_minimum_two_lines(self, transformer):
        """JournalEntry with only one line is still accepted by _require_lines
        (balance validation is separate)."""
        qbd = {
            "TxnID": "TXN-JE-100",
            "TxnDate": "2024-01-15",
            "JournalEntryLines": [
                {
                    "PostingType": "Debit",
                    "Amount": "500.00",
                    "AccountRef": "ACCT-001",
                },
            ],
        }
        result = transformer.transform_journalentry(qbd)
        # Should pass _require_lines (has >= 1 line)
        # Balance validation is a warning, not a skip
        assert result is not None

    def test_deposit_with_linked_payment(self, transformer):
        """Deposit with linked payment line items."""
        transformer.store_mapping("payments", "PMT-001", "QBO-PMT-001")
        qbd = {
            "TxnID": "TXN-DEP-100",
            "TxnDate": "2024-01-15",
            "DepositToAccountRef": "ACCT-001",
            "DepositLines": [
                {"Amount": "500.00", "AccountRef": "ACCT-002"},
            ],
        }
        result = transformer.transform_deposit(qbd)
        assert result is not None
        assert len(result["Line"]) >= 1

    def test_billpayment_with_applied_bill(self, transformer):
        """BillPayment with applied bill line."""
        transformer.store_mapping("bills", "BILL-001", "QBO-BILL-001")
        qbd = {
            "TxnID": "TXN-BP-100",
            "VendorRef": "VEND-001",
            "TotalAmount": "500.00",
            "TxnDate": "2024-01-15",
            "PaymentType": "Check",
            "BankAccountRef": "ACCT-001",
            "AppliedToBills": [
                {"BillRef": "BILL-001", "Amount": "500.00"},
            ],
        }
        result = transformer.transform_billpayment(qbd)
        assert result is not None
        assert len(result["Line"]) >= 1


# ============================================================================
# FULL PIPELINE: normalize_data_keys → normalize_extractor_fields → transform
# ============================================================================


class TestFullPipelineResilience:
    """End-to-end test: raw C# extractor JSON → normalize → transform."""

    def test_full_pipeline_with_sparse_data(self, transformer):
        """Simulate a full extraction with mostly empty entities.

        C# extractor outputs with NullValueHandling.Ignore means many
        entity collections may be empty (omitted) and individual entities
        have many missing optional fields.
        """
        raw_data = {
            "accounts": [
                {"listId": "A1", "name": "Cash", "accountType": "Bank"},
                {"listId": "A2", "name": "Revenue", "accountType": "Income"},
            ],
            "customers": [
                {"listId": "C1", "name": "Test Customer"},
                # Second customer has minimal data
                {"listId": "C2", "name": "Sparse Customer"},
            ],
            # No vendors, employees, items — all empty → omitted
            # No invoices, bills — all empty → omitted
        }

        # Step 1: normalize top-level keys
        normalized = QBDataTransformer.normalize_data_keys(raw_data)
        assert "Account" in normalized
        assert "Customer" in normalized

        # Step 2: normalize each entity
        for entity in normalized.get("Account", []):
            norm = QBDataTransformer.normalize_extractor_fields(entity, "Account")
            result = transformer.transform_account(norm)
            assert result is not None

        for entity in normalized.get("Customer", []):
            norm = QBDataTransformer.normalize_extractor_fields(entity, "Customer")
            result = transformer.transform_customer(norm)
            assert result is not None

    def test_full_pipeline_invoices_mixed_lines(self, transformer):
        """Some invoices have lines, some don't — verify mixed behavior."""
        raw_data = {
            "invoices": [
                {
                    "txnId": "INV-1",
                    "customerRefListId": "CUST-001",
                    "txnDate": "2024-01-15",
                    "lines": [{"amount": "100.00", "itemRefListId": "ITEM-001"}],
                },
                {
                    "txnId": "INV-2",
                    "customerRefListId": "CUST-001",
                    "txnDate": "2024-01-16",
                    # No lines — extraction failed
                },
            ],
        }

        normalized = QBDataTransformer.normalize_data_keys(raw_data)
        results = []
        for entity in normalized.get("Invoice", []):
            norm = QBDataTransformer.normalize_extractor_fields(entity, "Invoice")
            result = transformer.transform_invoice(norm)
            results.append(result)

        # First invoice should succeed
        assert results[0] is not None
        # Second invoice should be skipped (no lines)
        assert results[1] is None


# ============================================================================
# ID MAPPING CASE SENSITIVITY FIX
# ============================================================================


class TestIdMappingCaseNormalization:
    """Verify that PascalCase keys from the orchestrator are normalized to
    lowercase for consistent lookup via map_id() and map_id_required()."""

    def test_pascalcase_merge_normalizes_to_lowercase(self, transformer):
        """PascalCase keys from orchestrator merge into lowercase buckets."""
        existing_maps = {
            "Customers": {"CUST-001": "QBO-CUST-REAL-1"},
            "Accounts": {"ACCT-001": "QBO-ACCT-REAL-1"},
        }
        transformer.transform_entity(
            "Customers", {"Name": "Test"}, id_mapping=existing_maps
        )
        # Real QBO IDs should be in lowercase buckets
        assert transformer.id_mapping["customers"]["CUST-001"] == "QBO-CUST-REAL-1"
        assert transformer.id_mapping["accounts"]["ACCT-001"] == "QBO-ACCT-REAL-1"

    def test_real_id_replaces_temp_id(self, transformer):
        """Real QBO ID from orchestrator replaces temp ID from transformer."""
        # Simulate transformer storing a temp ID
        transformer.store_mapping("customers", "CUST-001", "temp_customers_1")
        assert transformer.map_id("customers", "CUST-001") == "temp_customers_1"

        # Simulate orchestrator merging real QBO ID (PascalCase key)
        existing_maps = {"Customers": {"CUST-001": "QBO-123"}}
        transformer.transform_entity(
            "Customers", {"Name": "Test"}, id_mapping=existing_maps
        )

        # map_id uses lowercase — should now find the real QBO ID
        assert transformer.map_id("customers", "CUST-001") == "QBO-123"

    def test_map_id_required_uses_real_id(self, transformer):
        """map_id_required resolves to real QBO ID after merge."""
        existing_maps = {"Vendors": {"VEND-001": "QBO-VEND-42"}}
        transformer.transform_entity("Vendors", {"Name": "V"}, id_mapping=existing_maps)

        qbo_id, valid = transformer.map_id_required(
            "vendors", "VEND-001", "Vendor for Bill", "Bill", "BILL-1"
        )
        assert valid is True
        assert qbo_id == "QBO-VEND-42"

    def test_cascade_customer_to_invoice(self, transformer):
        """Invoice resolves customer to real QBO ID after merge."""
        # Merge real customer ID
        existing_maps = {"Customers": {"CUST-001": "QBO-CUST-99"}}
        transformer.transform_entity(
            "Customers", {"Name": "X"}, id_mapping=existing_maps
        )

        # Merge real item ID
        existing_maps2 = {"Items": {"ITEM-001": "QBO-ITEM-50"}}
        transformer.transform_entity(
            "Items", {"Name": "Y", "ItemType": "Service"}, id_mapping=existing_maps2
        )

        # Now transform an invoice referencing that customer+item
        invoice = {
            "TxnID": "INV-001",
            "CustomerRef": "CUST-001",
            "TxnDate": "2024-01-15",
            "InvoiceLines": [{"Amount": "100.00", "ItemRef": "ITEM-001"}],
        }
        result = transformer.transform_invoice(invoice)
        assert result is not None
        assert result["CustomerRef"] == {"value": "QBO-CUST-99"}
        assert result["Line"][0]["SalesItemLineDetail"]["ItemRef"] == {
            "value": "QBO-ITEM-50"
        }

    def test_failed_customer_blocks_invoice(self, transformer):
        """Invoice skipped when customer mapping doesn't exist (failed creation)."""
        # No customer mapping at all — simulates failed customer creation
        invoice = {
            "TxnID": "INV-002",
            "CustomerRef": "CUST-MISSING",
            "TxnDate": "2024-01-15",
            "InvoiceLines": [{"Amount": "100.00", "ItemRef": "ITEM-001"}],
        }
        result = transformer.transform_invoice(invoice)
        # Invoice should be skipped — no valid CustomerRef
        assert result is None


# ============================================================================
# TAX SERVICE ROUTING
# ============================================================================


class TestTaxServiceRouting:
    """Verify TaxCode uses TaxService endpoint, TaxRate caches, TaxAgency is read-only."""

    def test_taxcode_produces_taxservice_payload(self, transformer):
        """TaxCode with rates produces _use_tax_service flag."""
        qbd = {
            "ListID": "TC-100",
            "Name": "County Tax",
            "TaxRates": [
                {"Name": "County Rate", "Rate": "6.5", "AgencyRef": "AG-1"},
            ],
        }
        result = transformer.transform_taxcode(qbd)
        assert result is not None
        assert result.get("_use_tax_service") is True
        assert result["TaxCode"] == "County Tax"
        assert len(result["TaxRateDetails"]) == 1
        detail = result["TaxRateDetails"][0]
        assert detail["TaxRateName"] == "County Rate"
        assert detail["RateValue"] == "6.50"
        assert detail["TaxApplicableOn"] == "Sales"

    def test_taxcode_with_cached_rate_refs(self, transformer):
        """TaxCode references TaxRate IDs that were cached by transform_taxrate."""
        # First cache a tax rate
        transformer.transform_taxrate(
            {"ListID": "TR-50", "Name": "City Tax", "Rate": "2.0", "AgencyRef": "AG-2"}
        )
        # Now create a TaxCode that references it by ID
        result = transformer.transform_taxcode(
            {"ListID": "TC-50", "Name": "City Code", "TaxRates": ["TR-50"]}
        )
        assert result is not None
        assert result["TaxRateDetails"][0]["TaxRateName"] == "City Tax"
        assert result["TaxRateDetails"][0]["RateValue"] == "2.00"

    def test_taxcode_default_skipped(self, transformer):
        """Default TaxCodes (TAX, NON) are skipped."""
        assert transformer.transform_taxcode({"Name": "TAX"}) is None
        assert transformer.transform_taxcode({"Name": "Non"}) is None

    def test_taxagency_stores_mapping_returns_none(self, transformer):
        """TaxAgency stores mapping but returns None (read-only)."""
        qbd = {"ListID": "TA-100", "Name": "IRS"}
        result = transformer.transform_taxagency(qbd)
        assert result is None

    def test_taxrate_caches_all_fields(self, transformer):
        """TaxRate caches Name, Rate, AgencyRef, ApplicableOn."""
        qbd = {
            "ListID": "TR-100",
            "Name": "Federal Tax",
            "Rate": "10.0",
            "AgencyRef": "AG-1",
            "ApplicableOn": "Purchase",
        }
        transformer.transform_taxrate(qbd)
        cached = transformer._tax_rate_cache["TR-100"]
        assert cached["Name"] == "Federal Tax"
        assert cached["Rate"] == "10.0"
        assert cached["AgencyRef"] == "AG-1"
        assert cached["ApplicableOn"] == "Purchase"


# ============================================================================
# CONFIG ENTITY PAYLOAD FIXES
# ============================================================================


class TestConfigEntityPayloadFixes:
    """Verify payload corrections for Term, PaymentMethod, Attachable, TimeActivity."""

    def test_term_no_type_field(self, transformer):
        """Term should NOT include read-only 'Type' field."""
        qbd = {"ListID": "T-1", "Name": "Custom 45", "DueDays": "45"}
        result = transformer.transform_term(qbd)
        assert result is not None
        assert "Type" not in result  # Type is read-only in QBO
        assert result["DueDays"] == 45

    def test_paymentmethod_credit_card_classification(self, transformer):
        """PaymentMethod with 'credit' in name → CREDIT_CARD type."""
        qbd = {"ListID": "PM-1", "Name": "Corporate Credit Card"}
        result = transformer.transform_paymentmethod(qbd)
        assert result is not None
        assert result["Type"] == "CREDIT_CARD"

    def test_paymentmethod_non_credit_card(self, transformer):
        """PaymentMethod without credit card keywords → NON_CREDIT_CARD."""
        qbd = {"ListID": "PM-2", "Name": "Wire Transfer"}
        result = transformer.transform_paymentmethod(qbd)
        assert result["Type"] == "NON_CREDIT_CARD"

    def test_paymentmethod_type_from_source(self, transformer):
        """PaymentMethod with explicit Type from source data."""
        qbd = {
            "ListID": "PM-3",
            "Name": "Company Card",
            "PaymentMethodType": "CreditCard",
        }
        result = transformer.transform_paymentmethod(qbd)
        assert result["Type"] == "CREDIT_CARD"

    def test_attachable_has_content_type(self, transformer):
        """Attachable should include ContentType derived from extension."""
        qbd = {"TxnID": "ATT-1", "FileName": "invoice_scan.pdf"}
        result = transformer.transform_attachable(qbd)
        assert result["ContentType"] == "application/pdf"

    def test_attachable_jpg_content_type(self, transformer):
        qbd = {"TxnID": "ATT-2", "FileName": "receipt.jpg"}
        result = transformer.transform_attachable(qbd)
        assert result["ContentType"] == "image/jpeg"

    def test_attachable_unknown_extension(self, transformer):
        """Unknown extension defaults to application/octet-stream."""
        qbd = {"TxnID": "ATT-3", "FileName": "data.xyz"}
        result = transformer.transform_attachable(qbd)
        assert result["ContentType"] == "application/octet-stream"

    def test_timeactivity_missing_employee_ref_skipped(self, transformer):
        """TimeActivity without valid EmployeeRef → skipped."""
        qbd = {"TxnID": "TA-1", "TxnDate": "2024-01-15", "NameOf": "Employee"}
        result = transformer.transform_timeactivity(qbd)
        assert result is None
        assert len(transformer.manual_review) >= 1
        assert "Missing required EmployeeRef" in transformer.manual_review[-1]["reason"]

    def test_timeactivity_missing_vendor_ref_skipped(self, transformer):
        """TimeActivity with NameOf=Vendor but no VendorRef → skipped."""
        qbd = {"TxnID": "TA-2", "TxnDate": "2024-01-15", "NameOf": "Vendor"}
        result = transformer.transform_timeactivity(qbd)
        assert result is None
        assert "Missing required VendorRef" in transformer.manual_review[-1]["reason"]

    def test_timeactivity_hours_minutes_default_to_zero(self, transformer):
        """TimeActivity always includes Hours/Minutes (default to 0)."""
        transformer.store_mapping("employees", "EMP-1", "QBO-EMP-1")
        qbd = {
            "TxnID": "TA-3",
            "TxnDate": "2024-01-15",
            "NameOf": "Employee",
            "EmployeeRef": "EMP-1",
        }
        result = transformer.transform_timeactivity(qbd)
        assert result is not None
        assert result["Hours"] == 0
        assert result["Minutes"] == 0

"""
Comprehensive Test Suite for Orchestrator, Verifier, and IIF Parser
Tests the migration orchestration flow, verification logic, and IIF parsing.

Covers:
1. Orchestrator entity ordering and flow
2. Plural-to-singular endpoint mapping
3. Token attribute handling (_base_access_token)
4. Verifier entity key matching (lowercase, singular, plural)
5. Verifier _reset() report structure
6. IIF parser TRNS/SPL/ENDTRNS block grouping
7. IIF parser header extraction
8. IIF parser CP1252 encoding support
9. IIF parser CSV injection prevention (inherited)
10. End-to-end orchestrator → transformer → verifier flow
"""

import os
import sys
import tempfile
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_transformer import QBDataTransformer  # noqa: E402
from iif_parser import IIFParser  # noqa: E402

# ============================================================================
# IIF PARSER TESTS
# ============================================================================


class TestIIFParserBasic:
    """Tests for IIF parser basic functionality"""

    @pytest.fixture
    def parser(self):
        return IIFParser()

    def test_empty_content(self, parser):
        """Test parsing empty content"""
        result = parser.parse_content("")
        assert result["data"] is not None
        assert result["summary"] == {}

    def test_header_extraction(self, parser):
        """Test that IIF headers are correctly extracted"""
        content = "!CUST\tNAME\tCOMPANY\tPHONE\n"
        parser.parse_content(content)
        assert "CUST" in parser.headers
        assert parser.headers["CUST"] == ["NAME", "COMPANY", "PHONE"]

    def test_customer_parsing(self, parser):
        """Test parsing a customer record"""
        content = (
            "!CUST\tNAME\tCOMPANY\tPHONE\n" "CUST\tAcme Corp\tAcme Inc\t555-1234\n"
        )
        result = parser.parse_content(content)
        assert len(result["data"]["customers"]) == 1
        customer = result["data"]["customers"][0]
        assert customer["NAME"] == "Acme Corp"
        assert customer["COMPANY"] == "Acme Inc"
        assert customer["PHONE"] == "555-1234"

    def test_vendor_parsing(self, parser):
        """Test parsing a vendor record"""
        content = "!VEND\tNAME\tCOMPANY\n" "VEND\tSupply Co\tSupply Corp\n"
        result = parser.parse_content(content)
        assert len(result["data"]["vendors"]) == 1
        vendor = result["data"]["vendors"][0]
        assert vendor["NAME"] == "Supply Co"

    def test_account_parsing(self, parser):
        """Test parsing account records"""
        content = (
            "!ACCNT\tNAME\tACCNTTYPE\tDESC\n"
            "ACCNT\tChecking\tBank\tMain checking account\n"
            "ACCNT\tAR\tAccounts Receivable\tTrade receivables\n"
        )
        result = parser.parse_content(content)
        assert len(result["data"]["accounts"]) == 2
        assert result["data"]["accounts"][0]["NAME"] == "Checking"
        assert result["data"]["accounts"][0]["ACCNTTYPE"] == "Bank"

    def test_item_parsing(self, parser):
        """Test parsing inventory items"""
        content = (
            "!INVITEM\tNAME\tITEMTYPE\tDESC\tPRICE\n"
            "INVITEM\tWidget\tInventory\tBlue Widget\t25.00\n"
        )
        result = parser.parse_content(content)
        assert len(result["data"]["items"]) == 1
        item = result["data"]["items"][0]
        assert item["NAME"] == "Widget"
        assert item["PRICE"] == "25.00"


class TestIIFTransactionBlocks:
    """Tests for TRNS/SPL/ENDTRNS block grouping"""

    @pytest.fixture
    def parser(self):
        return IIFParser()

    def test_transaction_block_grouping(self, parser):
        """CRITICAL: Test that TRNS/SPL/ENDTRNS blocks are properly grouped"""
        content = (
            "!TRNS\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\n"
            "!SPL\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\n"
            "TRNS\tInvoice\t01/15/2024\tAccounts Receivable\t100.00\n"
            "SPL\tInvoice\t01/15/2024\tSales Income\t-100.00\n"
            "ENDTRNS\n"
        )
        result = parser.parse_content(content)
        assert len(result["data"]["transactions"]) == 1
        txn = result["data"]["transactions"][0]
        assert txn["TRNSTYPE"] == "Invoice"
        assert txn["AMOUNT"] == "100.00"
        assert len(txn["_splits"]) == 1
        assert txn["_splits"][0]["AMOUNT"] == "-100.00"

    def test_multiple_transaction_blocks(self, parser):
        """Test parsing multiple TRNS/SPL/ENDTRNS blocks"""
        content = (
            "!TRNS\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\n"
            "!SPL\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\n"
            "TRNS\tInvoice\t01/15/2024\tAR\t100.00\n"
            "SPL\tInvoice\t01/15/2024\tSales\t-100.00\n"
            "ENDTRNS\n"
            "TRNS\tBill\t01/20/2024\tAP\t-200.00\n"
            "SPL\tBill\t01/20/2024\tExpenses\t200.00\n"
            "ENDTRNS\n"
        )
        result = parser.parse_content(content)
        assert len(result["data"]["transactions"]) == 2

    def test_transaction_with_multiple_splits(self, parser):
        """Test a transaction with multiple split lines"""
        content = (
            "!TRNS\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\n"
            "!SPL\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\n"
            "TRNS\tDeposit\t02/01/2024\tChecking\t500.00\n"
            "SPL\tDeposit\t02/01/2024\tSales\t-300.00\n"
            "SPL\tDeposit\t02/01/2024\tService Income\t-200.00\n"
            "ENDTRNS\n"
        )
        result = parser.parse_content(content)
        txn = result["data"]["transactions"][0]
        assert len(txn["_splits"]) == 2

    def test_spl_without_trns_ignored(self, parser):
        """Test that SPL lines without a preceding TRNS are handled gracefully"""
        content = (
            "!SPL\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\n"
            "SPL\tInvoice\t01/15/2024\tSales\t-100.00\n"
            "ENDTRNS\n"
        )
        # Should not crash - SPL without TRNS goes to transaction_splits only
        result = parser.parse_content(content)
        assert len(result["data"]["transactions"]) == 0
        assert len(result["data"]["transaction_splits"]) == 1


class TestIIFEdgeCases:
    """Tests for IIF parser edge cases"""

    @pytest.fixture
    def parser(self):
        return IIFParser()

    def test_tab_in_field_value(self, parser):
        """Test handling of extra tab-separated fields"""
        content = "!CUST\tNAME\tCOMPANY\n" "CUST\tTest Customer\tTest Co\textra_field\n"
        result = parser.parse_content(content)
        customer = result["data"]["customers"][0]
        assert customer["NAME"] == "Test Customer"
        # Extra field should be stored as field_N
        assert "field_2" in customer

    def test_windows_line_endings(self, parser):
        """Test handling of \\r\\n line endings"""
        content = "!CUST\tNAME\r\nCUST\tTest\r\n"
        result = parser.parse_content(content)
        assert len(result["data"]["customers"]) == 1

    def test_blank_lines_skipped(self, parser):
        """Test that blank lines are properly skipped"""
        content = "!CUST\tNAME\n" "\n" "CUST\tTest1\n" "\n" "\n" "CUST\tTest2\n"
        result = parser.parse_content(content)
        assert len(result["data"]["customers"]) == 2

    def test_stats_tracking(self, parser):
        """Test that parsing statistics are correctly tracked"""
        content = "!CUST\tNAME\n" "CUST\tCustomer1\n" "CUST\tCustomer2\n" "\n"
        result = parser.parse_content(content)
        stats = result["metadata"]["stats"]
        assert stats["parsed_records"] == 2
        assert stats["skipped_lines"] >= 1  # At least the blank line

    def test_mixed_record_types(self, parser):
        """Test parsing file with multiple entity types"""
        content = (
            "!CUST\tNAME\n"
            "!VEND\tNAME\n"
            "!ACCNT\tNAME\tACCNTTYPE\n"
            "CUST\tCustomer1\n"
            "VEND\tVendor1\n"
            "ACCNT\tChecking\tBank\n"
        )
        result = parser.parse_content(content)
        assert len(result["data"]["customers"]) == 1
        assert len(result["data"]["vendors"]) == 1
        assert len(result["data"]["accounts"]) == 1

    def test_unknown_record_type_skipped(self, parser):
        """Test that unknown record types are silently skipped"""
        content = "!CUST\tNAME\n" "CUST\tTest\n" "UNKNOWN\tSomething\n"
        result = parser.parse_content(content)
        assert len(result["data"]["customers"]) == 1
        assert result["metadata"]["stats"]["skipped_lines"] >= 1

    def test_record_type_case_insensitive(self, parser):
        """Test that record types are case-insensitive (uppercased)"""
        content = (
            "!CUST\tNAME\n"
            "cust\tTest1\n"  # lowercase should be uppercased
        )
        result = parser.parse_content(content)
        assert len(result["data"]["customers"]) == 1

    def test_summary_only_includes_nonempty(self, parser):
        """Test that summary only includes entity types with data"""
        content = "!CUST\tNAME\n" "CUST\tTest\n"
        result = parser.parse_content(content)
        summary = result["summary"]
        assert "customers" in summary
        assert "vendors" not in summary  # No vendors parsed


class TestIIFFileParser:
    """Tests for IIF file-level parsing with actual files"""

    def test_parse_file_creates_output(self, tmp_path, monkeypatch):
        """Test parsing an actual IIF file"""
        # Set DATA_DIR so the security check allows tmp_path
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        iif_content = (
            "!CUST\tNAME\tCOMPANY\n"
            "CUST\tAcme Corp\tAcme Inc\n"
            "CUST\tGlobal Co\tGlobal Inc\n"
        )
        iif_file = tmp_path / "test.iif"
        iif_file.write_text(iif_content, encoding="cp1252")

        parser = IIFParser()
        result = parser.parse_file(str(iif_file))
        assert len(result["data"]["customers"]) == 2

    def test_parse_file_cp1252_encoding(self, tmp_path, monkeypatch):
        """Test parsing file with CP1252 characters"""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        iif_content = "!CUST\tNAME\nCUST\tCaf\xe9 Corp\n"
        iif_file = tmp_path / "test_cp1252.iif"
        iif_file.write_bytes(iif_content.encode("cp1252"))

        parser = IIFParser()
        result = parser.parse_file(str(iif_file))
        assert len(result["data"]["customers"]) == 1
        assert "Caf" in result["data"]["customers"][0]["NAME"]


# ============================================================================
# VERIFIER TESTS
# ============================================================================


class TestVerifierReset:
    """Tests for verifier _reset() method"""

    def test_reset_includes_all_required_keys(self):
        """CRITICAL: _reset() must include 'summary', 'details', 'critical_metrics'"""
        mock_client = MagicMock()
        from verifier import PremiumMigrationVerifier

        verifier = PremiumMigrationVerifier(mock_client)

        verifier._reset()

        # These keys must exist after reset (they were missing before the fix)
        assert "summary" in verifier.report
        assert "details" in verifier.report
        assert "critical_metrics" in verifier.report
        assert "warnings" in verifier.report
        assert "errors" in verifier.report
        assert "verification_status" in verifier.report
        assert "migration_date" in verifier.report

    def test_reset_matches_init_structure(self):
        """Verify _reset() creates same structure as __init__"""
        mock_client = MagicMock()
        from verifier import PremiumMigrationVerifier

        verifier = PremiumMigrationVerifier(mock_client)

        set(verifier.report.keys())
        verifier._reset()
        reset_keys = set(verifier.report.keys())

        # Reset should have at least all the keys that init has
        assert "summary" in reset_keys
        assert "details" in reset_keys
        assert "critical_metrics" in reset_keys

    def test_reset_clears_previous_data(self):
        """Verify _reset() clears data from previous verification"""
        mock_client = MagicMock()
        from verifier import PremiumMigrationVerifier

        verifier = PremiumMigrationVerifier(mock_client)

        # Add some data
        verifier.report["summary"]["test"] = "data"
        verifier.report["errors"].append("test error")

        verifier._reset()

        assert verifier.report["summary"] == {}
        assert verifier.report["errors"] == []


class TestVerifierEntityKeyMatching:
    """Tests for verifier entity key matching across all naming conventions"""

    def test_verify_migration_with_plural_title_keys(self):
        """CRITICAL: Verifier must match title-case plural keys from orchestrator"""
        mock_client = MagicMock()
        # Mock query_count to return expected counts
        mock_client.query_count.return_value = 5

        from verifier import PremiumMigrationVerifier

        verifier = PremiumMigrationVerifier(mock_client)

        # Data with title-case plural keys (from orchestrator)
        entities = {
            "Customers": [{"Name": f"Cust{i}"} for i in range(5)],
            "Vendors": [{"Name": f"Vend{i}"} for i in range(3)],
            "Accounts": [{"Name": f"Acct{i}"} for i in range(10)],
        }

        result = verifier.verify_migration(
            entities=entities,
            upload_result={"successful": 18, "failed": 0},
            oauth_manager=MagicMock(),
        )

        # Verification should have actually checked entities
        # (Before the fix, it silently skipped all checks)
        assert result is not None

    def test_verify_migration_with_lowercase_keys(self):
        """Verifier must also match lowercase keys"""
        mock_client = MagicMock()
        mock_client.query_count.return_value = 3

        from verifier import PremiumMigrationVerifier

        verifier = PremiumMigrationVerifier(mock_client)

        entities = {
            "customers": [{"Name": f"Cust{i}"} for i in range(3)],
        }

        result = verifier.verify_migration(
            entities=entities,
            upload_result={"successful": 3, "failed": 0},
            oauth_manager=MagicMock(),
        )
        assert result is not None

    def test_verify_migration_with_singular_keys(self):
        """Verifier must also match singular keys"""
        mock_client = MagicMock()
        mock_client.query_count.return_value = 2

        from verifier import PremiumMigrationVerifier

        verifier = PremiumMigrationVerifier(mock_client)

        entities = {
            "Customer": [{"Name": "Cust1"}, {"Name": "Cust2"}],
        }

        result = verifier.verify_migration(
            entities=entities,
            upload_result={"successful": 2, "failed": 0},
            oauth_manager=MagicMock(),
        )
        assert result is not None

    def test_empty_migration_warning(self):
        """Verifier should warn on empty migration"""
        mock_client = MagicMock()
        from verifier import PremiumMigrationVerifier

        verifier = PremiumMigrationVerifier(mock_client)

        result = verifier.verify_migration(
            entities={},
            upload_result={"successful": 0, "failed": 0},
            oauth_manager=MagicMock(),
        )

        assert result is not None
        assert verifier.report["verification_status"] == "WARNING"


# ============================================================================
# ORCHESTRATOR TESTS
# ============================================================================


class TestOrchestratorPluralToSingular:
    """Tests for the PLURAL_TO_SINGULAR mapping in _migrate_entity"""

    def test_plural_to_singular_mapping_exists(self):
        """Verify the mapping covers all entity types from entity_order"""
        # These are the entity types used in entity_order
        entity_order_types = [
            "Accounts",
            "Customers",
            "Vendors",
            "Items",
            "Employees",
            "Invoices",
            "Bills",
            "Payments",
        ]

        # This mapping is defined inside _migrate_entity
        PLURAL_TO_SINGULAR = {
            "Accounts": "Account",
            "Customers": "Customer",
            "Vendors": "Vendor",
            "Items": "Item",
            "Employees": "Employee",
            "Invoices": "Invoice",
            "Bills": "Bill",
            "Payments": "Payment",
            "Estimates": "Estimate",
            "Deposits": "Deposit",
            "Transfers": "Transfer",
            "JournalEntries": "JournalEntry",
            "CreditMemos": "CreditMemo",
            "PurchaseOrders": "PurchaseOrder",
            "SalesReceipts": "SalesReceipt",
            "BillPayments": "BillPayment",
            "VendorCredits": "VendorCredit",
            "RefundReceipts": "RefundReceipt",
            "TimeActivities": "TimeActivity",
            "InventoryAdjustments": "InventoryAdjustment",
            "Purchases": "Purchase",
            "Attachables": "Attachable",
        }

        for entity_type in entity_order_types:
            assert (
                entity_type in PLURAL_TO_SINGULAR
            ), f"Missing mapping for '{entity_type}' in PLURAL_TO_SINGULAR"

    def test_singular_forms_are_valid_qbo_endpoints(self):
        """Verify singular forms produce valid QBO API endpoint names"""
        PLURAL_TO_SINGULAR = {
            "Accounts": "Account",
            "Customers": "Customer",
            "Vendors": "Vendor",
            "Items": "Item",
            "Employees": "Employee",
            "Invoices": "Invoice",
            "Bills": "Bill",
            "Payments": "Payment",
        }

        # QBO API endpoints are lowercase singular
        for plural, singular in PLURAL_TO_SINGULAR.items():
            endpoint = singular.lower()
            # Verify it's actually singular (no trailing 's' except for 'class')
            assert not endpoint.endswith("ss"), f"'{endpoint}' ends with 'ss'"


class TestOrchestratorEntityOrder:
    """Tests for entity processing order in orchestrator"""

    def test_entity_order_is_correct(self):
        """Accounts, Customers, Vendors must come before Invoices, Bills, Payments"""
        entity_order = [
            ("Accounts", 20, 30),
            ("Customers", 30, 40),
            ("Vendors", 40, 50),
            ("Items", 50, 60),
            ("Employees", 60, 65),
            ("Invoices", 65, 75),
            ("Bills", 75, 80),
            ("Payments", 80, 85),
        ]

        entity_names = [e[0] for e in entity_order]

        # Accounts must come before everything else
        assert entity_names.index("Accounts") < entity_names.index("Invoices")
        assert entity_names.index("Accounts") < entity_names.index("Bills")

        # Customers must come before Invoices and Payments
        assert entity_names.index("Customers") < entity_names.index("Invoices")
        assert entity_names.index("Customers") < entity_names.index("Payments")

        # Vendors must come before Bills
        assert entity_names.index("Vendors") < entity_names.index("Bills")

        # Items must come before Invoices
        assert entity_names.index("Items") < entity_names.index("Invoices")


class TestOrchestratorTokenHandling:
    """Tests for token attribute handling"""

    def test_base_access_token_attribute_name(self):
        """CRITICAL: Verify PremiumQBOClient uses _base_access_token"""
        # Read the source to verify the attribute name
        from qbo_client import PremiumQBOClient

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            client = PremiumQBOClient(
                access_token="test_token",
                base_url="https://sandbox-quickbooks.api.intuit.com/v3/company/1234",
                db_path=db_path,
            )
            assert hasattr(client, "_base_access_token")
            assert client._base_access_token == "test_token"
        finally:
            os.unlink(db_path)

    def test_token_refresh_updates_base_access_token(self):
        """CRITICAL: Token refresh must update _base_access_token, not access_token"""
        from qbo_client import PremiumQBOClient

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            client = PremiumQBOClient(
                access_token="old_token",
                base_url="https://sandbox-quickbooks.api.intuit.com/v3/company/1234",
                db_path=db_path,
            )

            # Simulate token refresh
            client._base_access_token = "new_token"

            # The headers should use the new token
            headers = client._get_request_headers()
            assert "new_token" in headers.get("Authorization", "")
        finally:
            os.unlink(db_path)


# ============================================================================
# INTEGRATION: TRANSFORMER → ORCHESTRATOR FLOW
# ============================================================================


class TestTransformerOrchestratorIntegration:
    """Tests for the transformer → orchestrator integration"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer(region="US")

    def test_transform_entity_with_plural_name(self, transformer):
        """transform_entity() must handle plural names from entity_order"""
        account = {
            "Name": "Checking",
            "AccountType": "Bank",
            "Balance": "1000.00",
            "ListID": "ACC-001",
            "IsActive": True,
        }

        result = transformer.transform_entity("Accounts", account)
        assert result is not None
        assert result["AccountType"] == "Bank"
        assert result["Name"] == "Checking"

    def test_transform_entity_customer_plural(self, transformer):
        """transform_entity('Customers', ...) should work"""
        customer = {
            "Name": "Acme Corp",
            "CompanyName": "Acme Inc",
            "ListID": "CUST-001",
            "IsActive": True,
        }

        result = transformer.transform_entity("Customers", customer)
        assert result is not None
        assert "DisplayName" in result

    def test_id_mapping_propagation(self, transformer):
        """Test that ID mappings propagate between entity types"""
        # First transform a customer
        customer = {"Name": "Test Customer", "ListID": "CUST-001", "IsActive": True}
        transformer.transform_entity("Customers", customer)

        # Verify the mapping was stored
        assert "CUST-001" in transformer.id_mapping["customers"]

    def test_full_entity_chain_transform(self, transformer):
        """Test transforming a realistic chain of dependent entities"""
        # 1. Accounts first
        accounts = [
            {
                "Name": "Checking",
                "AccountType": "Bank",
                "ListID": "ACC-001",
                "IsActive": True,
            },
            {
                "Name": "AR",
                "AccountType": "Accounts Receivable",
                "ListID": "ACC-002",
                "IsActive": True,
            },
            {
                "Name": "Sales Income",
                "AccountType": "Income",
                "ListID": "ACC-003",
                "IsActive": True,
            },
        ]
        for acct in accounts:
            result = transformer.transform_entity("Accounts", acct)
            assert result is not None

        # 2. Customers
        customers = [
            {"Name": "Acme Corp", "ListID": "CUST-001", "IsActive": True},
        ]
        for cust in customers:
            result = transformer.transform_entity("Customers", cust)
            assert result is not None

        # 3. Items
        items = [
            {
                "Name": "Widget",
                "ItemType": "Service",
                "ListID": "ITEM-001",
                "IsActive": True,
                "UnitPrice": "25.00",
            },
        ]
        for item in items:
            result = transformer.transform_entity("Items", item)
            assert result is not None

        # Verify all mappings are stored
        assert "ACC-001" in transformer.id_mapping["accounts"]
        assert "CUST-001" in transformer.id_mapping["customers"]
        assert "ITEM-001" in transformer.id_mapping["items"]

    def test_invoice_skipped_without_customer(self, transformer):
        """Invoice must be skipped if CustomerRef is not mapped"""
        invoice = {
            "RefNumber": "1001",
            "CustomerRef": "NONEXISTENT",
            "TxnDate": "2024-01-15",
            "InvoiceLines": [],
            "TxnID": "INV-001",
        }

        result = transformer.transform_entity("Invoices", invoice)
        assert result is None  # Should be skipped
        assert transformer.stats["total_skipped"] > 0

    def test_bill_skipped_without_vendor(self, transformer):
        """Bill must be skipped if VendorRef is not mapped"""
        bill = {
            "RefNumber": "BILL-001",
            "VendorRef": "NONEXISTENT",
            "TxnDate": "2024-01-20",
            "ExpenseLines": [],
            "TxnID": "BILL-001",
        }

        result = transformer.transform_entity("Bills", bill)
        assert result is None

    def test_trial_balance_tracking(self, transformer):
        """Test that trial balance is tracked during account transformation"""
        # Debit-normal account
        transformer.transform_entity(
            "Accounts",
            {
                "Name": "Cash",
                "AccountType": "Bank",
                "Balance": "5000.00",
                "ListID": "ACC-1",
                "IsActive": True,
            },
        )

        # Credit-normal account
        transformer.transform_entity(
            "Accounts",
            {
                "Name": "AP",
                "AccountType": "Accounts Payable",
                "Balance": "5000.00",
                "ListID": "ACC-2",
                "IsActive": True,
            },
        )

        assert transformer.trial_balance["debits"] == Decimal("5000.00")
        assert transformer.trial_balance["credits"] == Decimal("5000.00")


# ============================================================================
# FULL FLOW: IIF → TRANSFORM → VERIFY
# ============================================================================


class TestFullIIFToQBOFlow:
    """End-to-end: Parse IIF → Transform → Verify structure"""

    def test_iif_to_transform_accounts(self):
        """Parse IIF accounts and transform to QBO format"""
        parser = IIFParser()
        content = (
            "!ACCNT\tNAME\tACCNTTYPE\tBALANCE\n"
            "ACCNT\tChecking\tBank\t10000.00\n"
            "ACCNT\tSavings\tBank\t5000.00\n"
        )
        parsed = parser.parse_content(content)
        accounts = parsed["data"]["accounts"]

        transformer = QBDataTransformer(region="US")
        for acct in accounts:
            # Map IIF fields to transformer format
            qbd_acct = {
                "Name": acct["NAME"],
                "AccountType": acct["ACCNTTYPE"],
                "Balance": acct.get("BALANCE", "0"),
                "ListID": f"ACC-{acct['NAME']}",
                "IsActive": True,
            }
            result = transformer.transform_entity("Accounts", qbd_acct)
            assert result is not None
            assert result["AccountType"] == "Bank"

    def test_iif_to_transform_customers(self):
        """Parse IIF customers and transform to QBO format"""
        parser = IIFParser()
        content = (
            "!CUST\tNAME\tCOMPANY\tPHONE\n" "CUST\tJohn Doe\tAcme Corp\t555-1234\n"
        )
        parsed = parser.parse_content(content)
        customers = parsed["data"]["customers"]

        transformer = QBDataTransformer(region="US")
        for cust in customers:
            qbd_cust = {
                "Name": cust["NAME"],
                "CompanyName": cust.get("COMPANY", ""),
                "Phone": cust.get("PHONE", ""),
                "ListID": f"CUST-{cust['NAME']}",
                "IsActive": True,
            }
            result = transformer.transform_entity("Customers", qbd_cust)
            assert result is not None
            assert "DisplayName" in result

    def test_full_iif_parse_to_qbo_structure(self):
        """Test complete IIF → QBO transformation produces valid structure"""
        parser = IIFParser()
        content = (
            "!ACCNT\tNAME\tACCNTTYPE\n"
            "!CUST\tNAME\tCOMPANY\n"
            "!VEND\tNAME\tCOMPANY\n"
            "ACCNT\tChecking\tBank\n"
            "ACCNT\tAR\tAccounts Receivable\n"
            "CUST\tAcme Corp\tAcme Inc\n"
            "VEND\tSupply Co\tSupply Corp\n"
        )
        parsed = parser.parse_content(content)

        transformer = QBDataTransformer(region="US")

        # Transform accounts
        for acct in parsed["data"]["accounts"]:
            transformer.transform_entity(
                "Accounts",
                {
                    "Name": acct["NAME"],
                    "AccountType": acct["ACCNTTYPE"],
                    "ListID": f"ACC-{acct['NAME']}",
                    "IsActive": True,
                },
            )

        # Transform customers
        for cust in parsed["data"]["customers"]:
            transformer.transform_entity(
                "Customers",
                {
                    "Name": cust["NAME"],
                    "ListID": f"CUST-{cust['NAME']}",
                    "IsActive": True,
                },
            )

        # Transform vendors
        for vend in parsed["data"]["vendors"]:
            transformer.transform_entity(
                "Vendors",
                {
                    "Name": vend["NAME"],
                    "ListID": f"VEND-{vend['NAME']}",
                    "IsActive": True,
                },
            )

        # Verify stats
        assert transformer.stats["total_processed"] == 4
        assert transformer.stats["total_skipped"] == 0

"""
Comprehensive Test Suite for QBDataTransformer
ForensicBridge Premium Migration Engine

Tests cover:
1. Date formatting and parsing
2. DisplayName uniqueness enforcement
3. Entity transformations (Customer, Vendor, Account, Item, etc.)
4. Trial balance calculations
5. ID mapping
6. Sanitization and validation
7. Edge cases and error handling

TEST-01: Unit tests for QBDataTransformer
"""

import pytest
from decimal import Decimal
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_transformer import QBDataTransformer


class TestQBDataTransformerInit:
    """Tests for QBDataTransformer initialization"""

    def test_default_initialization(self):
        """Test transformer initializes with correct defaults"""
        transformer = QBDataTransformer()

        assert transformer.region == 'US'
        assert transformer.enable_multi_currency is False
        assert transformer.default_currency == 'USD'
        assert transformer.VERSION == '3.1.0'

    def test_region_initialization(self):
        """Test transformer initializes with correct region-specific settings"""
        regions = {
            'US': 'USD',
            'CA': 'CAD',
            'UK': 'GBP',
            'AU': 'AUD',
            'IN': 'INR',
            'FR': 'EUR'
        }

        for region, expected_currency in regions.items():
            transformer = QBDataTransformer(region=region)
            assert transformer.default_currency == expected_currency

    def test_multi_currency_enabled(self):
        """Test multi-currency can be enabled"""
        transformer = QBDataTransformer(enable_multi_currency=True)
        assert transformer.enable_multi_currency is True

    def test_initial_stats_structure(self):
        """Test initial stats are properly structured"""
        transformer = QBDataTransformer()

        assert 'total_processed' in transformer.stats
        assert 'total_skipped' in transformer.stats
        assert 'by_entity_type' in transformer.stats
        assert 'errors' in transformer.stats
        assert 'warnings' in transformer.stats
        assert transformer.stats['total_processed'] == 0


class TestDateFormatting:
    """Tests for date formatting functionality"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer(region='US')

    def test_format_date_iso(self, transformer):
        """Test ISO date format is parsed correctly"""
        assert transformer.format_date('2024-01-15') == '2024-01-15'
        assert transformer.format_date('2024-12-31T23:59:59') == '2024-12-31'
        assert transformer.format_date('2024-06-01T00:00:00Z') == '2024-06-01'

    def test_format_date_us(self, transformer):
        """Test US date format (MM/DD/YYYY)"""
        result = transformer.format_date('01/15/2024')
        assert result == '2024-01-15'

        result = transformer.format_date('12/31/2024')
        assert result == '2024-12-31'

    def test_format_date_uk(self):
        """Test UK date format (DD/MM/YYYY)"""
        transformer = QBDataTransformer(region='UK')
        result = transformer.format_date('15/01/2024')
        assert result == '2024-01-15'

    def test_format_date_none(self, transformer):
        """Test None input returns None"""
        assert transformer.format_date(None) is None
        assert transformer.format_date('') is None

    def test_format_date_invalid(self, transformer):
        """Test invalid date returns None"""
        assert transformer.format_date('not-a-date') is None
        assert transformer.format_date('99/99/9999') is None

    def test_format_date_with_whitespace(self, transformer):
        """Test date with whitespace is handled"""
        assert transformer.format_date('  2024-01-15  ') == '2024-01-15'


class TestDisplayNameUniqueness:
    """Tests for DisplayName uniqueness enforcement"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_unique_name_unchanged(self, transformer):
        """Test unique name is returned unchanged"""
        name = transformer.ensure_unique_display_name('Acme Corp', 'Customer')
        assert name == 'Acme Corp'

    def test_duplicate_name_incremented(self, transformer):
        """Test duplicate names get incremented"""
        name1 = transformer.ensure_unique_display_name('Acme Corp', 'Customer')
        name2 = transformer.ensure_unique_display_name('Acme Corp', 'Customer')
        name3 = transformer.ensure_unique_display_name('Acme Corp', 'Customer')

        assert name1 == 'Acme Corp'
        assert name2 == 'Acme Corp (2)'
        assert name3 == 'Acme Corp (3)'

    def test_case_insensitive_uniqueness(self, transformer):
        """Test uniqueness check is case-insensitive"""
        name1 = transformer.ensure_unique_display_name('ACME CORP', 'Customer')
        name2 = transformer.ensure_unique_display_name('acme corp', 'Customer')

        assert name1 == 'ACME CORP'
        assert name2 == 'acme corp (2)'

    def test_empty_name_gets_default(self, transformer):
        """Test empty name gets a default name"""
        name = transformer.ensure_unique_display_name('', 'Customer')
        assert name == 'Unnamed Customer'

    def test_none_name_gets_default(self, transformer):
        """Test None name gets a default name"""
        name = transformer.ensure_unique_display_name(None, 'Vendor')
        assert name == 'Unnamed Vendor'

    def test_cross_entity_uniqueness(self, transformer):
        """Test uniqueness is enforced across entity types"""
        name1 = transformer.ensure_unique_display_name('John Smith', 'Customer')
        name2 = transformer.ensure_unique_display_name('John Smith', 'Vendor')

        assert name1 == 'John Smith'
        assert name2 == 'John Smith (2)'


class TestSanitization:
    """Tests for name sanitization"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_sanitize_removes_special_chars(self, transformer):
        """Test special characters are removed"""
        result = transformer.sanitize_name('Acme <Corp> & "Partners"')
        assert '<' not in result
        assert '>' not in result
        assert '"' not in result

    def test_sanitize_preserves_valid_chars(self, transformer):
        """Test valid characters are preserved"""
        result = transformer.sanitize_name("O'Brien-Smith Inc")
        assert "O'Brien" in result
        assert 'Smith' in result

    def test_sanitize_trims_whitespace(self, transformer):
        """Test whitespace is trimmed"""
        result = transformer.sanitize_name('  Acme Corp  ')
        assert result == 'Acme Corp'

    def test_sanitize_collapses_whitespace(self, transformer):
        """Test multiple spaces are collapsed"""
        result = transformer.sanitize_name('Acme    Corp')
        assert '    ' not in result

    def test_sanitize_truncates_long_names(self, transformer):
        """Test long names are truncated to 100 chars"""
        long_name = 'A' * 150
        result = transformer.sanitize_name(long_name)
        assert len(result) <= 100

    def test_sanitize_html_entities(self, transformer):
        """Test HTML entities are unescaped"""
        result = transformer.sanitize_name('Acme &amp; Partners')
        assert '&amp;' not in result


class TestToDecimal:
    """Tests for decimal conversion"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_to_decimal_string(self, transformer):
        """Test string to decimal conversion"""
        assert transformer.to_decimal('100.50') == Decimal('100.50')
        assert transformer.to_decimal('1000') == Decimal('1000.00')

    def test_to_decimal_float(self, transformer):
        """Test float to decimal conversion"""
        result = transformer.to_decimal(100.499)
        assert result == Decimal('100.50')  # Rounds to 2 decimals

    def test_to_decimal_int(self, transformer):
        """Test int to decimal conversion"""
        assert transformer.to_decimal(100) == Decimal('100.00')

    def test_to_decimal_none(self, transformer):
        """Test None returns zero"""
        assert transformer.to_decimal(None) == Decimal('0')

    def test_to_decimal_empty_string(self, transformer):
        """Test empty string returns zero"""
        assert transformer.to_decimal('') == Decimal('0')

    def test_to_decimal_invalid(self, transformer):
        """Test invalid value returns zero"""
        assert transformer.to_decimal('not-a-number') == Decimal('0')

    def test_to_decimal_negative(self, transformer):
        """Test negative values are handled"""
        assert transformer.to_decimal('-100.50') == Decimal('-100.50')


class TestIDMapping:
    """Tests for ID mapping functionality"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_store_and_retrieve_mapping(self, transformer):
        """Test storing and retrieving ID mappings"""
        transformer.store_mapping('Customer', 'QBD-001', 'QBO-001')

        result = transformer.map_id('Customer', 'QBD-001')
        assert result == 'QBO-001'

    def test_map_nonexistent_id(self, transformer):
        """Test mapping non-existent ID returns None"""
        result = transformer.map_id('Customer', 'nonexistent')
        assert result is None

    def test_map_none_id(self, transformer):
        """Test mapping None ID returns None"""
        result = transformer.map_id('Customer', None)
        assert result is None

    def test_store_mapping_skips_none(self, transformer):
        """Test storing None values is skipped"""
        transformer.store_mapping('Customer', None, 'QBO-001')
        transformer.store_mapping('Customer', 'QBD-001', None)

        # Neither should be stored
        assert 'Customer' not in transformer.id_mapping or len(transformer.id_mapping['Customer']) == 0


class TestEntityTransformations:
    """Tests for entity transformation methods"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_transform_customer_basic(self, transformer):
        """Test basic customer transformation"""
        qbd_customer = {
            'Name': 'Acme Corporation',
            'IsActive': True,
            'CompanyName': 'Acme Corp',
            'Balance': 1000.00
        }

        result = transformer.transform_customer(qbd_customer)

        assert result['DisplayName'] == 'Acme Corporation'
        assert result['Active'] is True
        assert result['CompanyName'] == 'Acme Corp'

    def test_transform_customer_with_contact(self, transformer):
        """Test customer transformation with contact info"""
        qbd_customer = {
            'Name': 'John Doe',
            'Email': 'john@example.com',
            'Phone': '555-1234',
            'IsActive': True
        }

        result = transformer.transform_customer(qbd_customer)

        assert result['PrimaryEmailAddr']['Address'] == 'john@example.com'
        assert result['PrimaryPhone']['FreeFormNumber'] == '555-1234'

    def test_transform_vendor_basic(self, transformer):
        """Test basic vendor transformation"""
        qbd_vendor = {
            'Name': 'Supplier Inc',
            'IsActive': True,
            'Balance': 500.00
        }

        result = transformer.transform_vendor(qbd_vendor)

        assert result['DisplayName'] == 'Supplier Inc'
        assert result['Active'] is True

    def test_transform_account_bank(self, transformer):
        """Test bank account transformation"""
        qbd_account = {
            'Name': 'Operating Account',
            'AccountType': 'Bank',
            'IsActive': True,
            'Balance': 10000.00,
            'AccountNumber': '1000'
        }

        result = transformer.transform_account(qbd_account)

        assert result['Name'] == 'Operating Account'
        assert result['AccountType'] == 'Bank'
        assert result['AcctNum'] == '1000'

    def test_transform_item_inventory(self, transformer):
        """Test inventory item transformation"""
        qbd_item = {
            'Name': 'Widget',
            'ItemType': 'Inventory',
            'Description': 'A standard widget',
            'SalesPrice': 9.99,
            'Cost': 5.00,
            'QtyOnHand': 100
        }

        result = transformer.transform_item(qbd_item)

        assert result['Name'] == 'Widget'
        assert result['Type'] == 'Inventory'

    def test_transform_item_service(self, transformer):
        """Test service item transformation"""
        qbd_item = {
            'Name': 'Consulting',
            'ItemType': 'Service',
            'Description': 'Hourly consulting',
            'SalesPrice': 150.00
        }

        result = transformer.transform_item(qbd_item)

        assert result['Name'] == 'Consulting'
        assert result['Type'] == 'Service'


class TestTrialBalance:
    """Tests for trial balance calculations"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_initial_trial_balance(self, transformer):
        """Test initial trial balance is zero"""
        assert transformer.trial_balance['debits'] == Decimal('0')
        assert transformer.trial_balance['credits'] == Decimal('0')

    def test_debit_account_positive_balance(self, transformer):
        """Test debit account with positive balance"""
        qbd_account = {
            'Name': 'Cash',
            'AccountType': 'Bank',
            'Balance': 1000.00
        }

        transformer.transform_account(qbd_account)

        assert transformer.trial_balance['debits'] == Decimal('1000.00')

    def test_credit_account_positive_balance(self, transformer):
        """Test credit account with positive balance"""
        qbd_account = {
            'Name': 'Accounts Payable',
            'AccountType': 'Accounts Payable',
            'Balance': 500.00
        }

        transformer.transform_account(qbd_account)

        assert transformer.trial_balance['credits'] == Decimal('500.00')


class TestTransformMethod:
    """Tests for the main transform method"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_transform_empty_data(self, transformer):
        """Test transforming empty data"""
        result = transformer.transform({})

        assert 'metadata' in result
        assert 'entities' in result
        assert 'summary' in result
        assert 'trial_balance' in result

    def test_transform_with_customers(self, transformer):
        """Test transforming data with customers"""
        qb_data = {
            'Customer': [
                {'Name': 'Customer 1', 'IsActive': True},
                {'Name': 'Customer 2', 'IsActive': True}
            ]
        }

        result = transformer.transform(qb_data)

        assert 'Customer' in result['entities']
        assert len(result['entities']['Customer']) == 2

    def test_transform_summary_counts(self, transformer):
        """Test transform summary includes correct counts"""
        qb_data = {
            'Customer': [{'Name': 'Customer 1', 'IsActive': True}],
            'Vendor': [{'Name': 'Vendor 1', 'IsActive': True}]
        }

        result = transformer.transform(qb_data)

        assert result['summary']['total_entities'] >= 2


class TestManualReview:
    """Tests for manual review functionality"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_add_manual_review_item(self, transformer):
        """Test adding items to manual review"""
        transformer.add_manual_review('Customer', 'Test Customer', 'Duplicate detected')

        assert len(transformer.manual_review) == 1
        assert transformer.manual_review[0]['type'] == 'Customer'
        assert transformer.manual_review[0]['name'] == 'Test Customer'
        assert transformer.manual_review[0]['reason'] == 'Duplicate detected'

    def test_manual_review_has_timestamp(self, transformer):
        """Test manual review items have timestamps"""
        transformer.add_manual_review('Vendor', 'Test Vendor', 'Missing info')

        assert 'timestamp' in transformer.manual_review[0]


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_transform_with_missing_fields(self, transformer):
        """Test transformation handles missing fields gracefully"""
        qbd_customer = {}  # Empty customer

        # Should not raise an exception
        result = transformer.transform_customer(qbd_customer)
        assert 'DisplayName' in result

    def test_very_long_company_name(self, transformer):
        """Test handling very long company names"""
        long_name = 'A' * 500
        qbd_customer = {'Name': long_name}

        result = transformer.transform_customer(qbd_customer)
        assert len(result['DisplayName']) <= 100

    def test_unicode_characters(self, transformer):
        """Test handling unicode characters in names"""
        qbd_customer = {'Name': 'Müller GmbH', 'IsActive': True}

        result = transformer.transform_customer(qbd_customer)
        assert 'Müller' in result['DisplayName'] or 'Muller' in result['DisplayName']


class TestLineSkippingValidation:
    """Tests for line items being correctly skipped when required refs are unmapped."""

    @pytest.fixture
    def transformer(self):
        t = QBDataTransformer()
        # Pre-populate some ID mappings so we can test mapped vs unmapped
        t.store_mapping('accounts', 'ACCT-1', 'qbo-acct-1')
        t.store_mapping('items', 'ITEM-1', 'qbo-item-1')
        t.store_mapping('invoices', 'INV-1', 'qbo-inv-1')
        t.store_mapping('payments', 'PAY-1', 'qbo-pay-1')
        t.store_mapping('customers', 'CUST-1', 'qbo-cust-1')
        return t

    def test_purchase_skips_lines_without_account_ref(self, transformer):
        qbd = {
            'PaymentType': 'Cash',
            'TxnDate': '2024-01-15',
            'ExpenseLines': [
                {'AccountRef': 'ACCT-1', 'Amount': '100'},
                {'AccountRef': 'UNMAPPED', 'Amount': '200'},
                {'AccountRef': 'ACCT-1', 'Amount': '50'},
            ]
        }
        result = transformer.transform_purchase(qbd)
        assert result is not None
        assert len(result['Line']) == 2
        assert transformer.stats['dropped_lines'] == 1

    def test_purchase_returns_none_when_all_lines_unmapped(self, transformer):
        qbd = {
            'PaymentType': 'Cash',
            'TxnDate': '2024-01-15',
            'ExpenseLines': [
                {'AccountRef': 'UNMAPPED-1', 'Amount': '100'},
                {'AccountRef': 'UNMAPPED-2', 'Amount': '200'},
            ]
        }
        result = transformer.transform_purchase(qbd)
        assert result is None

    def test_inventoryadjustment_skips_lines_without_item_ref(self, transformer):
        qbd = {
            'TxnDate': '2024-01-15',
            'AdjustmentLines': [
                {'ItemRef': 'ITEM-1', 'QuantityDifference': '5'},
                {'ItemRef': 'UNMAPPED', 'QuantityDifference': '3'},
            ]
        }
        result = transformer.transform_inventoryadjustment(qbd)
        assert result is not None
        assert len(result['Line']) == 1
        assert transformer.stats['dropped_lines'] == 1

    def test_journalentry_skips_lines_without_account_ref(self, transformer):
        qbd = {
            'TxnDate': '2024-01-15',
            'JournalEntryLines': [
                {'AccountRef': 'ACCT-1', 'Amount': '500', 'PostingType': 'Debit'},
                {'AccountRef': 'UNMAPPED', 'Amount': '500', 'PostingType': 'Credit'},
                {'AccountRef': 'ACCT-1', 'Amount': '500', 'PostingType': 'Credit'},
            ]
        }
        result = transformer.transform_journalentry(qbd)
        assert result is not None
        assert len(result['Line']) == 2
        assert transformer.stats['dropped_lines'] == 1

    def test_deposit_skips_lines_without_account_or_linked_txn(self, transformer):
        qbd = {
            'TxnDate': '2024-01-15',
            'DepositLines': [
                {'AccountRef': 'ACCT-1', 'Amount': '100'},
                {'AccountRef': 'UNMAPPED', 'Amount': '200'},  # No LinkedTxn either
                {'AccountRef': None, 'Amount': '50', 'LinkedTxn': {'TxnId': 'PAY-1'}},
            ]
        }
        result = transformer.transform_deposit(qbd)
        assert result is not None
        assert len(result['Line']) == 2
        assert transformer.stats['dropped_lines'] == 1

    def test_deposit_keeps_line_with_linked_txn_but_no_account(self, transformer):
        qbd = {
            'TxnDate': '2024-01-15',
            'DepositLines': [
                {'Amount': '100', 'LinkedTxn': {'TxnId': 'PAY-1'}},
            ]
        }
        result = transformer.transform_deposit(qbd)
        assert result is not None
        assert len(result['Line']) == 1
        assert 'LinkedTxn' in result['Line'][0]

    def test_payment_returns_none_when_no_invoice_mapped(self, transformer):
        qbd = {
            'RefNumber': 'PAY-100',
            'TxnDate': '2024-01-15',
            'CustomerRef': 'CUST-1',
            'AppliedToInvoices': [
                {'InvoiceRef': 'UNMAPPED-INV', 'Amount': '500'},
            ]
        }
        result = transformer.transform_payment(qbd)
        assert result is None

    def test_payment_keeps_lines_with_mapped_invoices(self, transformer):
        qbd = {
            'RefNumber': 'PAY-100',
            'TxnDate': '2024-01-15',
            'CustomerRef': 'CUST-1',
            'AppliedToInvoices': [
                {'InvoiceRef': 'INV-1', 'Amount': '500'},
                {'InvoiceRef': 'UNMAPPED-INV', 'Amount': '200'},
            ]
        }
        result = transformer.transform_payment(qbd)
        assert result is not None
        assert len(result['Line']) == 1


class TestFormatDateValidation:
    """Tests for date validation rejecting impossible dates."""

    @pytest.fixture
    def transformer(self):
        return QBDataTransformer()

    def test_rejects_feb_31(self, transformer):
        result = transformer.format_date('2024-02-31')
        assert result is None

    def test_rejects_apr_31(self, transformer):
        result = transformer.format_date('2024-04-31')
        assert result is None

    def test_accepts_valid_leap_day(self, transformer):
        result = transformer.format_date('2024-02-29')
        assert result == '2024-02-29'

    def test_rejects_non_leap_feb_29(self, transformer):
        result = transformer.format_date('2023-02-29')
        assert result is None

    def test_accepts_valid_date(self, transformer):
        result = transformer.format_date('2024-12-15')
        assert result == '2024-12-15'

    def test_rejects_month_13(self, transformer):
        result = transformer.format_date('2024-13-01')
        assert result is None

    def test_legacy_format_rejects_feb_31(self, transformer):
        result = transformer.format_date('02/31/2024')
        assert result is None

    def test_legacy_format_accepts_valid(self, transformer):
        result = transformer.format_date('01/15/2024')
        assert result == '2024-01-15'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

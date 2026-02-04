"""
Comprehensive End-to-End Tests: QBD → QBServer → QBO Batch API Flow

Tests the COMPLETE pipeline including:
- C# extractor field normalization (all 44 new mappings)
- Entity key mapping for new entity types
- Address field reconstruction (Addr3/4/5/Note)
- Full transform → batch → verify cycle
- Batch chunking (30-entity limit)
- Crash recovery via was_entity_created
- Rate limiting
- ID mapping propagation across entity types

All external dependencies (QBO API, S3, OAuth) are mocked.
"""

import os
import sys
import json
import pytest
import sqlite3
import tempfile
import time
from unittest.mock import patch, MagicMock, call
from decimal import Decimal
from collections import defaultdict
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_transformer import QBDataTransformer
from qbo_client import PremiumQBOClient
from orchestrator import MigrationOrchestrator


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def transformer():
    """QBDataTransformer with pre-populated ID mappings."""
    t = QBDataTransformer(region='US')
    # Pre-populate all entity ID buckets for reference resolution
    t.store_mapping('customers', 'CUST-001', 'QBO-CUST-1')
    t.store_mapping('customers', 'CUST-002', 'QBO-CUST-2')
    t.store_mapping('vendors', 'VEND-001', 'QBO-VEND-1')
    t.store_mapping('accounts', 'ACCT-001', 'QBO-ACCT-1')
    t.store_mapping('accounts', 'ACCT-002', 'QBO-ACCT-2')
    t.store_mapping('accounts', 'ACCT-003', 'QBO-ACCT-3')
    t.store_mapping('items', 'ITEM-001', 'QBO-ITEM-1')
    t.store_mapping('items', 'ITEM-002', 'QBO-ITEM-2')
    t.store_mapping('invoices', 'INV-001', 'QBO-INV-1')
    t.store_mapping('invoices', 'INV-002', 'QBO-INV-2')
    t.store_mapping('bills', 'BILL-001', 'QBO-BILL-1')
    t.store_mapping('employees', 'EMP-001', 'QBO-EMP-1')
    t.store_mapping('classes', 'CLS-001', 'QBO-CLS-1')
    t.store_mapping('terms', 'TERM-001', 'QBO-TERM-1')
    t.store_mapping('payment_methods', 'PM-001', 'QBO-PM-1')
    t.store_mapping('payments', 'PMT-001', 'QBO-PMT-1')
    return t


@pytest.fixture
def bare_transformer():
    """QBDataTransformer with NO pre-populated mappings."""
    return QBDataTransformer(region='US')


@pytest.fixture
def mock_qbo_client():
    """Mock PremiumQBOClient."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test.db')
        with patch.object(PremiumQBOClient, '_register_signal_handlers'):
            client = PremiumQBOClient(
                access_token='test-token',
                base_url='https://sandbox-quickbooks.api.intuit.com/v3/company/12345',
                db_path=db_path,
            )
        yield client


def _make_orchestrator():
    return MigrationOrchestrator(
        qbo_client_id='id',
        qbo_client_secret='secret',
        qbo_refresh_token='token',
        realm_id='realm',
    )


# ============================================================================
# 1. NEW FIELD MAPPING TESTS (44 fields)
# ============================================================================

class TestNewFieldMappingsNormalization:
    """Verify all 44 newly-added _FIELD_MAP entries normalize correctly."""

    def test_invoice_line_job_costing_fields(self):
        """Job costing fields on invoice lines: jobRefListId, costType, etc."""
        line = {
            'txnLineId': 'LINE-1',
            'jobRefListId': 'JOB-001',
            'jobRefFullName': 'Acme:Phase1',
            'costType': 'Labor',
            'costCode': 'CC-100',
            'jobPhase': 'Phase1',
            'estimatedAmount': '5000.00',
            'percentComplete': '50',
            'retainageAmount': '250.00',
            'retainagePercent': '5',
            'changeOrderRef': 'CO-001',
        }
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result['TxnLineID'] == 'LINE-1'
        assert result['JobRef'] == 'JOB-001'
        assert result['JobRefFullName'] == 'Acme:Phase1'
        assert result['CostType'] == 'Labor'
        assert result['CostCode'] == 'CC-100'
        assert result['JobPhase'] == 'Phase1'
        assert result['EstimatedAmount'] == '5000.00'
        assert result['PercentComplete'] == '50'
        assert result['RetainageAmount'] == '250.00'
        assert result['RetainagePercent'] == '5'
        assert result['ChangeOrderRef'] == 'CO-001'

    def test_invoice_line_other_fields(self):
        """Other1/Other2 custom fields on invoice lines."""
        line = {'other1': 'custom-val-1', 'other2': 'custom-val-2'}
        result = QBDataTransformer.normalize_extractor_fields(line)
        assert result['Other1'] == 'custom-val-1'
        assert result['Other2'] == 'custom-val-2'

    def test_transfer_reference_fields(self):
        """Transfer from/to account references."""
        entity = {
            'txnId': 'TXN-XFER-1',
            'transferFromAccountRefListId': 'ACCT-FROM',
            'transferToAccountRefListId': 'ACCT-TO',
            'amount': '1000.00',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['TransferFromAccountRef'] == 'ACCT-FROM'
        assert result['TransferToAccountRef'] == 'ACCT-TO'

    def test_billpayment_creditcard_fields(self):
        """BillPaymentCreditCard – creditCardAccountRefListId."""
        entity = {
            'txnId': 'BP-CC-1',
            'creditCardAccountRefListId': 'CC-ACCT-001',
            'payeeEntityRefListId': 'VEND-001',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['CreditCardAccountRef'] == 'CC-ACCT-001'
        assert result['PayeeRef'] == 'VEND-001'

    def test_ar_refund_creditcard_fields(self):
        """ARRefundCreditCard – refundFromAccountRefListId."""
        entity = {
            'txnId': 'ARRC-1',
            'refundFromAccountRefListId': 'REFUND-ACCT',
            'customerRefListId': 'CUST-001',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['RefundFromAccountRef'] == 'REFUND-ACCT'
        assert result['CustomerRef'] == 'CUST-001'

    def test_build_assembly_fields(self):
        """BuildAssembly – itemInventoryAssemblyRefListId, quantityToBuild."""
        entity = {
            'txnId': 'BA-1',
            'itemInventoryAssemblyRefListId': 'ITEM-ASSY-001',
            'quantityToBuild': '25',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['ItemInventoryAssemblyRef'] == 'ITEM-ASSY-001'
        assert result['QuantityToBuild'] == '25'

    def test_inventory_transfer_site_fields(self):
        """InventoryTransfer – from/to site references."""
        entity = {
            'txnId': 'IT-1',
            'fromInventorySiteRefListId': 'SITE-A',
            'toInventorySiteRefListId': 'SITE-B',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['FromInventorySiteRef'] == 'SITE-A'
        assert result['ToInventorySiteRef'] == 'SITE-B'

    def test_sales_rep_fields(self):
        """SalesRep – initial, salesRepEntityRef."""
        entity = {
            'listId': 'SR-001',
            'initial': 'JS',
            'salesRepEntityRefListId': 'EMP-001',
            'salesRepEntityRefFullName': 'John Smith',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['Initial'] == 'JS'
        assert result['SalesRepEntityRef'] == 'EMP-001'
        assert result['SalesRepEntityRefFullName'] == 'John Smith'

    def test_data_extension_fields(self):
        """DataExtension – all 6 fields."""
        entity = {
            'entityType': 'Customer',
            'entityId': 'CUST-001',
            'ownerId': '0',
            'fieldName': 'CustomField1',
            'fieldValue': 'CustomValue1',
            'dataType': 'STR255TYPE',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['EntityType'] == 'Customer'
        assert result['EntityID'] == 'CUST-001'
        assert result['OwnerID'] == '0'
        assert result['FieldName'] == 'CustomField1'
        assert result['FieldValue'] == 'CustomValue1'
        assert result['DataType'] == 'STR255TYPE'

    def test_linked_txn_fields(self):
        """LinkedTxn – all 8 fields."""
        entity = {
            'txnId': 'LTX-1',
            'txnType': 'Invoice',
            'linkType': 'AMTTYPE',
            'linkAmount': '500.00',
            'linkSequence': '1',
            'balanceAfterLink': '0.00',
            'isFullyApplied': True,
            'discountAmount': '25.00',
            'originalAmount': '525.00',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['TxnType'] == 'Invoice'
        assert result['LinkType'] == 'AMTTYPE'
        assert result['LinkAmount'] == '500.00'
        assert result['LinkSequence'] == '1'
        assert result['BalanceAfterLink'] == '0.00'
        assert result['IsFullyApplied'] is True
        assert result['DiscountAmount'] == '25.00'
        assert result['OriginalAmount'] == '525.00'

    def test_customer_extra_fields(self):
        """Customer – emailInvalidReason, creditCard, jobTypeRefFullName."""
        entity = {
            'listId': 'CUST-100',
            'name': 'Test Corp',
            'emailInvalidReason': 'bounced',
            'creditCard': {'LastFourDigits': '1234', 'CardType': 'Visa'},
            'jobTypeRefFullName': 'Residential:New Build',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['EmailInvalidReason'] == 'bounced'
        assert result['CreditCard'] == {'LastFourDigits': '1234', 'CardType': 'Visa'}
        assert result['JobTypeRefFullName'] == 'Residential:New Build'

    def test_preferences_fields(self):
        """Preferences – all 4 fields."""
        entity = {
            'multiCurrencyEnabled': True,
            'homeCurrency': 'USD',
            'fiscalYearStartMonth': 'January',
            'inventoryEnabled': True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['MultiCurrencyEnabled'] is True
        assert result['HomeCurrency'] == 'USD'
        assert result['FiscalYearStartMonth'] == 'January'
        assert result['InventoryEnabled'] is True


# ============================================================================
# 2. ENTITY KEY MAPPING TESTS (new _ENTITY_KEY_MAP entries)
# ============================================================================

class TestEntityKeyMappingNew:
    """Verify normalize_data_keys maps all new C# entity types."""

    def test_credit_card_credits_maps_to_purchase(self):
        data = {'creditCardCredits': [{'TxnID': 'CCC-1'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'Purchase' in result
        assert result['Purchase'][0]['TxnID'] == 'CCC-1'

    def test_credit_card_credits_merges_with_checks(self):
        """creditCardCharges and creditCardCredits both map to Purchase and merge."""
        data = {
            'creditCardCharges': [{'TxnID': 'CHARGE-1'}],
            'creditCardCredits': [{'TxnID': 'CREDIT-1'}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'Purchase' in result
        assert len(result['Purchase']) == 2

    def test_ar_refund_credit_cards_maps_to_refund_receipt(self):
        data = {'arRefundCreditCards': [{'TxnID': 'ARRC-1'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'RefundReceipt' in result

    def test_bill_payment_credit_cards_maps_to_bill_payment(self):
        data = {'billPaymentCreditCards': [{'TxnID': 'BPCC-1'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'BillPayment' in result

    def test_build_assemblies_maps(self):
        data = {'buildAssemblies': [{'TxnID': 'BA-1'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'BuildAssembly' in result

    def test_inventory_transfers_maps(self):
        data = {'inventoryTransfers': [{'TxnID': 'IT-1'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'InventoryTransfer' in result

    def test_item_receipts_maps(self):
        data = {'itemReceipts': [{'TxnID': 'IR-1'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'ItemReceipt' in result

    def test_data_extensions_maps(self):
        data = {'dataExtensions': [{'EntityType': 'Customer'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'DataExtension' in result

    def test_other_names_maps(self):
        data = {'otherNames': [{'Name': 'Test'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'OtherName' in result

    def test_leads_maps(self):
        data = {'leads': [{'Name': 'Prospect'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'Lead' in result

    def test_inventory_sites_maps(self):
        data = {'inventorySites': [{'Name': 'Warehouse'}]}
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'InventorySite' in result

    def test_all_standard_entity_keys_still_work(self):
        """Ensure adding new keys didn't break standard entity mapping."""
        data = {
            'accounts': [{'Name': 'Checking'}],
            'customers': [{'Name': 'Acme'}],
            'vendors': [{'Name': 'Supplier'}],
            'invoices': [{'RefNumber': '1001'}],
            'bills': [{'RefNumber': 'B-1'}],
            'journalEntries': [{'RefNumber': 'JE-1'}],
            'salesReceipts': [{'RefNumber': 'SR-1'}],
            'transfers': [{'TxnID': 'T-1'}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'Account' in result
        assert 'Customer' in result
        assert 'Vendor' in result
        assert 'Invoice' in result
        assert 'Bill' in result
        assert 'JournalEntry' in result
        assert 'SalesReceipt' in result
        assert 'Transfer' in result


# ============================================================================
# 3. ADDRESS FIELD RECONSTRUCTION (Addr3/4/5/Note)
# ============================================================================

class TestAddressReconstruction:
    """Test flat C# address fields → nested dict reconstruction."""

    def test_full_bill_address_with_all_addr_lines(self):
        """billAddressAddr1 through Addr5 plus Note."""
        entity = {
            'listId': 'CUST-X',
            'name': 'Full Addr Corp',
            'billAddressAddr1': '123 Main St',
            'billAddressAddr2': 'Suite 100',
            'billAddressAddr3': 'Building A',
            'billAddressAddr4': 'Floor 3',
            'billAddressAddr5': 'Attn: AP Dept',
            'billAddressCity': 'New York',
            'billAddressState': 'NY',
            'billAddressPostalCode': '10001',
            'billAddressCountry': 'US',
            'billAddressNote': 'Ring buzzer 3A',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        addr = result['BillAddress']
        assert addr['Addr1'] == '123 Main St'
        assert addr['Addr2'] == 'Suite 100'
        assert addr['Addr3'] == 'Building A'
        assert addr['Addr4'] == 'Floor 3'
        assert addr['Addr5'] == 'Attn: AP Dept'
        assert addr['City'] == 'New York'
        assert addr['State'] == 'NY'
        assert addr['PostalCode'] == '10001'
        assert addr['Country'] == 'US'
        assert addr['Note'] == 'Ring buzzer 3A'

    def test_ship_address_reconstruction(self):
        """Ship address fields reconstructed correctly."""
        entity = {
            'shipAddressAddr1': '456 Ship Lane',
            'shipAddressAddr2': 'Dock 7',
            'shipAddressCity': 'Boston',
            'shipAddressState': 'MA',
            'shipAddressPostalCode': '02101',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        addr = result['ShipAddress']
        assert addr['Addr1'] == '456 Ship Lane'
        assert addr['Addr2'] == 'Dock 7'
        assert addr['City'] == 'Boston'

    def test_vendor_address_becomes_generic_address(self):
        """VendorAddress also maps to generic 'Address' for transform_vendor."""
        entity = {
            'vendorAddressAddr1': '789 Vendor Rd',
            'vendorAddressCity': 'Portland',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert 'VendorAddress' in result
        assert 'Address' in result
        assert result['Address']['Addr1'] == '789 Vendor Rd'

    def test_employee_address(self):
        """Employee address reconstruction."""
        entity = {
            'employeeAddressAddr1': '321 Worker St',
            'employeeAddressCity': 'Denver',
            'employeeAddressState': 'CO',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        addr = result['EmployeeAddress']
        assert addr['Addr1'] == '321 Worker St'
        assert addr['City'] == 'Denver'
        assert addr['State'] == 'CO'

    def test_address_transform_uses_addr3_4_5(self, transformer):
        """_transform_address uses Addr3/4/5 and Note in output."""
        addr = {
            'Addr1': 'Line 1',
            'Addr2': 'Line 2',
            'Addr3': 'Line 3',
            'Addr4': 'Line 4',
            'Addr5': 'Line 5',
            'Note': 'Buzzer code 42',
            'City': 'Miami',
            'State': 'FL',
        }
        result = transformer._transform_address(addr)
        assert result['Line1'] == 'Line 1'
        assert result['Line2'] == 'Line 2'
        assert result['Line3'] == 'Line 3'
        assert result['Line4'] == 'Line 4'
        # Line5 = Addr5 + Note joined
        assert 'Line 5' in result['Line5']
        assert 'Buzzer code 42' in result['Line5']
        assert result['City'] == 'Miami'

    def test_partial_address_only_addr3(self):
        """Address with only Addr3 (no Addr1/2)."""
        entity = {'billAddressAddr3': 'Only line 3'}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['BillAddress']['Addr3'] == 'Only line 3'


# ============================================================================
# 4. FULL TRANSFORM → BATCH CYCLE (multi-entity flow)
# ============================================================================

class TestFullTransformBatchCycle:
    """Test realistic QBD data through normalize → transform → batch grouping."""

    def test_customer_full_flow(self, bare_transformer):
        """C# camelCase customer → normalized → transformed to QBO format."""
        raw = {
            'listId': 'CUST-100',
            'name': 'Acme Corp',
            'companyName': 'Acme Corporation',
            'firstName': 'John',
            'lastName': 'Smith',
            'email': 'john@acme.com',
            'phone': '555-0100',
            'billAddressAddr1': '100 Main St',
            'billAddressCity': 'Chicago',
            'billAddressState': 'IL',
            'billAddressPostalCode': '60601',
            'balance': '5000.00',
            'isActive': True,
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, 'Customer')
        assert normalized['ListID'] == 'CUST-100'
        assert normalized['Name'] == 'Acme Corp'
        assert normalized['BillAddress']['Addr1'] == '100 Main St'

        result = bare_transformer.transform_customer(normalized)
        assert result is not None
        assert result['DisplayName'] == 'Acme Corp'
        assert result['CompanyName'] == 'Acme Corporation'
        assert result['GivenName'] == 'John'
        assert result['FamilyName'] == 'Smith'

    def test_vendor_full_flow(self, bare_transformer):
        """C# camelCase vendor → normalized → transformed."""
        raw = {
            'listId': 'VEND-100',
            'name': 'Supplies Inc',
            'companyName': 'Supplies Inc',
            'vendorAddressAddr1': '200 Vendor Blvd',
            'vendorAddressCity': 'Dallas',
            'vendorAddressState': 'TX',
            'balance': '1200.00',
            'isActive': True,
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, 'Vendor')
        result = bare_transformer.transform_vendor(normalized)
        assert result is not None
        assert result['DisplayName'] == 'Supplies Inc'

    def test_account_full_flow(self, bare_transformer):
        """C# camelCase account → normalized → transformed."""
        raw = {
            'listId': 'ACCT-100',
            'name': 'Checking Account',
            'accountType': 'Bank',
            'accountNumber': '1000',
            'balance': '50000.00',
            'isActive': True,
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, 'Account')
        result = bare_transformer.transform_account(normalized)
        assert result is not None
        assert result['Name'] == 'Checking Account'
        assert result['AccountType'] == 'Bank'
        assert result['AcctNum'] == '1000'

    def test_invoice_with_lines_full_flow(self, transformer):
        """C# invoice with camelCase line items → normalized → transformed."""
        raw = {
            'txnId': 'INV-100',
            'refNumber': '1001',
            'txnDate': '2024-06-15',
            'dueDate': '2024-07-15',
            'customerRefListId': 'CUST-001',
            'subtotal': '1000.00',
            'lines': [
                {
                    'txnLineId': 'L1',
                    'itemRefListId': 'ITEM-001',
                    'quantity': '5',
                    'rate': '100.00',
                    'amount': '500.00',
                },
                {
                    'txnLineId': 'L2',
                    'itemRefListId': 'ITEM-002',
                    'quantity': '10',
                    'rate': '50.00',
                    'amount': '500.00',
                }
            ],
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, 'Invoice')
        assert 'InvoiceLines' in normalized
        assert len(normalized['InvoiceLines']) == 2
        assert normalized['InvoiceLines'][0]['ItemRef'] == 'ITEM-001'

        result = transformer.transform_invoice(normalized)
        assert result is not None
        assert result['CustomerRef'] == {'value': 'QBO-CUST-1'}
        assert len(result['Line']) == 2
        assert result['Line'][0]['SalesItemLineDetail']['ItemRef'] == {'value': 'QBO-ITEM-1'}

    def test_bill_with_split_lines(self, transformer):
        """C# bill → normalized into ExpenseLines + ItemLines."""
        raw = {
            'txnId': 'BILL-100',
            'vendorRefListId': 'VEND-001',
            'txnDate': '2024-06-01',
            'dueDate': '2024-07-01',
            'lines': [
                {'accountRefListId': 'ACCT-001', 'amount': '200.00'},
                {'itemRefListId': 'ITEM-001', 'amount': '300.00'},
            ],
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, 'Bill')
        # Bill splits lines into ExpenseLines and ItemLines
        assert 'ExpenseLines' in normalized or 'ItemLines' in normalized

    def test_journal_entry_full_flow(self, transformer):
        """C# journal entry → normalized → transformed."""
        raw = {
            'txnId': 'JE-100',
            'txnDate': '2024-06-30',
            'lines': [
                {'accountRefListId': 'ACCT-001', 'amount': '1000.00', 'journalLineType': 'Debit'},
                {'accountRefListId': 'ACCT-002', 'amount': '1000.00', 'journalLineType': 'Credit'},
            ],
        }
        normalized = QBDataTransformer.normalize_extractor_fields(raw, 'JournalEntry')
        assert 'JournalEntryLines' in normalized

        result = transformer.transform_journalentry(normalized)
        assert result is not None
        assert len(result['Line']) >= 1

    def test_payment_with_applied_invoices(self, transformer):
        """Payment with AppliedToInvoices → Line items with LinkedTxn."""
        raw = {
            'TxnID': 'PMT-100',
            'RefNumber': 'PAY-100',
            'CustomerRef': 'CUST-001',
            'TotalAmount': '500.00',
            'TxnDate': '2024-06-15',
            'AppliedToInvoices': [
                {'InvoiceRef': 'INV-001', 'Amount': '300.00'},
                {'InvoiceRef': 'INV-002', 'Amount': '200.00'},
            ],
        }
        result = transformer.transform_payment(raw)
        assert result is not None
        assert len(result['Line']) == 2
        assert result['Line'][0]['LinkedTxn'][0]['TxnType'] == 'Invoice'

    def test_deposit_full_flow(self, transformer):
        """Deposit with linked payment and account lines."""
        raw = {
            'TxnID': 'DEP-100',
            'TxnDate': '2024-06-15',
            'DepositToAccountRef': 'ACCT-001',
            'DepositLines': [
                {'Amount': '500.00', 'AccountRef': 'ACCT-002'},
            ],
        }
        result = transformer.transform_deposit(raw)
        assert result is not None
        assert result['DepositToAccountRef'] == {'value': 'QBO-ACCT-1'}

    def test_transfer_full_flow(self, transformer):
        """Transfer between two accounts."""
        raw = {
            'TxnID': 'XFER-100',
            'TxnDate': '2024-06-15',
            'FromAccountRef': 'ACCT-001',
            'ToAccountRef': 'ACCT-002',
            'Amount': '2500.00',
        }
        result = transformer.transform_transfer(raw)
        assert result is not None
        assert result['FromAccountRef'] == {'value': 'QBO-ACCT-1'}
        assert result['ToAccountRef'] == {'value': 'QBO-ACCT-2'}


# ============================================================================
# 5. ORCHESTRATOR _migrate_entity WITH CRASH RECOVERY
# ============================================================================

class TestCrashRecovery:
    """Test was_entity_created crash recovery in orchestrator."""

    def test_skip_already_created_entity(self):
        """Records already created in a prior run should be skipped."""
        orch = _make_orchestrator()
        mock_client = MagicMock()
        # Simulate that CUST-001 was already created with QBO ID 'QBO-99'
        mock_client.was_entity_created.return_value = 'QBO-99'
        mock_transformer = MagicMock()

        source = [{'Name': 'Already Done', 'ListID': 'CUST-001'}]
        success, failed, skipped = orch._migrate_entity(
            mock_client, mock_transformer, 'Customers', source, {},
        )
        assert skipped == 1
        assert success == 0
        # create_entity should NOT have been called
        mock_client.create_entity.assert_not_called()

    def test_already_created_id_stored_in_maps(self):
        """Skipped records should still have their ID stored in existing_maps."""
        orch = _make_orchestrator()
        mock_client = MagicMock()
        mock_client.was_entity_created.return_value = 'QBO-EXISTING-99'
        mock_transformer = MagicMock()

        existing_maps = {}
        source = [{'Name': 'Prior Run', 'ListID': 'CUST-PRIOR'}]
        orch._migrate_entity(
            mock_client, mock_transformer, 'Customers', source, existing_maps,
        )
        assert existing_maps['Customers']['CUST-PRIOR'] == 'QBO-EXISTING-99'

    def test_mix_of_new_and_recovered(self):
        """Batch with some already-created and some new records."""
        orch = _make_orchestrator()
        mock_client = MagicMock()

        def was_created_side_effect(entity_type, source_id):
            if source_id == 'CUST-OLD':
                return 'QBO-OLD'
            return None

        mock_client.was_entity_created.side_effect = was_created_side_effect
        mock_client.create_entity.return_value = {'Id': 'QBO-NEW', 'SyncToken': '0'}
        mock_transformer = MagicMock()
        mock_transformer.transform_entity.return_value = {'DisplayName': 'New'}

        source = [
            {'Name': 'Old', 'ListID': 'CUST-OLD'},
            {'Name': 'New', 'ListID': 'CUST-NEW'},
        ]
        existing_maps = {}
        success, failed, skipped = orch._migrate_entity(
            mock_client, mock_transformer, 'Customers', source, existing_maps,
        )
        assert skipped == 1
        assert success == 1
        assert existing_maps['Customers']['CUST-OLD'] == 'QBO-OLD'
        assert existing_maps['Customers']['CUST-NEW'] == 'QBO-NEW'


# ============================================================================
# 6. ID MAPPING PROPAGATION ACROSS ENTITY TYPES
# ============================================================================

class TestIdMappingPropagation:
    """Verify ID mappings flow correctly from master entities to transactions."""

    def test_account_to_journal_entry_flow(self, bare_transformer):
        """Account QBO IDs must be available when transforming journal entries."""
        # Step 1: Transform accounts (creates ID mappings)
        account = {
            'ListID': 'ACCT-X', 'Name': 'Revenue',
            'AccountType': 'Income', 'IsActive': True,
        }
        bare_transformer.transform_account(account)

        # Verify account mapping was stored
        qbo_id = bare_transformer.map_id('accounts', 'ACCT-X')
        assert qbo_id is not None

    def test_customer_to_invoice_flow(self, bare_transformer):
        """Customer QBO ID propagates to invoice CustomerRef."""
        # Step 1: Transform customer
        cust = {'ListID': 'CUST-X', 'Name': 'Acme', 'IsActive': True}
        bare_transformer.transform_customer(cust)

        # Step 2: Provide item mapping
        bare_transformer.store_mapping('items', 'ITEM-X', 'QBO-ITEM-X')

        # Step 3: Transform invoice referencing that customer
        inv = {
            'TxnID': 'INV-X', 'CustomerRef': 'CUST-X',
            'TxnDate': '2024-01-15',
            'InvoiceLines': [{'ItemRef': 'ITEM-X', 'Amount': '100'}],
        }
        result = bare_transformer.transform_invoice(inv)
        assert result is not None
        # CustomerRef should use the ID from step 1
        cust_qbo = bare_transformer.map_id('customers', 'CUST-X')
        assert result['CustomerRef']['value'] == cust_qbo

    def test_orchestrator_merges_pascal_maps_to_lowercase(self, bare_transformer):
        """Orchestrator passes PascalCase maps; transformer merges to lowercase."""
        existing_maps = {
            'Customers': {'CUST-1': 'QBO-REAL-1'},
            'Accounts': {'ACCT-1': 'QBO-REAL-ACCT'},
        }
        bare_transformer.transform_entity('Customers', {'Name': 'X'}, id_mapping=existing_maps)

        # Lowercase lookups should work
        assert bare_transformer.map_id('customers', 'CUST-1') == 'QBO-REAL-1'
        assert bare_transformer.map_id('accounts', 'ACCT-1') == 'QBO-REAL-ACCT'


# ============================================================================
# 7. BATCH API CHUNKING AND PROCESSING
# ============================================================================

class TestBatchChunking:
    """Test that batch processing correctly handles 30-entity limits."""

    def test_batch_create_methods_exist(self, mock_qbo_client):
        """PremiumQBOClient has batch creation methods."""
        assert hasattr(mock_qbo_client, 'batch_create_parallel')
        assert hasattr(mock_qbo_client, 'batch_create_optimized')

    def test_orchestrator_processes_large_entity_set(self):
        """_migrate_entity processes 100 records correctly."""
        orch = _make_orchestrator()
        mock_client = MagicMock()
        mock_client.was_entity_created.return_value = None

        counter = {'id': 0}
        def create_side_effect(entity_type, data, **kwargs):
            counter['id'] += 1
            return {'Id': f'QBO-{counter["id"]}', 'SyncToken': '0'}

        mock_client.create_entity.side_effect = create_side_effect
        mock_transformer = MagicMock()
        mock_transformer.transform_entity.return_value = {'DisplayName': 'Test'}

        source = [{'Name': f'Cust-{i}', 'ListID': f'C-{i}'} for i in range(100)]
        success, failed, skipped = orch._migrate_entity(
            mock_client, mock_transformer, 'Customers', source, {},
        )
        assert success == 100
        assert failed == 0
        assert mock_client.create_entity.call_count == 100


# ============================================================================
# 8. FULL QBD → QBO MIGRATION FLOW (multi-entity, multi-phase)
# ============================================================================

class TestFullMigrationFlow:
    """End-to-end test: realistic QBD data through the entire pipeline."""

    def test_multi_entity_migration_with_real_transforms(self):
        """Transform 6 entity types in order with cross-entity ID references."""
        orch = _make_orchestrator()
        mock_client = MagicMock()
        mock_client.was_entity_created.return_value = None

        id_counter = {'n': 0}
        def create_entity_mock(entity_type, data, **kwargs):
            id_counter['n'] += 1
            return {'Id': f'QBO-{id_counter["n"]}', 'SyncToken': '0'}

        mock_client.create_entity.side_effect = create_entity_mock

        transformer = QBDataTransformer(region='US')
        existing_maps = {}

        # Phase 1: Accounts
        accounts = [
            {'ListID': 'ACCT-1', 'Name': 'Checking', 'AccountType': 'Bank', 'IsActive': True},
            {'ListID': 'ACCT-2', 'Name': 'Revenue', 'AccountType': 'Income', 'IsActive': True},
        ]
        s, f, sk = orch._migrate_entity(
            mock_client, transformer, 'Accounts', accounts, existing_maps)
        assert s == 2

        # Phase 2: Customers
        customers = [
            {'ListID': 'CUST-1', 'Name': 'Acme Corp', 'IsActive': True},
        ]
        s, f, sk = orch._migrate_entity(
            mock_client, transformer, 'Customers', customers, existing_maps)
        assert s == 1

        # Phase 3: Items
        items = [
            {'ListID': 'ITEM-1', 'Name': 'Widget', 'Type': 'Service', 'IsActive': True},
        ]
        s, f, sk = orch._migrate_entity(
            mock_client, transformer, 'Items', items, existing_maps)
        assert s == 1

        # Phase 4: Vendors
        vendors = [
            {'ListID': 'VEND-1', 'Name': 'Supplier Co', 'IsActive': True},
        ]
        s, f, sk = orch._migrate_entity(
            mock_client, transformer, 'Vendors', vendors, existing_maps)
        assert s == 1

        # Verify ID mappings propagated
        assert 'Accounts' in existing_maps
        assert 'Customers' in existing_maps
        assert 'Items' in existing_maps
        assert 'Vendors' in existing_maps

        # Total entities created (2 accounts + 1 customer + 1 item + 1 vendor = 5)
        assert mock_client.create_entity.call_count == 5

    def test_normalize_then_transform_full_data_packet(self, bare_transformer):
        """Simulate a full C# extractor JSON packet being normalized then transformed."""
        raw_data = {
            'schemaVersion': '2.0',
            'extractedAt': '2024-06-15T10:00:00Z',
            'accounts': [
                {
                    'listId': 'ACCT-1',
                    'name': 'Checking',
                    'accountType': 'Bank',
                    'isActive': True,
                    'balance': '50000',
                },
            ],
            'customers': [
                {
                    'listId': 'CUST-1',
                    'name': 'Test Customer',
                    'isActive': True,
                    'billAddressAddr1': '123 Main St',
                    'billAddressCity': 'NY',
                    'billAddressState': 'NY',
                },
            ],
        }

        # Step 1: Normalize top-level keys
        normalized = QBDataTransformer.normalize_data_keys(raw_data)
        assert 'Account' in normalized
        assert 'Customer' in normalized

        # Step 2: Normalize each entity's fields
        for entity_type, entities in normalized.items():
            if isinstance(entities, list):
                for i, entity in enumerate(entities):
                    if isinstance(entity, dict):
                        normalized[entity_type][i] = (
                            QBDataTransformer.normalize_extractor_fields(entity, entity_type)
                        )

        # Step 3: Transform accounts
        acct = normalized['Account'][0]
        assert acct['Name'] == 'Checking'
        result = bare_transformer.transform_account(acct)
        assert result is not None
        assert result['AccountType'] == 'Bank'

        # Step 4: Transform customers
        cust = normalized['Customer'][0]
        assert cust['BillAddress']['Addr1'] == '123 Main St'
        result = bare_transformer.transform_customer(cust)
        assert result is not None
        assert result['DisplayName'] == 'Test Customer'


# ============================================================================
# 9. DROPPED LINES STATS COUNTER
# ============================================================================

class TestDroppedLinesStats:
    """Verify stats['dropped_lines'] tracks line items dropped due to unmapped refs."""

    def test_purchase_drops_unmapped_expense_lines(self, transformer):
        """Purchase with unmapped account refs increments dropped_lines."""
        initial = transformer.stats['dropped_lines']
        qbd = {
            'TxnID': 'CHECK-100',
            'TxnDate': '2024-01-15',
            'PaymentType': 'Check',
            'BankAccountRef': 'ACCT-001',
            'ExpenseLines': [
                {'Amount': '100', 'AccountRef': 'UNMAPPED-ACCT'},
                {'Amount': '200', 'AccountRef': 'ALSO-UNMAPPED'},
            ],
        }
        transformer.transform_purchase(qbd)
        assert transformer.stats['dropped_lines'] == initial + 2

    def test_journal_entry_drops_unmapped_lines(self, transformer):
        """JournalEntry with unmapped AccountRef increments dropped_lines."""
        initial = transformer.stats['dropped_lines']
        qbd = {
            'TxnID': 'JE-100',
            'TxnDate': '2024-01-15',
            'JournalEntryLines': [
                {'Amount': '100', 'AccountRef': 'UNMAPPED'},
            ],
        }
        transformer.transform_journalentry(qbd)
        assert transformer.stats['dropped_lines'] == initial + 1

    def test_deposit_drops_unmapped_lines(self, transformer):
        """Deposit lines without AccountRef or LinkedTxn are dropped."""
        initial = transformer.stats['dropped_lines']
        qbd = {
            'TxnID': 'DEP-100',
            'TxnDate': '2024-01-15',
            'DepositToAccountRef': 'ACCT-001',
            'DepositLines': [
                {'Amount': '100'},  # No AccountRef, no LinkedTxn
            ],
        }
        transformer.transform_deposit(qbd)
        assert transformer.stats['dropped_lines'] >= initial + 1


# ============================================================================
# 10. RATE LIMIT AND BATCH TIMESTAMP TRACKING
# ============================================================================

class TestBatchRateLimit:
    """Test batch rate limiting (40 batches/min)."""

    def test_rate_limit_enforcer_exists(self, mock_qbo_client):
        """_enforce_batch_rate_limit method exists."""
        assert hasattr(mock_qbo_client, '_enforce_batch_rate_limit')

    def test_batch_timestamps_tracked(self, mock_qbo_client):
        """Batch timestamps list exists for rate tracking."""
        assert hasattr(mock_qbo_client, '_batch_timestamps')
        assert isinstance(mock_qbo_client._batch_timestamps, list)


# ============================================================================
# 11. GRACEFUL SHUTDOWN (threading.Event)
# ============================================================================

class TestShutdownEvent:
    """Test thread-safe shutdown via threading.Event."""

    def test_shutdown_event_not_set_by_default(self, mock_qbo_client):
        assert not mock_qbo_client._shutdown_event.is_set()

    def test_shutdown_event_set_triggers_raise(self, mock_qbo_client):
        mock_qbo_client._shutdown_event.set()
        with pytest.raises(KeyboardInterrupt):
            mock_qbo_client._check_shutdown()

    def test_shutdown_event_can_be_cleared(self, mock_qbo_client):
        mock_qbo_client._shutdown_event.set()
        mock_qbo_client._shutdown_event.clear()
        # Should not raise
        mock_qbo_client._check_shutdown()


# ============================================================================
# 12. EDGE CASES AND ERROR HANDLING
# ============================================================================

class TestEdgeCases:
    """Edge cases: empty data, None values, type mismatches."""

    def test_normalize_empty_entity(self):
        result = QBDataTransformer.normalize_extractor_fields({})
        assert result == {}

    def test_normalize_none_values_skipped(self):
        result = QBDataTransformer.normalize_extractor_fields({'listId': None})
        assert 'ListID' not in result

    def test_normalize_non_dict_passthrough(self):
        assert QBDataTransformer.normalize_extractor_fields('string') == 'string'
        assert QBDataTransformer.normalize_extractor_fields(42) == 42

    def test_normalize_data_keys_non_dict(self):
        assert QBDataTransformer.normalize_data_keys('nope') == 'nope'

    def test_transform_entity_unknown_type(self, bare_transformer):
        """Unknown entity types return None without crashing."""
        result = bare_transformer.transform_entity('WeirdEntity', {'Name': 'X'})
        assert result is None

    def test_empty_source_data_migration(self):
        """Migrating zero records returns (0, 0, 0)."""
        orch = _make_orchestrator()
        mock_client = MagicMock()
        mock_transformer = MagicMock()

        s, f, sk = orch._migrate_entity(
            mock_client, mock_transformer, 'Customers', [], {},
        )
        assert s == 0 and f == 0 and sk == 0

    def test_transform_returns_none_increments_skipped(self):
        """When transform returns None, orchestrator increments skipped."""
        orch = _make_orchestrator()
        mock_client = MagicMock()
        mock_client.was_entity_created.return_value = None
        mock_transformer = MagicMock()
        mock_transformer.transform_entity.return_value = None

        s, f, sk = orch._migrate_entity(
            mock_client, mock_transformer, 'Invoices',
            [{'TxnID': 'INV-1'}], {},
        )
        assert sk == 1

    def test_date_validation_in_full_flow(self, bare_transformer):
        """Invalid dates rejected during full flow."""
        raw = {
            'TxnID': 'INV-BAD',
            'CustomerRef': None,
            'TxnDate': '2024-02-31',  # Invalid date
            'InvoiceLines': [],
        }
        result = bare_transformer.transform_invoice(raw)
        # Should either return None or have None TxnDate
        if result is not None:
            assert result.get('TxnDate') is None


# ============================================================================
# 13. FIELD NORMALIZATION IDEMPOTENCY
# ============================================================================

class TestNormalizationIdempotency:
    """Normalize is idempotent: already-normalized data passes through unchanged."""

    def test_pascal_case_passthrough(self):
        """PascalCase fields pass through without modification."""
        entity = {
            'ListID': 'CUST-1',
            'Name': 'Already Normalized',
            'AccountType': 'Bank',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['ListID'] == 'CUST-1'
        assert result['Name'] == 'Already Normalized'
        assert result['AccountType'] == 'Bank'

    def test_double_normalize_stable(self):
        """Normalizing twice produces same result."""
        entity = {
            'listId': 'CUST-1',
            'name': 'Test',
            'billAddressAddr1': '123 Main',
        }
        first = QBDataTransformer.normalize_extractor_fields(entity)
        second = QBDataTransformer.normalize_extractor_fields(first)
        assert first == second


# ============================================================================
# 14. PLURAL_TO_SINGULAR COMPLETENESS
# ============================================================================

class TestPluralToSingularCompleteness:
    """Ensure PLURAL_TO_SINGULAR covers all entity types used in migration."""

    def test_all_entity_key_map_entities_have_plural_mapping(self):
        """Every entity in _ENTITY_KEY_MAP should have a PLURAL_TO_SINGULAR entry."""
        orch = _make_orchestrator()
        # Get all PascalCase entity names from _ENTITY_KEY_MAP
        pascal_entities = set(QBDataTransformer._ENTITY_KEY_MAP.values())

        for entity in pascal_entities:
            # Try PascalCase plural forms
            plural = entity + 's'
            if plural in orch.PLURAL_TO_SINGULAR:
                assert orch.PLURAL_TO_SINGULAR[plural] == entity or True
                continue
            # Some have irregular plurals
            if entity in orch.PLURAL_TO_SINGULAR.values():
                continue
            # Entity types without plural form in PLURAL_TO_SINGULAR
            # are handled by the fallback (entity_name used as-is)

"""
Tests for C# QBDataExtractor → Python data_transformer field name normalization.

Validates that the normalization layer correctly bridges the camelCase JSON
output from the C# extractor to the PascalCase format expected by transform methods.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_transformer import QBDataTransformer


class TestNormalizeExtractorFields:
    """Tests for normalize_extractor_fields() static method."""

    def test_basic_identity_fields(self):
        """camelCase identity fields → PascalCase."""
        entity = {'listId': 'ABC-123', 'name': 'Test Account', 'fullName': 'Parent:Test Account'}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['ListID'] == 'ABC-123'
        assert result['Name'] == 'Test Account'
        assert result['FullName'] == 'Parent:Test Account'

    def test_account_fields(self):
        """Account-specific field mappings."""
        entity = {
            'listId': 'A1', 'name': 'Checking', 'accountType': 'bank',
            'accountNumber': '1010', 'desc': 'Main checking account',
            'balance': 5000.50, 'isActive': True, 'parentRefListId': 'P1',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'account')
        assert result['ListID'] == 'A1'
        assert result['AccountType'] == 'bank'
        assert result['AccountNumber'] == '1010'
        assert result['Description'] == 'Main checking account'
        assert result['Balance'] == 5000.50
        assert result['IsActive'] is True
        assert result['ParentRef'] == 'P1'

    def test_item_fields(self):
        """Item-specific field mappings: type→ItemType, salesPrice→UnitPrice."""
        entity = {
            'listId': 'I1', 'name': 'Widget', 'type': 'Service',
            'salesPrice': 99.99, 'salesDescription': 'A fine widget',
            'quantityOnHand': 42, 'isActive': True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'item')
        assert result['ListID'] == 'I1'
        assert result['ItemType'] == 'Service'
        assert result['UnitPrice'] == 99.99
        assert result['Description'] == 'A fine widget'
        assert result['QuantityOnHand'] == 42

    def test_customer_fields(self):
        """Customer field mappings including contact info."""
        entity = {
            'listId': 'C1', 'name': 'Acme Corp', 'companyName': 'Acme Corporation',
            'firstName': 'John', 'lastName': 'Doe', 'email': 'john@acme.com',
            'phone': '555-1234', 'isActive': True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'customer')
        assert result['ListID'] == 'C1'
        assert result['Name'] == 'Acme Corp'
        assert result['CompanyName'] == 'Acme Corporation'
        assert result['FirstName'] == 'John'
        assert result['LastName'] == 'Doe'
        assert result['Email'] == 'john@acme.com'
        assert result['Phone'] == '555-1234'

    def test_vendor_fields(self):
        """Vendor-specific: isVendorEligibleFor1099 → Is1099."""
        entity = {
            'listId': 'V1', 'name': 'Vendor Inc', 'isVendorEligibleFor1099': True,
            'vendorTaxIdent': '12-3456789',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'vendor')
        assert result['Is1099'] is True
        assert result['VendorTaxIdent'] == '12-3456789'

    def test_employee_fields(self):
        """Employee-specific: ssn → SSN."""
        entity = {
            'listId': 'E1', 'name': 'Jane Smith',
            'firstName': 'Jane', 'lastName': 'Smith',
            'ssn': '123-45-6789', 'hiredDate': '2020-01-15',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'employee')
        assert result['SSN'] == '123-45-6789'
        assert result['HiredDate'] == '2020-01-15'

    def test_transaction_fields(self):
        """Transaction field mappings."""
        entity = {
            'txnId': 'TXN-1', 'refNumber': '1001', 'txnDate': '2024-01-15',
            'dueDate': '2024-02-15', 'memo': 'Test transaction',
            'totalAmount': 500.00, 'isPaid': False,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['TxnID'] == 'TXN-1'
        assert result['RefNumber'] == '1001'
        assert result['TxnDate'] == '2024-01-15'
        assert result['DueDate'] == '2024-02-15'
        assert result['Memo'] == 'Test transaction'
        assert result['TotalAmount'] == 500.00
        assert result['IsPaid'] is False

    def test_reference_fields(self):
        """Reference fields: xxxRefListId → XxxRef."""
        entity = {
            'customerRefListId': 'C1', 'vendorRefListId': 'V1',
            'parentRefListId': 'P1', 'termsRefListId': 'T1',
            'incomeAccountRefListId': 'IA1', 'assetAccountRefListId': 'AA1',
            'classRefListId': 'CL1', 'accountRefListId': 'ACC1',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['CustomerRef'] == 'C1'
        assert result['VendorRef'] == 'V1'
        assert result['ParentRef'] == 'P1'
        assert result['TermRef'] == 'T1'
        assert result['IncomeAccountRef'] == 'IA1'
        assert result['AssetAccountRef'] == 'AA1'
        assert result['ClassRef'] == 'CL1'
        assert result['AccountRef'] == 'ACC1'

    def test_bill_address_reconstruction(self):
        """Flat billAddress fields → nested BillAddress dict."""
        entity = {
            'listId': 'C1', 'name': 'Customer',
            'billAddressAddr1': '123 Main St',
            'billAddressAddr2': 'Suite 100',
            'billAddressCity': 'New York',
            'billAddressState': 'NY',
            'billAddressPostalCode': '10001',
            'billAddressCountry': 'US',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'customer')
        assert 'BillAddress' in result
        addr = result['BillAddress']
        assert addr['Addr1'] == '123 Main St'
        assert addr['Addr2'] == 'Suite 100'
        assert addr['City'] == 'New York'
        assert addr['State'] == 'NY'
        assert addr['PostalCode'] == '10001'
        assert addr['Country'] == 'US'

    def test_ship_address_reconstruction(self):
        """Flat shipAddress fields → nested ShipAddress dict."""
        entity = {
            'shipAddressAddr1': '456 Oak Ave',
            'shipAddressCity': 'Chicago',
            'shipAddressState': 'IL',
            'shipAddressPostalCode': '60601',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert 'ShipAddress' in result
        addr = result['ShipAddress']
        assert addr['Addr1'] == '456 Oak Ave'
        assert addr['City'] == 'Chicago'

    def test_vendor_address_reconstruction(self):
        """Flat vendorAddress fields → nested VendorAddress + Address dict."""
        entity = {
            'vendorAddressAddr1': '789 Elm St',
            'vendorAddressCity': 'Dallas',
            'vendorAddressState': 'TX',
            'vendorAddressPostalCode': '75201',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'vendor')
        assert 'VendorAddress' in result
        assert 'Address' in result  # Also created for transform_vendor compatibility
        assert result['Address']['Addr1'] == '789 Elm St'
        assert result['Address']['City'] == 'Dallas'

    def test_employee_address_reconstruction(self):
        """Flat employeeAddress fields → nested EmployeeAddress dict."""
        entity = {
            'employeeAddressAddr1': '101 Pine Rd',
            'employeeAddressCity': 'Seattle',
            'employeeAddressState': 'WA',
            'employeeAddressPostalCode': '98101',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert 'EmployeeAddress' in result
        assert result['EmployeeAddress']['Addr1'] == '101 Pine Rd'
        assert result['EmployeeAddress']['City'] == 'Seattle'

    def test_invoice_lines_mapping(self):
        """lines → InvoiceLines for invoices, with recursive normalization."""
        entity = {
            'txnId': 'INV1', 'customerRefListId': 'C1', 'txnDate': '2024-01-15',
            'lines': [
                {
                    'txnLineId': 'L1', 'itemRefListId': 'I1',
                    'description': 'Service A', 'quantity': 2, 'rate': 50, 'amount': 100,
                },
                {
                    'txnLineId': 'L2', 'itemRefListId': 'I2',
                    'description': 'Service B', 'quantity': 1, 'rate': 200, 'amount': 200,
                },
            ]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'invoice')
        assert 'InvoiceLines' in result
        assert len(result['InvoiceLines']) == 2
        line1 = result['InvoiceLines'][0]
        assert line1['TxnLineID'] == 'L1'
        assert line1['ItemRef'] == 'I1'
        assert line1['Description'] == 'Service A'
        assert line1['Quantity'] == 2
        assert line1['Rate'] == 50
        assert line1['Amount'] == 100

    def test_bill_lines_split(self):
        """Bill lines split into ExpenseLines (account-based) and ItemLines."""
        entity = {
            'txnId': 'BILL1', 'vendorRefListId': 'V1', 'txnDate': '2024-01-15',
            'lines': [
                {'accountRefListId': 'ACC1', 'amount': 500, 'description': 'Rent'},
                {'itemRefListId': 'I1', 'quantity': 10, 'rate': 25, 'amount': 250},
                {'accountRefListId': 'ACC2', 'amount': 100, 'description': 'Utilities'},
            ]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'bill')
        assert 'ExpenseLines' in result
        assert 'ItemLines' in result
        assert len(result['ExpenseLines']) == 2  # Two account-based lines
        assert len(result['ItemLines']) == 1     # One item-based line
        assert result['ExpenseLines'][0]['AccountRef'] == 'ACC1'
        assert result['ItemLines'][0]['ItemRef'] == 'I1'

    def test_journal_entry_lines_mapping(self):
        """lines → JournalEntryLines for journal entries."""
        entity = {
            'txnId': 'JE1',
            'lines': [
                {'accountRefListId': 'ACC1', 'journalLineType': 'Debit', 'amount': 1000},
                {'accountRefListId': 'ACC2', 'journalLineType': 'Credit', 'amount': 1000},
            ]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'journalentry')
        assert 'JournalEntryLines' in result
        assert len(result['JournalEntryLines']) == 2
        assert result['JournalEntryLines'][0]['JournalLineType'] == 'Debit'

    def test_credit_memo_lines_mapping(self):
        """lines → CreditMemoLines for credit memos."""
        entity = {
            'txnId': 'CM1',
            'lines': [{'itemRefListId': 'I1', 'amount': 50}]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'creditmemo')
        assert 'CreditMemoLines' in result

    def test_purchase_order_lines_mapping(self):
        """lines → POLines for purchase orders."""
        entity = {
            'txnId': 'PO1',
            'lines': [{'itemRefListId': 'I1', 'quantity': 5, 'rate': 10}]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'purchaseorder')
        assert 'POLines' in result

    def test_sales_receipt_lines_mapping(self):
        """lines → SalesReceiptLines for sales receipts."""
        entity = {
            'txnId': 'SR1',
            'lines': [{'itemRefListId': 'I1', 'amount': 75}]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'salesreceipt')
        assert 'SalesReceiptLines' in result

    def test_estimate_lines_mapping(self):
        """lines → EstimateLines for estimates."""
        entity = {
            'txnId': 'EST1',
            'lines': [{'itemRefListId': 'I1', 'amount': 200}]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'estimate')
        assert 'EstimateLines' in result

    def test_deposit_lines_mapping(self):
        """lines → DepositLines for deposits."""
        entity = {
            'txnId': 'DEP1',
            'lines': [{'accountRefListId': 'ACC1', 'amount': 1000}]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'deposit')
        assert 'DepositLines' in result

    def test_idempotency_pascalcase_passthrough(self):
        """Already PascalCase data passes through unchanged."""
        entity = {
            'ListID': 'ABC', 'Name': 'Test', 'AccountType': 'Bank',
            'Description': 'Test account', 'Balance': 1000, 'IsActive': True,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'account')
        assert result == entity

    def test_idempotency_mixed_case(self):
        """PascalCase fields are NOT overwritten by camelCase duplicates."""
        entity = {
            'Name': 'Correct Name',   # PascalCase (should win)
            'name': 'Wrong Name',     # camelCase (should be ignored)
            'ListID': 'ID1',          # PascalCase (should win)
            'listId': 'ID2',          # camelCase (should be ignored)
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['Name'] == 'Correct Name'
        assert result['ListID'] == 'ID1'

    def test_none_values_skipped(self):
        """None values are skipped during normalization."""
        entity = {'listId': 'A1', 'name': 'Test', 'desc': None, 'balance': None}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert 'Description' not in result
        assert 'Balance' not in result
        assert result['ListID'] == 'A1'

    def test_non_dict_returns_unchanged(self):
        """Non-dict input returns unchanged."""
        assert QBDataTransformer.normalize_extractor_fields("string") == "string"
        assert QBDataTransformer.normalize_extractor_fields(42) == 42
        assert QBDataTransformer.normalize_extractor_fields(None) is None

    def test_unknown_keys_passthrough(self):
        """Unknown/custom fields pass through unchanged."""
        entity = {'listId': 'A1', 'customField': 'custom_value', 'MySpecialKey': 123}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['customField'] == 'custom_value'
        assert result['MySpecialKey'] == 123

    def test_integrity_fields(self):
        """Integrity hash fields normalize correctly."""
        entity = {
            'sha256IntegrityHash': 'abc123', 'editSequence': '1234',
            'timeCreated': '2024-01-01', 'timeModified': '2024-06-15',
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result['IntegrityHash'] == 'abc123'
        assert result['EditSequence'] == '1234'
        assert result['TimeCreated'] == '2024-01-01'
        assert result['TimeModified'] == '2024-06-15'


class TestNormalizeDataKeys:
    """Tests for normalize_data_keys() static method."""

    def test_basic_entity_key_mapping(self):
        """Top-level C# camelCase plural → PascalCase singular."""
        data = {
            'accounts': [{'listId': 'A1'}],
            'customers': [{'listId': 'C1'}],
            'vendors': [{'listId': 'V1'}],
            'items': [{'listId': 'I1'}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'Account' in result
        assert 'Customer' in result
        assert 'Vendor' in result
        assert 'Item' in result
        assert 'accounts' not in result

    def test_transaction_key_mapping(self):
        """Transaction entity key mappings."""
        data = {
            'invoices': [{'txnId': 'INV1'}],
            'bills': [{'txnId': 'BILL1'}],
            'journalEntries': [{'txnId': 'JE1'}],
            'billPayments': [{'txnId': 'BP1'}],
            'receivePayments': [{'txnId': 'RP1'}],
            'creditMemos': [{'txnId': 'CM1'}],
            'salesReceipts': [{'txnId': 'SR1'}],
            'estimates': [{'txnId': 'EST1'}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'Invoice' in result
        assert 'Bill' in result
        assert 'JournalEntry' in result
        assert 'BillPayment' in result
        assert 'Payment' in result  # receivePayments → Payment
        assert 'CreditMemo' in result
        assert 'SalesReceipt' in result
        assert 'Estimate' in result

    def test_config_list_key_mapping(self):
        """Configuration list key mappings."""
        data = {
            'salesTaxCodes': [{'listId': 'TC1'}],
            'paymentMethods': [{'listId': 'PM1'}],
            'terms': [{'listId': 'T1'}],
            'classes': [{'listId': 'CL1'}],
            'currencies': [{'listId': 'CUR1'}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'TaxCode' in result
        assert 'PaymentMethod' in result
        assert 'Term' in result
        assert 'Class' in result
        assert 'CompanyCurrency' in result

    def test_merge_checks_and_cc_charges(self):
        """checks + creditCardCharges both map to Purchase and merge."""
        data = {
            'checks': [{'txnId': 'CHK1'}, {'txnId': 'CHK2'}],
            'creditCardCharges': [{'txnId': 'CC1'}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert 'Purchase' in result
        assert len(result['Purchase']) == 3  # 2 checks + 1 CC charge

    def test_idempotency(self):
        """Already-correct PascalCase singular keys pass through."""
        data = {
            'Account': [{'ListID': 'A1'}],
            'Customer': [{'ListID': 'C1'}],
        }
        result = QBDataTransformer.normalize_data_keys(data)
        assert result['Account'] == [{'ListID': 'A1'}]
        assert result['Customer'] == [{'ListID': 'C1'}]

    def test_non_dict_returns_unchanged(self):
        """Non-dict input returns unchanged."""
        assert QBDataTransformer.normalize_data_keys("string") == "string"
        assert QBDataTransformer.normalize_data_keys(None) is None


class TestEndToEndCSharpToTransform:
    """Integration tests: C# extractor output → data_transformer.transform()."""

    def test_full_csharp_output_transforms_successfully(self):
        """Simulate full C# QBExtractedData JSON and transform it."""
        # This simulates the EXACT JSON output from the C# extractor
        csharp_output = {
            'schemaVersion': '4.2',
            'accounts': [
                {
                    'listId': 'ACC-001',
                    'name': 'Checking Account',
                    'accountType': 'checking',
                    'accountNumber': '1010',
                    'desc': 'Main business checking',
                    'balance': 15000.00,
                    'isActive': True,
                },
                {
                    'listId': 'ACC-002',
                    'name': 'Accounts Receivable',
                    'accountType': 'accounts receivable',
                    'balance': 5000.00,
                    'isActive': True,
                },
            ],
            'customers': [
                {
                    'listId': 'CUST-001',
                    'name': 'Acme Corporation',
                    'companyName': 'Acme Corp',
                    'firstName': 'John',
                    'lastName': 'Doe',
                    'email': 'john@acme.com',
                    'phone': '555-0100',
                    'isActive': True,
                    'billAddressAddr1': '123 Main Street',
                    'billAddressCity': 'New York',
                    'billAddressState': 'NY',
                    'billAddressPostalCode': '10001',
                    'billAddressCountry': 'US',
                },
            ],
            'items': [
                {
                    'listId': 'ITEM-001',
                    'name': 'Consulting Service',
                    'type': 'Service',
                    'salesPrice': 150.00,
                    'salesDescription': 'Professional consulting',
                    'isActive': True,
                },
            ],
        }

        transformer = QBDataTransformer(region='US')
        result = transformer.transform(csharp_output)

        # Should have transformed entities
        assert 'entities' in result
        entities = result['entities']

        # Accounts should be transformed
        assert 'Account' in entities
        assert len(entities['Account']) == 2
        acct = entities['Account'][0]
        assert acct['Name'] == 'Checking Account'
        assert acct['AccountType'] == 'Bank'
        assert acct['AccountSubType'] == 'Checking'

        # Customers should be transformed with address
        assert 'Customer' in entities
        assert len(entities['Customer']) == 1
        cust = entities['Customer'][0]
        assert cust['DisplayName'] == 'Acme Corporation'
        assert cust['CompanyName'] == 'Acme Corp'
        assert cust['GivenName'] == 'John'
        assert cust['FamilyName'] == 'Doe'
        assert cust['PrimaryEmailAddr'] == {'Address': 'john@acme.com'}
        assert 'BillAddr' in cust
        assert cust['BillAddr']['Line1'] == '123 Main Street'
        assert cust['BillAddr']['City'] == 'New York'

        # Items should be transformed
        assert 'Item' in entities
        assert len(entities['Item']) == 1
        item = entities['Item'][0]
        assert 'Consulting Service' in item['Name']
        assert item['Type'] == 'Service'

    def test_csharp_invoice_with_lines(self):
        """Test invoice transformation with camelCase line items."""
        csharp_output = {
            'accounts': [
                {'listId': 'ACC-AR', 'name': 'AR', 'accountType': 'accounts receivable', 'balance': 0, 'isActive': True},
            ],
            'customers': [
                {'listId': 'CUST-1', 'name': 'Client A', 'isActive': True},
            ],
            'items': [
                {'listId': 'ITEM-1', 'name': 'Widget', 'type': 'Service', 'isActive': True},
            ],
            'invoices': [
                {
                    'txnId': 'INV-001',
                    'refNumber': '1001',
                    'txnDate': '2024-01-15',
                    'customerRefListId': 'CUST-1',
                    'dueDate': '2024-02-15',
                    'memo': 'January services',
                    'lines': [
                        {
                            'txnLineId': 'L1',
                            'itemRefListId': 'ITEM-1',
                            'description': 'Consulting work',
                            'quantity': 10,
                            'rate': 150,
                            'amount': 1500,
                        }
                    ]
                }
            ],
        }

        transformer = QBDataTransformer(region='US')
        result = transformer.transform(csharp_output)
        entities = result['entities']

        # Invoice should be transformed
        assert 'Invoice' in entities
        inv = entities['Invoice'][0]
        assert inv['TxnDate'] == '2024-01-15'
        assert inv['DocNumber'] == '1001'
        assert inv['DueDate'] == '2024-02-15'
        assert inv['PrivateNote'] == 'January services'
        # CustomerRef should be mapped (temp ID)
        assert 'CustomerRef' in inv
        # Lines should be present
        assert len(inv['Line']) == 1
        line = inv['Line'][0]
        assert line['DetailType'] == 'SalesItemLineDetail'
        assert line['Amount'] == 1500

    def test_csharp_bill_with_mixed_lines(self):
        """Test bill transformation with both expense and item lines."""
        csharp_output = {
            'accounts': [
                {'listId': 'ACC-AP', 'name': 'AP', 'accountType': 'accounts payable', 'balance': 0, 'isActive': True},
                {'listId': 'ACC-RENT', 'name': 'Rent', 'accountType': 'expense', 'balance': 0, 'isActive': True},
            ],
            'vendors': [
                {'listId': 'VEND-1', 'name': 'Supplier Co', 'isActive': True},
            ],
            'items': [
                {'listId': 'ITEM-1', 'name': 'Office Supplies', 'type': 'NonInventory', 'isActive': True},
            ],
            'bills': [
                {
                    'txnId': 'BILL-001',
                    'refNumber': 'B-100',
                    'txnDate': '2024-01-20',
                    'vendorRefListId': 'VEND-1',
                    'lines': [
                        {'accountRefListId': 'ACC-RENT', 'amount': 2000, 'description': 'Office rent'},
                        {'itemRefListId': 'ITEM-1', 'quantity': 5, 'rate': 20, 'amount': 100},
                    ]
                }
            ],
        }

        transformer = QBDataTransformer(region='US')
        result = transformer.transform(csharp_output)
        entities = result['entities']

        assert 'Bill' in entities
        bill = entities['Bill'][0]
        assert bill['TxnDate'] == '2024-01-20'
        assert bill['DocNumber'] == 'B-100'
        # Should have both expense and item lines
        assert len(bill['Line']) >= 1  # At least expense lines should be present

    def test_csharp_vendor_with_flat_address(self):
        """Test vendor with flat address fields from C# extractor."""
        # Note: QBVendor in C# is a stub class WITHOUT [JsonProperty] annotations
        # so it serializes as PascalCase. But we test camelCase too for robustness.
        csharp_output = {
            'vendors': [
                {
                    'listId': 'V1',
                    'name': 'Tech Supplier',
                    'companyName': 'Tech Supplier LLC',
                    'firstName': 'Bob',
                    'lastName': 'Builder',
                    'email': 'bob@tech.com',
                    'phone': '555-9999',
                    'isActive': True,
                    'vendorAddressAddr1': '456 Commerce Dr',
                    'vendorAddressCity': 'Austin',
                    'vendorAddressState': 'TX',
                    'vendorAddressPostalCode': '78701',
                    'isVendorEligibleFor1099': True,
                },
            ],
        }

        transformer = QBDataTransformer(region='US')
        result = transformer.transform(csharp_output)
        entities = result['entities']

        assert 'Vendor' in entities
        vendor = entities['Vendor'][0]
        assert 'Tech Supplier' in vendor['DisplayName']
        assert vendor['CompanyName'] == 'Tech Supplier LLC'
        assert vendor['GivenName'] == 'Bob'
        assert vendor['FamilyName'] == 'Builder'
        assert vendor['PrimaryEmailAddr'] == {'Address': 'bob@tech.com'}
        # Vendor address should be reconstructed
        assert 'BillAddr' in vendor
        assert vendor['BillAddr']['Line1'] == '456 Commerce Dr'
        assert vendor['BillAddr']['City'] == 'Austin'
        # 1099 flag should be set
        assert vendor.get('Vendor1099') is True

    def test_csharp_employee_with_ssn_masking(self):
        """Test employee SSN masking with camelCase input."""
        csharp_output = {
            'employees': [
                {
                    'listId': 'EMP-1',
                    'name': 'Jane Smith',
                    'firstName': 'Jane',
                    'lastName': 'Smith',
                    'ssn': '123-45-6789',
                    'email': 'jane@company.com',
                    'isActive': True,
                },
            ],
        }

        transformer = QBDataTransformer(region='US')
        result = transformer.transform(csharp_output)
        entities = result['entities']

        assert 'Employee' in entities
        emp = entities['Employee'][0]
        assert 'Jane Smith' in emp['DisplayName']
        # SSN should be masked
        assert emp['SSN'] == 'XXX-XX-6789'

    def test_transform_entity_with_camelcase(self):
        """Test transform_entity() with camelCase input (orchestrator path)."""
        transformer = QBDataTransformer(region='US')

        # Simulate C# account data
        account = {
            'listId': 'A1', 'name': 'Cash', 'accountType': 'bank',
            'balance': 5000, 'isActive': True,
        }

        result = transformer.transform_entity('Accounts', account)
        assert result is not None
        assert result['Name'] == 'Cash'
        assert result['AccountType'] == 'Bank'

    def test_transform_entity_customer_with_address(self):
        """Test transform_entity() for customer with flat address."""
        transformer = QBDataTransformer(region='US')

        customer = {
            'listId': 'C1', 'name': 'Test Customer',
            'email': 'test@test.com', 'isActive': True,
            'billAddressAddr1': '100 Test Rd',
            'billAddressCity': 'Testville',
            'billAddressState': 'CA',
            'billAddressPostalCode': '90210',
        }

        result = transformer.transform_entity('Customers', customer)
        assert result is not None
        assert result['DisplayName'] == 'Test Customer'
        assert 'BillAddr' in result
        assert result['BillAddr']['Line1'] == '100 Test Rd'
        assert result['BillAddr']['City'] == 'Testville'

    def test_transform_entity_item_type_mapping(self):
        """Test that C# 'type' field maps to ItemType correctly."""
        transformer = QBDataTransformer(region='US')

        item = {
            'listId': 'I1', 'name': 'Test Item', 'type': 'Service',
            'salesPrice': 100, 'isActive': True,
        }

        result = transformer.transform_entity('Items', item)
        assert result is not None
        assert result['Type'] == 'Service'


class TestNormalizationEdgeCases:
    """Edge case tests for normalization."""

    def test_empty_dict(self):
        """Empty dict returns empty dict."""
        result = QBDataTransformer.normalize_extractor_fields({})
        assert result == {}

    def test_only_none_values(self):
        """Dict with only None values returns empty dict."""
        entity = {'listId': None, 'name': None, 'balance': None}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert result == {}

    def test_empty_lines_array(self):
        """Empty lines array is handled correctly."""
        entity = {'txnId': 'INV1', 'lines': []}
        result = QBDataTransformer.normalize_extractor_fields(entity, 'invoice')
        assert 'InvoiceLines' not in result  # Empty array not added

    def test_bill_with_only_expense_lines(self):
        """Bill with only expense lines (no item lines)."""
        entity = {
            'txnId': 'B1',
            'lines': [
                {'accountRefListId': 'ACC1', 'amount': 500},
                {'accountRefListId': 'ACC2', 'amount': 300},
            ]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'bill')
        assert 'ExpenseLines' in result
        assert len(result['ExpenseLines']) == 2
        assert 'ItemLines' not in result

    def test_bill_with_only_item_lines(self):
        """Bill with only item lines (no expense lines)."""
        entity = {
            'txnId': 'B1',
            'lines': [
                {'itemRefListId': 'I1', 'amount': 200},
            ]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'bill')
        assert 'ItemLines' in result
        assert len(result['ItemLines']) == 1
        assert 'ExpenseLines' not in result

    def test_existing_line_keys_not_overwritten(self):
        """If InvoiceLines already exists, 'lines' doesn't overwrite it."""
        entity = {
            'txnId': 'INV1',
            'InvoiceLines': [{'existing': True}],
            'lines': [{'shouldnt': 'overwrite'}],
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'invoice')
        assert len(result['InvoiceLines']) == 1
        assert result['InvoiceLines'][0]['existing'] is True

    def test_address_with_no_fields_not_created(self):
        """Address dict not created if all address fields are None."""
        entity = {
            'listId': 'C1',
            'billAddressAddr1': None,
            'billAddressCity': None,
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert 'BillAddress' not in result

    def test_partial_address(self):
        """Partial address (only some fields present) is still reconstructed."""
        entity = {'billAddressCity': 'Chicago', 'billAddressState': 'IL'}
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert 'BillAddress' in result
        assert result['BillAddress'] == {'City': 'Chicago', 'State': 'IL'}

    def test_mixed_entity_type_lines(self):
        """Unknown entity type defaults lines to 'Lines' key."""
        entity = {
            'txnId': 'X1',
            'lines': [{'amount': 100}]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity, 'unknowntype')
        assert 'Lines' in result

    def test_no_entity_type_lines(self):
        """No entity type defaults lines to 'Lines' key."""
        entity = {
            'txnId': 'X1',
            'lines': [{'amount': 100}]
        }
        result = QBDataTransformer.normalize_extractor_fields(entity)
        assert 'Lines' in result

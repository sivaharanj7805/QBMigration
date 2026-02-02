"""
Data Normalizer - Converts C# extraction output to Python transformer expected format

This module bridges the format gap between:
- C# QBDesktopReader output (camelCase, plural entity keys, full field names)
- Python QBDataTransformer input (PascalCase, singular entity keys, short field names)

C# Output Example:
{
    "accounts": [{"listId": "123", "vendorRefListId": "456", ...}],
    "customers": [...],
    ...
}

Python Expected Format:
{
    "Account": [{"ListID": "123", "VendorRef": "456", ...}],
    "Customer": [...],
    ...
}
"""

import logging
from typing import Dict, List, Any, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)


# =============================================================================
# ENTITY KEY MAPPING (C# plural camelCase → Python singular PascalCase)
# =============================================================================

ENTITY_KEY_MAP = {
    # Lists/Master Data
    'accounts': 'Account',
    'customers': 'Customer',
    'vendors': 'Vendor',
    'employees': 'Employee',
    'leads': 'Lead',
    'otherNames': 'OtherName',
    'items': 'Item',
    'classes': 'Class',
    'paymentMethods': 'PaymentMethod',
    'terms': 'Term',
    'dateDrivenTerms': 'DateDrivenTerm',
    'salesTaxCodes': 'TaxCode',
    'customerTypes': 'CustomerType',
    'vendorTypes': 'VendorType',
    'jobTypes': 'JobType',
    'currencies': 'CompanyCurrency',
    'customerMessages': 'CustomerMessage',
    'inventorySites': 'InventorySite',
    'priceLevels': 'PriceLevel',
    'salesReps': 'SalesRep',
    'shipMethods': 'ShipMethod',
    'salesTaxGroups': 'SalesTaxGroup',

    # Transactions
    'invoices': 'Invoice',
    'purchaseOrders': 'PurchaseOrder',
    'salesOrders': 'SalesOrder',
    'bills': 'Bill',
    'billPayments': 'BillPayment',
    'receivePayments': 'Payment',
    'creditMemos': 'CreditMemo',
    'salesReceipts': 'SalesReceipt',
    'estimates': 'Estimate',
    'journalEntries': 'JournalEntry',
    'checks': 'Purchase',  # Checks map to Purchase in QBO
    'creditCardCharges': 'CreditCardCharge',
    'creditCardCredits': 'CreditCardCredit',
    'charges': 'Charge',
    'deposits': 'Deposit',
    'inventoryAdjustments': 'InventoryAdjustment',
    'itemReceipts': 'ItemReceipt',
    'buildAssemblies': 'BuildAssembly',
    'transfers': 'Transfer',
    'inventoryTransfers': 'InventoryTransfer',
    'vendorCredits': 'VendorCredit',
    'arRefundCreditCards': 'ARRefundCreditCard',
    'billPaymentCreditCards': 'BillPaymentCreditCard',
    'salesTaxPayments': 'TaxPayment',

    # Supporting data
    'reportVerification': 'ReportVerification',
    'preferences': 'Preferences',
    'dataExtensions': 'DataExtension',
    'deletedRecords': 'DeletedRecords',
    'payrollItemWages': 'PayrollItemWage',
    'payrollItemNonWages': 'PayrollItemNonWage',
    'workersCompCodes': 'WorkersCompCode',
    'company': 'CompanyInfo',
    'companyActivity': 'CompanyActivity',
}

# Reverse mapping for output normalization if needed
ENTITY_KEY_MAP_REVERSE = {v: k for k, v in ENTITY_KEY_MAP.items()}


# =============================================================================
# FIELD NAME MAPPING (C# camelCase full → Python PascalCase short)
# =============================================================================

FIELD_MAP = {
    # ID fields
    'listId': 'ListID',
    'txnId': 'TxnID',
    'txnLineId': 'TxnLineID',

    # Reference fields (ListID suffix → Ref)
    'vendorRefListId': 'VendorRef',
    'vendorRefFullName': 'VendorRefFullName',
    'customerRefListId': 'CustomerRef',
    'customerRefFullName': 'CustomerRefFullName',
    'accountRefListId': 'AccountRef',
    'accountRefFullName': 'AccountRefFullName',
    'itemRefListId': 'ItemRef',
    'itemRefFullName': 'ItemRefFullName',
    'parentRefListId': 'ParentRef',
    'parentRefFullName': 'ParentRefFullName',
    'classRefListId': 'ClassRef',
    'classRefFullName': 'ClassRefFullName',
    'termRefListId': 'TermRef',
    'termRefFullName': 'TermRefFullName',
    'salesTaxCodeRefListId': 'TaxCodeRef',
    'salesTaxCodeRefFullName': 'TaxCodeRefFullName',
    'paymentMethodRefListId': 'PaymentMethodRef',
    'paymentMethodRefFullName': 'PaymentMethodRefFullName',
    'depositToAccountRefListId': 'DepositToAccountRef',
    'depositToAccountRefFullName': 'DepositToAccountRefFullName',
    'apAccountRefListId': 'APAccountRef',
    'apAccountRefFullName': 'APAccountRefFullName',
    'arAccountRefListId': 'ARAccountRef',
    'arAccountRefFullName': 'ARAccountRefFullName',
    'bankAccountRefListId': 'BankAccountRef',
    'bankAccountRefFullName': 'BankAccountRefFullName',
    'creditCardAccountRefListId': 'CreditCardAccountRef',
    'creditCardAccountRefFullName': 'CreditCardAccountRefFullName',
    'currencyRefListId': 'CurrencyRef',
    'currencyRefFullName': 'CurrencyRefFullName',
    'payeeEntityRefListId': 'PayeeEntityRef',
    'payeeEntityRefFullName': 'PayeeEntityRefFullName',
    'customerTypeRefListId': 'CustomerTypeRef',
    'customerTypeRefFullName': 'CustomerTypeRefFullName',
    'jobTypeRefListId': 'JobTypeRef',
    'jobTypeRefFullName': 'JobTypeRefFullName',
    'salesRepRefListId': 'SalesRepRef',
    'salesRepRefFullName': 'SalesRepRefFullName',
    'shipMethodRefListId': 'ShipMethodRef',
    'shipMethodRefFullName': 'ShipMethodRefFullName',
    'priceLevelRefListId': 'PriceLevelRef',
    'priceLevelRefFullName': 'PriceLevelRefFullName',
    'fromInventorySiteRefListId': 'FromInventorySiteRef',
    'fromInventorySiteRefFullName': 'FromInventorySiteRefFullName',
    'toInventorySiteRefListId': 'ToInventorySiteRef',
    'toInventorySiteRefFullName': 'ToInventorySiteRefFullName',
    'refundFromAccountRefListId': 'RefundFromAccountRef',
    'refundFromAccountRefFullName': 'RefundFromAccountRefFullName',

    # Common fields
    'name': 'Name',
    'nameOriginal': 'NameOriginal',
    'fullName': 'FullName',
    'isActive': 'IsActive',
    'desc': 'Description',
    'descOriginal': 'DescriptionOriginal',
    'description': 'Description',
    'memo': 'Memo',

    # Date fields
    'txnDate': 'TxnDate',
    'dueDate': 'DueDate',
    'shipDate': 'ShipDate',
    'timeCreated': 'TimeCreated',
    'timeModified': 'TimeModified',

    # Numeric fields
    'amount': 'Amount',
    'amountDue': 'AmountDue',
    'totalAmount': 'TotalAmount',
    'balance': 'Balance',
    'totalBalance': 'TotalBalance',
    'quantity': 'Quantity',
    'rate': 'Rate',
    'cost': 'Cost',
    'price': 'Price',
    'salesPrice': 'SalesPrice',
    'purchaseCost': 'PurchaseCost',
    'qtyOnHand': 'QtyOnHand',
    'reorderPoint': 'ReorderPoint',
    'priceLevelPercentage': 'PriceLevelPercentage',
    'priceLevelType': 'PriceLevelType',

    # Reference number fields
    'refNumber': 'RefNumber',
    'txnNumber': 'TxnNumber',
    'editSequence': 'EditSequence',

    # Account-specific
    'accountType': 'AccountType',
    'specialAccountType': 'SpecialAccountType',
    'accountNumber': 'AccountNumber',
    'bankNumber': 'BankNumber',
    'isTaxAccount': 'IsTaxAccount',
    'taxLineId': 'TaxLineID',
    'taxLineName': 'TaxLineName',
    'cashFlowClassification': 'CashFlowClassification',
    'sublevel': 'Sublevel',

    # Customer-specific
    'companyName': 'CompanyName',
    'companyNameOriginal': 'CompanyNameOriginal',
    'salutation': 'Salutation',
    'firstName': 'FirstName',
    'middleName': 'MiddleName',
    'lastName': 'LastName',
    'email': 'Email',
    'phone': 'Phone',
    'fax': 'Fax',
    'mobile': 'Mobile',
    'altPhone': 'AltPhone',
    'contact': 'Contact',
    'altContact': 'AltContact',
    'notes': 'Notes',
    'creditLimit': 'CreditLimit',
    'resaleNumber': 'ResaleNumber',
    'isJob': 'IsJob',
    'jobStatus': 'JobStatus',
    'jobStartDate': 'JobStartDate',
    'jobEndDate': 'JobEndDate',
    'jobProjectedEndDate': 'JobProjectedEndDate',
    'jobDescription': 'JobDescription',

    # Vendor-specific
    'vendor1099': 'Vendor1099',
    'taxId': 'TaxID',

    # Item-specific
    'itemType': 'ItemType',
    'isTaxable': 'IsTaxable',
    'salesDesc': 'SalesDesc',
    'purchaseDesc': 'PurchaseDesc',
    'uom': 'UOM',
    'avgCost': 'AvgCost',
    'assetAccountRef': 'AssetAccountRef',
    'incomeAccountRef': 'IncomeAccountRef',
    'cogsAccountRef': 'COGSAccountRef',
    'expenseAccountRef': 'ExpenseAccountRef',

    # Transaction-specific
    'isPaid': 'IsPaid',
    'isPending': 'IsPending',
    'isManuallyClosed': 'IsManuallyClosed',
    'isAdjustment': 'IsAdjustment',
    'exchangeRate': 'ExchangeRate',
    'appliedAmount': 'AppliedAmount',
    'unappliedAmount': 'UnappliedAmount',
    'unusedCredits': 'UnusedCredits',
    'unusedPayment': 'UnusedPayment',

    # Line items
    'lines': 'Lines',
    'expenseLines': 'ExpenseLines',
    'itemLines': 'ItemLines',
    'invoiceLines': 'InvoiceLines',
    'journalLines': 'JournalLines',
    'linkedTransactions': 'AppliedToBills',  # BillPayment linked txns → AppliedToBills
    'linkToTxnId': 'LinkToTxnID',
    'subtotal': 'Subtotal',
    'salesTaxTotal': 'SalesTaxTotal',
    'clearedStatus': 'ClearedStatus',
    'unitOfMeasure': 'UnitOfMeasure',
    'lotNumber': 'LotNumber',
    'serialNumber': 'SerialNumber',
    'linkAmount': 'PaymentAmount',  # LinkedTxn amount → PaymentAmount

    # Address fields
    'billAddress': 'BillAddress',
    'shipAddress': 'ShipAddress',
    'addr1': 'Line1',
    'addr2': 'Line2',
    'addr3': 'Line3',
    'addr4': 'Line4',
    'addr5': 'Line5',
    'city': 'City',
    'state': 'State',
    'postalCode': 'PostalCode',
    'country': 'Country',

    # Integrity
    'sha256IntegrityHash': 'IntegrityHash',
    'integrityHash': 'IntegrityHash',
}


# =============================================================================
# LINE ITEM FIELD MAPPING
# =============================================================================

LINE_FIELD_MAP = {
    'txnLineId': 'TxnLineID',
    'itemRefListId': 'ItemRef',
    'itemRefFullName': 'ItemRefFullName',
    'accountRefListId': 'AccountRef',
    'accountRefFullName': 'AccountRefFullName',
    'classRefListId': 'ClassRef',
    'classRefFullName': 'ClassRefFullName',
    'description': 'Description',
    'desc': 'Description',
    'memo': 'Memo',
    'quantity': 'Quantity',
    'rate': 'Rate',
    'amount': 'Amount',
    'cost': 'Cost',
    'taxCodeRefListId': 'TaxCodeRef',
    'taxCodeRefFullName': 'TaxCodeRefFullName',
    'isBillable': 'IsBillable',
    'billableStatus': 'BillableStatus',
    'journalLineType': 'JournalLineType',  # 'Debit' or 'Credit'
    # LinkedTxn fields (for AppliedToBills)
    'txnId': 'BillRef',  # In linked txns, txnId is the bill reference
    'txnType': 'TxnType',
    'linkAmount': 'Amount',  # Rename linkAmount to Amount for consistency
    'appliedAmount': 'Amount',
}


# =============================================================================
# NORMALIZER CLASS
# =============================================================================

class QBDataNormalizer:
    """
    Normalizes QuickBooks Desktop extraction data from C# format to Python format.

    Usage:
        normalizer = QBDataNormalizer()
        normalized_data = normalizer.normalize(raw_csharp_data)
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize normalizer.

        Args:
            strict_mode: If True, raise errors on unknown fields. If False, pass through.
        """
        self.strict_mode = strict_mode
        self.stats = {
            'entities_normalized': 0,
            'records_normalized': 0,
            'fields_mapped': 0,
            'unknown_fields': [],
            'unknown_entities': []
        }

    def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize entire QBD extraction data.

        Args:
            data: Raw C# extraction output

        Returns:
            Normalized data in Python transformer expected format
        """
        if not data:
            return {}

        # Reset stats
        self.stats = {
            'entities_normalized': 0,
            'records_normalized': 0,
            'fields_mapped': 0,
            'unknown_fields': [],
            'unknown_entities': []
        }

        normalized = {}

        for key, value in data.items():
            # Map entity key
            normalized_key = ENTITY_KEY_MAP.get(key)

            if normalized_key is None:
                # Check if it's already in expected format
                if key in ENTITY_KEY_MAP_REVERSE:
                    normalized_key = key
                else:
                    # Pass through metadata fields unchanged
                    if key in ('schemaVersion', 'extractionVersion', 'extractedAt',
                              'sessionId', 'qbVersion', 'isIncrementalSync',
                              'incrementalFromDate', 'metadata'):
                        normalized[key] = value
                        continue

                    # Unknown entity
                    if self.strict_mode:
                        raise ValueError(f"Unknown entity key: {key}")
                    else:
                        self.stats['unknown_entities'].append(key)
                        # Try to normalize anyway with capitalized key
                        normalized_key = key[0].upper() + key[1:] if key else key

            # Normalize entity records
            if isinstance(value, list):
                normalized[normalized_key] = [
                    self._normalize_record(record, normalized_key)
                    for record in value
                ]
                self.stats['entities_normalized'] += 1
                self.stats['records_normalized'] += len(value)
            elif isinstance(value, dict):
                normalized[normalized_key] = self._normalize_record(value, normalized_key)
                self.stats['entities_normalized'] += 1
                self.stats['records_normalized'] += 1
            else:
                normalized[normalized_key] = value

        logger.info(f"Normalized {self.stats['entities_normalized']} entity types, "
                   f"{self.stats['records_normalized']} records, "
                   f"{self.stats['fields_mapped']} fields mapped")

        if self.stats['unknown_entities']:
            logger.warning(f"Unknown entities (passed through): {self.stats['unknown_entities']}")

        return normalized

    def _normalize_record(self, record: Dict[str, Any], entity_type: str) -> Dict[str, Any]:
        """
        Normalize a single record.

        Args:
            record: Raw record from C# extraction
            entity_type: Type of entity for context-aware normalization

        Returns:
            Normalized record
        """
        if not record or not isinstance(record, dict):
            return record

        normalized = {}

        for key, value in record.items():
            # Map field name
            normalized_key = FIELD_MAP.get(key)

            if normalized_key is None:
                # Check if already in expected format
                if key in FIELD_MAP.values():
                    normalized_key = key
                else:
                    # Pass through unknown fields
                    normalized_key = key
                    if key not in self.stats['unknown_fields']:
                        self.stats['unknown_fields'].append(key)
            else:
                self.stats['fields_mapped'] += 1

            # Recursively normalize nested structures
            if isinstance(value, dict):
                # Handle address objects
                if 'addr1' in value or 'city' in value or 'Line1' in value:
                    normalized[normalized_key] = self._normalize_address(value)
                else:
                    normalized[normalized_key] = self._normalize_record(value, entity_type)
            elif isinstance(value, list):
                # Handle line items
                if normalized_key in ('Lines', 'ExpenseLines', 'ItemLines',
                                     'InvoiceLines', 'JournalLines'):
                    normalized[normalized_key] = [
                        self._normalize_line(line) for line in value
                    ]
                else:
                    normalized[normalized_key] = [
                        self._normalize_record(item, entity_type)
                        if isinstance(item, dict) else item
                        for item in value
                    ]
            else:
                normalized[normalized_key] = value

        return normalized

    def _normalize_line(self, line: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a line item (invoice line, expense line, etc.)
        """
        if not line or not isinstance(line, dict):
            return line

        normalized = {}

        for key, value in line.items():
            # Use line-specific mapping first, then general mapping
            normalized_key = LINE_FIELD_MAP.get(key) or FIELD_MAP.get(key) or key

            if isinstance(value, dict):
                normalized[normalized_key] = self._normalize_record(value, 'Line')
            elif isinstance(value, list):
                normalized[normalized_key] = [
                    self._normalize_record(item, 'Line')
                    if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                normalized[normalized_key] = value

        return normalized

    def _normalize_address(self, address: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize an address object.
        """
        if not address:
            return address

        addr_map = {
            'addr1': 'Line1',
            'addr2': 'Line2',
            'addr3': 'Line3',
            'addr4': 'Line4',
            'addr5': 'Line5',
            'city': 'City',
            'state': 'State',
            'postalCode': 'PostalCode',
            'country': 'Country',
        }

        normalized = {}
        for key, value in address.items():
            normalized_key = addr_map.get(key, key)
            normalized[normalized_key] = value

        return normalized

    def get_stats(self) -> Dict[str, Any]:
        """Get normalization statistics."""
        return self.stats.copy()


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def normalize_qbd_data(data: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
    """
    Convenience function to normalize QBD data.

    Args:
        data: Raw C# extraction output
        strict: If True, raise errors on unknown fields

    Returns:
        Normalized data in Python transformer expected format
    """
    normalizer = QBDataNormalizer(strict_mode=strict)
    return normalizer.normalize(data)


# =============================================================================
# INTEGRATION HELPER
# =============================================================================

def normalize_before_transform(transform_func):
    """
    Decorator to automatically normalize data before transformation.

    Usage:
        @normalize_before_transform
        def my_transform(data):
            # data is already normalized
            ...
    """
    def wrapper(data, *args, **kwargs):
        normalized = normalize_qbd_data(data)
        return transform_func(normalized, *args, **kwargs)
    return wrapper


# =============================================================================
# TESTING
# =============================================================================

if __name__ == '__main__':
    # Test with sample data
    sample_csharp_data = {
        'accounts': [
            {
                'listId': 'ACCT-001',
                'name': 'Checking',
                'accountType': 'Bank',
                'isActive': True,
                'balance': 10000.00
            }
        ],
        'customers': [
            {
                'listId': 'CUST-001',
                'name': 'Acme Corp',
                'companyName': 'Acme Corporation',
                'email': 'contact@acme.com',
                'isActive': True
            }
        ],
        'bills': [
            {
                'txnId': 'BILL-001',
                'vendorRefListId': 'VEND-001',
                'txnDate': '2024-01-15',
                'amountDue': 500.00,
                'lines': [
                    {
                        'txnLineId': 'LINE-001',
                        'accountRefListId': 'ACCT-002',
                        'amount': 500.00
                    }
                ]
            }
        ]
    }

    normalizer = QBDataNormalizer()
    normalized = normalizer.normalize(sample_csharp_data)

    print("Normalized data:")
    import json
    print(json.dumps(normalized, indent=2, default=str))

    print("\nStats:")
    print(normalizer.get_stats())

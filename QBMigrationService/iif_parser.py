"""
QuickBooks Desktop IIF File Parser
Parses IIF (Intuit Interchange Format) files exported from QuickBooks Desktop

IIF is a tab-delimited format used by QuickBooks for importing/exporting data.
This parser converts IIF files to JSON format for migration to QuickBooks Online.
"""

import os
import json
import csv
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
import logging

logger = logging.getLogger(__name__)



class IIFParser:
    """Parser for QuickBooks Desktop IIF export files"""
    
    # IIF record types and their field mappings
    RECORD_TYPES = {
        'CUST': 'customers',
        'VEND': 'vendors', 
        'INVITEM': 'items',
        'ACCNT': 'accounts',
        'EMP': 'employees',
        'TRNS': 'transactions',
        'SPL': 'transaction_splits',
        'CLASS': 'classes',
        'TERMS': 'terms',
        'SHIPMETH': 'shipping_methods',
        'PAYMETH': 'payment_methods',
        'OTHERNAME': 'other_names',
        'INVMEMO': 'memos',
        'TODO': 'todos',
        'TIMEACT': 'time_activities',
        'BUDGET': 'budgets',
    }
    
    def __init__(self):
        self.data = {key: [] for key in self.RECORD_TYPES.values()}
        self.headers = {}
        self.errors = []
        self.stats = {
            'total_lines': 0,
            'parsed_records': 0,
            'skipped_lines': 0,
            'errors': 0
        }
    
    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """Parse an IIF file and return structured data
        AUDIT FIX: Added robust path validation with proper containment check
        """
        # Reset state for fresh parse
        self.data = {key: [] for key in self.RECORD_TYPES.values()}
        self.headers = {}
        self.errors = []
        self.stats = {'total_lines': 0, 'parsed_records': 0, 'skipped_lines': 0, 'errors': 0}

        # Security: Robust path traversal prevention
        # 1. Normalize the path to resolve any relative components
        real_path = os.path.realpath(file_path)

        # 2. Define allowed base directories (current working directory or explicit data dir)
        allowed_base_dirs = [
            os.path.realpath(os.getcwd()),
            os.path.realpath(os.path.dirname(__file__)),
        ]

        # Add DATA_DIR from environment if configured
        data_dir = os.environ.get('DATA_DIR')
        if data_dir:
            allowed_base_dirs.append(os.path.realpath(data_dir))

        # 3. Check that the resolved path is within one of the allowed directories
        is_path_allowed = any(
            real_path.startswith(base_dir + os.sep) or real_path == base_dir
            for base_dir in allowed_base_dirs
        )

        if not is_path_allowed:
            raise ValueError(f"Security: File path is outside allowed directories: {file_path}")

        # 4. Verify the file exists and is a regular file (not symlink to outside)
        if not os.path.isfile(real_path):
            raise ValueError(f"Invalid file path (not a file): {file_path}")

        with open(real_path, 'r', encoding='utf-8', errors='replace') as f:
            return self.parse_content(f.read())
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Parse IIF content string"""
        # Reset state for fresh parse
        self.data = {key: [] for key in self.RECORD_TYPES.values()}
        self.headers = {}
        self.errors = []
        self.stats = {'total_lines': 0, 'parsed_records': 0, 'skipped_lines': 0, 'errors': 0}

        lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        self.stats['total_lines'] = len(lines)
        
        # AUDIT FIX: Removed unused current_type variable

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                self.stats['skipped_lines'] += 1
                continue
            
            try:
                fields = line.split('\t')
                record_type = fields[0].upper() if fields else ''
                
                # Header line defines columns
                if record_type.startswith('!'):
                    header_type = record_type[1:]  # Remove the !
                    self.headers[header_type] = fields[1:]
                    
                # Transaction split line (must be checked before general RECORD_TYPES)
                elif record_type == 'SPL':
                    headers = self.headers.get('SPL', [])
                    record = {}
                    for i, value in enumerate(fields[1:], 0):
                        if i < len(headers):
                            record[headers[i]] = value.strip()
                    record['_source_line'] = line_num
                    record['_record_type'] = 'SPL'
                    self.data['transaction_splits'].append(record)
                    self.stats['parsed_records'] += 1

                # Data line
                elif record_type in self.RECORD_TYPES:
                    data_key = self.RECORD_TYPES[record_type]
                    headers = self.headers.get(record_type, [])

                    record = {}
                    for i, value in enumerate(fields[1:], 0):
                        if i < len(headers):
                            record[headers[i]] = value.strip()
                        else:
                            record[f'field_{i}'] = value.strip()

                    record['_source_line'] = line_num
                    record['_record_type'] = record_type
                    self.data[data_key].append(record)
                    self.stats['parsed_records'] += 1
                    
                elif record_type == 'ENDTRNS':
                    # End of transaction marker
                    pass
                    
                else:
                    self.stats['skipped_lines'] += 1
                    
            except Exception as e:
                self.errors.append({
                    'line': line_num,
                    'content': line[:100],
                    'error': str(e)
                })
                self.stats['errors'] += 1
        
        return self.get_result()
    
    def get_result(self) -> Dict[str, Any]:
        """Get parsed result with metadata"""
        return {
            'metadata': {
                'parsed_at': datetime.now(timezone.utc).isoformat(),
                'stats': self.stats,
                'errors': self.errors[:100]  # Limit error list
            },
            'data': self.data,
            'summary': self._get_summary()
        }
    
    def _get_summary(self) -> Dict[str, int]:
        """Get count of records by type"""
        return {key: len(value) for key, value in self.data.items() if value}


class QuickBooksExportParser:
    """
    Unified parser for QuickBooks Desktop exports
    Supports: IIF, CSV, Excel exports
    """
    
    def __init__(self):
        self.iif_parser = IIFParser()
        self.data = {}
        self.file_type = None
    
    def parse(self, file_path: str) -> Dict[str, Any]:
        """Parse a QuickBooks export file (auto-detect format)"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.iif':
            self.file_type = 'iif'
            return self.iif_parser.parse_file(file_path)
        elif ext == '.csv':
            self.file_type = 'csv'
            return self._parse_csv(file_path)
        elif ext in ['.xls', '.xlsx']:
            self.file_type = 'excel'
            return self._parse_excel(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
    
    def _validate_file_path(self, file_path: str) -> str:
        """Validate file path for security (path traversal prevention)"""
        real_path = os.path.realpath(file_path)
        allowed_base_dirs = [
            os.path.realpath(os.getcwd()),
            os.path.realpath(os.path.dirname(__file__)),
        ]
        data_dir = os.environ.get('DATA_DIR')
        if data_dir:
            allowed_base_dirs.append(os.path.realpath(data_dir))

        is_path_allowed = any(
            real_path.startswith(base_dir + os.sep) or real_path == base_dir
            for base_dir in allowed_base_dirs
        )
        if not is_path_allowed:
            raise ValueError(f"Security: File path is outside allowed directories: {file_path}")
        if not os.path.isfile(real_path):
            raise ValueError(f"Invalid file path (not a file): {file_path}")
        return real_path

    def _parse_csv(self, file_path: str) -> Dict[str, Any]:
        """Parse CSV export from QuickBooks"""
        # Security: Validate path
        real_path = self._validate_file_path(file_path)
        records = []

        with open(real_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Clean up keys and values (handle None keys from extra columns)
                clean_row = {
                    (k.strip() if k else '_unknown'): v.strip() if v else ''
                    for k, v in row.items() if k is not None
                }
                records.append(clean_row)
        
        # Detect entity type from headers or filename
        entity_type = self._detect_entity_type(file_path, records)
        
        return {
            'metadata': {
                'parsed_at': datetime.now(timezone.utc).isoformat(),
                'file_type': 'csv',
                'record_count': len(records)
            },
            'data': {entity_type: records},
            'summary': {entity_type: len(records)}
        }
    
    def _parse_excel(self, file_path: str) -> Dict[str, Any]:
        """Parse Excel export from QuickBooks"""
        # Security: Validate path
        real_path = self._validate_file_path(file_path)
        try:
            import openpyxl
        except ImportError:
            raise ImportError("openpyxl required for Excel parsing. Install with: pip install openpyxl")

        wb = openpyxl.load_workbook(real_path, read_only=True)
        all_data = {}
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            
            if not rows:
                continue
            
            headers = [str(h).strip() if h else f'col_{i}' for i, h in enumerate(rows[0])]
            records = []
            
            for row in rows[1:]:
                record = {}
                for i, value in enumerate(row):
                    if i < len(headers):
                        record[headers[i]] = str(value).strip() if value else ''
                records.append(record)
            
            if records:
                all_data[sheet_name.lower().replace(' ', '_')] = records
        
        return {
            'metadata': {
                'parsed_at': datetime.now(timezone.utc).isoformat(),
                'file_type': 'excel',
                'sheets': list(all_data.keys())
            },
            'data': all_data,
            'summary': {k: len(v) for k, v in all_data.items()}
        }
    
    def _detect_entity_type(self, file_path: str, records: List[Dict]) -> str:
        """Detect entity type from filename or content"""
        filename = os.path.basename(file_path).lower()

        # Check filename with word boundary matching
        type_hints = {
            'customers': 'customers',
            'customer': 'customers',
            'vendors': 'vendors',
            'vendor': 'vendors',
            'invoices': 'invoices',
            'invoice': 'invoices',
            'bills': 'bills',
            'bill': 'bills',
            'payments': 'payments',
            'payment': 'payments',
            'accounts': 'accounts',
            'account': 'accounts',
            'items': 'items',
            'item': 'items',
            'employees': 'employees',
            'employee': 'employees',
            'journal': 'journal_entries',
        }

        # Use word boundary matching instead of substring
        filename_lower = os.path.basename(filename).replace('.csv', '').replace('.xlsx', '').replace('.xls', '')
        for hint, entity_type in type_hints.items():
            # Check for exact match or word boundary
            if filename_lower == hint or filename_lower.startswith(hint + '_') or filename_lower.endswith('_' + hint):
                return entity_type
        
        # Check headers
        if records:
            headers = set(records[0].keys())
            if 'Customer' in headers or 'Company' in headers:
                return 'customers'
            elif 'Vendor' in headers:
                return 'vendors'
            elif 'Invoice #' in headers or 'Invoice Number' in headers:
                return 'invoices'
        
        return 'unknown'


def transform_for_qbo(iif_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform parsed IIF data to QuickBooks Online format
    """
    qbo_data = {
        'customers': [],
        'vendors': [],
        'items': [],
        'accounts': [],
        'invoices': [],
        'bills': [],
        'payments': [],
    }
    
    # Transform customers
    for cust in iif_data.get('data', {}).get('customers', []):
        qbo_data['customers'].append({
            'DisplayName': cust.get('NAME', ''),
            'CompanyName': cust.get('COMPANYNAME', ''),
            'GivenName': cust.get('FIRSTNAME', ''),
            'FamilyName': cust.get('LASTNAME', ''),
            'PrimaryEmailAddr': {'Address': cust.get('EMAIL', '')},
            'PrimaryPhone': {'FreeFormNumber': cust.get('PHONE1', '')},
            'BillAddr': {
                'Line1': cust.get('BADDR1', ''),
                'Line2': cust.get('BADDR2', ''),
                'City': cust.get('BADDR3', ''),
                'CountrySubDivisionCode': cust.get('BADDR4', ''),
                'PostalCode': cust.get('BADDR5', ''),
            },
            '_source': 'iif_import',
            '_original_id': cust.get('NAME', '')
        })
    
    # Transform vendors
    for vend in iif_data.get('data', {}).get('vendors', []):
        qbo_data['vendors'].append({
            'DisplayName': vend.get('NAME', ''),
            'CompanyName': vend.get('COMPANYNAME', ''),
            'GivenName': vend.get('FIRSTNAME', ''),
            'FamilyName': vend.get('LASTNAME', ''),
            'PrimaryEmailAddr': {'Address': vend.get('EMAIL', '')},
            'PrimaryPhone': {'FreeFormNumber': vend.get('PHONE1', '')},
            '_source': 'iif_import',
            '_original_id': vend.get('NAME', '')
        })
    
    # Transform accounts
    for acct in iif_data.get('data', {}).get('accounts', []):
        acct_type_map = {
            'BANK': 'Bank',
            'AR': 'Accounts Receivable',
            'AP': 'Accounts Payable',
            'CCARD': 'Credit Card',
            'INC': 'Income',
            'EXP': 'Expense',
            'FIXASSET': 'Fixed Asset',
            'OASSET': 'Other Asset',
            'OCURLIAB': 'Other Current Liability',
            'LTLIAB': 'Long Term Liability',
            'EQUITY': 'Equity',
            'COGS': 'Cost of Goods Sold',
        }
        
        qbo_data['accounts'].append({
            'Name': acct.get('NAME', ''),
            'AccountType': acct_type_map.get(acct.get('ACCNTTYPE', ''), 'Expense'),
            'Description': acct.get('DESC', ''),
            '_source': 'iif_import',
            '_original_id': acct.get('NAME', '')
        })
    
    # Transform items
    for item in iif_data.get('data', {}).get('items', []):
        item_type = item.get('INVITEMTYPE', 'SERV')
        type_map = {
            'SERV': 'Service',
            'PART': 'NonInventory',
            'INVENTORY': 'Inventory',
            'ASSEMBLY': 'Inventory',
            'OTHCHARGE': 'Service',
            'DISCOUNT': 'Service',
            'PAYMENT': 'Service',
            'SUBTOTAL': 'Service',
            'GROUP': 'Bundle',
            'FIXEDASSET': 'NonInventory',
        }
        qbo_type = type_map.get(item_type, 'Service')
        qbo_data['items'].append({
            'Name': item.get('NAME', ''),
            'Description': item.get('DESC', ''),
            'UnitPrice': Decimal(str(item.get('PRICE', 0) or 0)),
            'Type': qbo_type,
            '_source': 'iif_import',
            '_original_id': item.get('NAME', '')
        })
    
    return qbo_data


# CLI for testing
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        logger.info("Usage: python iif_parser.py <file.iif>")
        sys.exit(1)
    
    parser = QuickBooksExportParser()
    result = parser.parse(sys.argv[1])
    
    logger.info(json.dumps(result, indent=2, default=str))

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
from datetime import datetime
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
        """Parse an IIF file and return structured data"""
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return self.parse_content(f.read())
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Parse IIF content string"""
        lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        self.stats['total_lines'] = len(lines)
        
        current_type = None
        
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
                    current_type = header_type
                    
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
                    
                # Transaction split line
                elif record_type == 'SPL':
                    headers = self.headers.get('SPL', [])
                    record = {}
                    for i, value in enumerate(fields[1:], 0):
                        if i < len(headers):
                            record[headers[i]] = value.strip()
                    record['_source_line'] = line_num
                    self.data['transaction_splits'].append(record)
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
                'parsed_at': datetime.utcnow().isoformat(),
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
    
    def _parse_csv(self, file_path: str) -> Dict[str, Any]:
        """Parse CSV export from QuickBooks"""
        records = []
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Clean up keys and values
                clean_row = {
                    k.strip(): v.strip() if v else ''
                    for k, v in row.items()
                }
                records.append(clean_row)
        
        # Detect entity type from headers or filename
        entity_type = self._detect_entity_type(file_path, records)
        
        return {
            'metadata': {
                'parsed_at': datetime.utcnow().isoformat(),
                'file_type': 'csv',
                'record_count': len(records)
            },
            'data': {entity_type: records},
            'summary': {entity_type: len(records)}
        }
    
    def _parse_excel(self, file_path: str) -> Dict[str, Any]:
        """Parse Excel export from QuickBooks"""
        try:
            import openpyxl
        except ImportError:
            raise ImportError("openpyxl required for Excel parsing. Install with: pip install openpyxl")
        
        wb = openpyxl.load_workbook(file_path, read_only=True)
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
                'parsed_at': datetime.utcnow().isoformat(),
                'file_type': 'excel',
                'sheets': list(all_data.keys())
            },
            'data': all_data,
            'summary': {k: len(v) for k, v in all_data.items()}
        }
    
    def _detect_entity_type(self, file_path: str, records: List[Dict]) -> str:
        """Detect entity type from filename or content"""
        filename = os.path.basename(file_path).lower()
        
        # Check filename
        type_hints = {
            'customer': 'customers',
            'vendor': 'vendors',
            'invoice': 'invoices',
            'bill': 'bills',
            'payment': 'payments',
            'account': 'accounts',
            'item': 'items',
            'employee': 'employees',
            'journal': 'journal_entries',
        }
        
        for hint, entity_type in type_hints.items():
            if hint in filename:
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
        qbo_data['items'].append({
            'Name': item.get('NAME', ''),
            'Description': item.get('DESC', ''),
            'UnitPrice': item.get('PRICE', 0),
            'Type': 'Service' if item.get('INVITEMTYPE') == 'SERV' else 'Inventory',
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

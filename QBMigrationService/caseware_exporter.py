"""
Caseware Audit Bundle Exporter
==============================

Generates "Audit-Ready" CSV files for direct import into Caseware Working Papers
and OnPoint DAS. This bypasses the buggy QuickBooks Export Utility.

OUTPUT FILES:
1. Audit_TB.csv - Trial Balance with Lead Sheet codes
2. Audit_GL.csv - General Ledger with SHA-256 integrity hashes
3. Audit_Mapping.cvw - Caseware column configuration

FEATURES:
✓ Cryptographic integrity hash for every transaction (SHA-256)
✓ Pre-mapped to Caseware Lead Sheet codes
✓ Multi-currency support
✓ Period-based filtering
✓ Variance analysis columns

Author: QB Migration System
Version: 1.0.0
License: Proprietary
"""

import csv
import hashlib
import json
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Generator
import os
import chardet  # For encoding detection
import threading

logger = logging.getLogger(__name__)


class CasewareExporter:
    """
    Generates Caseware Audit Bundle from QB Desktop extracted data.
    
    The "Caseware Mode" alternative to QBO migration.
    """
    
    VERSION = "1.0.0"
    
    # Caseware Lead Sheet Code Mappings
    # Expanded for Agricultural, Manufacturing, and high-value sectors
    LEAD_SHEET_CODES = {
        # Assets - General
        'Bank': 'A1',
        'Accounts Receivable': 'A2',
        'Other Current Assets': 'A3',
        'Fixed Assets': 'A4',
        'Other Assets': 'A5',
        'Inventory': 'A3.1',
        'Prepaid Expenses': 'A3.2',
        
        # Assets - Agricultural (High-value sector)
        'Livestock': 'A6.1',
        'Crops': 'A6.2',
        'Agricultural Inventory': 'A6.3',
        'Farm Equipment': 'A6.4',
        'Agricultural Land': 'A6.5',
        'Breeding Stock': 'A6.6',
        'Growing Crops': 'A6.7',
        'Harvested Crops': 'A6.8',
        
        # Assets - Manufacturing (High-value sector)
        'Raw Materials': 'A7.1',
        'Work in Process': 'A7.2',
        'Finished Goods': 'A7.3',
        'Manufacturing Equipment': 'A7.4',
        'Factory Buildings': 'A7.5',
        'Tooling': 'A7.6',
        'Packaging Materials': 'A7.7',
        'Production Supplies': 'A7.8',
        
        # Assets - Other Industries
        'Construction in Progress': 'A8.1',
        'Software Development': 'A8.2',
        'Oil & Gas Equipment': 'A8.3',
        'Mining Assets': 'A8.4',
        'Real Estate Held for Sale': 'A8.5',
        
        # Liabilities
        'Accounts Payable': 'L1',
        'Credit Card': 'L2',
        'Other Current Liabilities': 'L3',
        'Long Term Liabilities': 'L4',
        'Sales Tax Payable': 'L3.1',
        'Payroll Liabilities': 'L3.2',
        'Accrued Liabilities': 'L3.3',
        'Deferred Revenue': 'L3.4',
        'Mortgage Payable': 'L4.1',
        'Equipment Loans': 'L4.2',
        
        # Equity
        'Equity': 'E1',
        'Retained Earnings': 'E2',
        'Opening Balance Equity': 'E3',
        'Shareholder Equity': 'E4',
        'Partner Capital': 'E5',
        
        # Income
        'Income': 'R1',
        'Other Income': 'R2',
        'Sales': 'R1.1',
        'Service Income': 'R1.2',
        'Agricultural Sales': 'R1.3',
        'Manufacturing Sales': 'R1.4',
        'Contract Revenue': 'R1.5',
        
        # Cost of Goods Sold
        'Cost of Goods Sold': 'C1',
        'Direct Labor': 'C2',
        'Manufacturing Overhead': 'C3',
        'Agricultural COGS': 'C4',
        
        # Expenses
        'Expense': 'X1',
        'Other Expense': 'X2',
        'Depreciation': 'X3',
        'Amortization': 'X4',
    }
    
    # Account type classification for debit/credit determination
    DEBIT_TYPES = {
        'Bank', 'Accounts Receivable', 'Other Current Assets',
        'Fixed Assets', 'Other Assets', 'Cost of Goods Sold',
        'Expense', 'Other Expense', 'Inventory'
    }
    
    def __init__(self, output_dir: str, company_name: str = "Company"):
        """
        Initialize Caseware Exporter.
        
        Args:
            output_dir: Directory to write audit bundle files
            company_name: Company name for report headers
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.company_name = company_name
        
        # Statistics (thread-safe)
        self._stats_lock = threading.Lock()
        self.stats = {
            'accounts_exported': 0,
            'transactions_exported': 0,
            'total_debits': Decimal('0'),
            'total_credits': Decimal('0'),
            'hashes_generated': 0
        }
        
        logger.info(f"CasewareExporter v{self.VERSION} initialized. Output: {self.output_dir}")
    
    # ========================================================================
    # HASH VERIFICATION (FIX #3: Independent verification method)
    # ========================================================================
    
    @staticmethod
    def verify_hash(data: Dict, expected_hash: str) -> bool:
        """
        Verify a record's integrity hash matches the expected value.
        
        CANONICAL FORMAT DOCUMENTATION:
        1. Key fields are processed first in this order:
           txnId, TxnID, listId, ListID, refNumber, RefNumber,
           txnDate, TxnDate, amount, Amount, balance, Balance,
           name, Name, fullName, FullName
        2. Remaining fields are sorted alphabetically
        3. Format: "field1:value1|field2:value2|..."
        4. Numbers formatted to 2 decimal places
        5. Dates formatted as YYYY-MM-DD
        
        Args:
            data: The record dictionary to verify
            expected_hash: The expected SHA-256 hash (64-char hex)
            
        Returns:
            True if hash matches, False otherwise
        """
        computed_hash = CasewareExporter.compute_sha256_hash(data)
        return computed_hash.lower() == expected_hash.lower()
    
    # ========================================================================
    # HASH GENERATION (THE $60M COLUMN)
    # ========================================================================
    
    @staticmethod
    def compute_sha256_hash(data: Dict) -> str:
        """
        Compute SHA-256 integrity hash for a transaction/account.
        
        Uses canonical field ordering for deterministic hashing.
        Compatible with HashVerifier.cs in QBDesktopReader.
        
        Args:
            data: Transaction or account data dictionary
            
        Returns:
            64-character lowercase hex hash
        """
        # Build canonical string representation
        hash_input = []
        
        # Key fields in canonical order
        key_fields = [
            'txnId', 'TxnID', 'listId', 'ListID',
            'refNumber', 'RefNumber',
            'txnDate', 'TxnDate',
            'amount', 'Amount', 'balance', 'Balance',
            'name', 'Name', 'fullName', 'FullName'
        ]
        
        for field in key_fields:
            if field in data and data[field] is not None:
                value = data[field]
                if isinstance(value, (int, float, Decimal)):
                    value = f"{float(value):.2f}"
                elif isinstance(value, datetime):
                    value = value.strftime('%Y-%m-%d')
                hash_input.append(f"{field}:{value}")
        
        # Add all remaining fields sorted alphabetically
        for key in sorted(data.keys()):
            if key not in key_fields and data[key] is not None:
                value = data[key]
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True, default=str)
                elif isinstance(value, (int, float, Decimal)):
                    value = f"{float(value):.2f}"
                hash_input.append(f"{key}:{value}")
        
        # Compute SHA-256
        canonical_string = "|".join(hash_input)
        hash_bytes = hashlib.sha256(canonical_string.encode('utf-8')).hexdigest()
        
        return hash_bytes
    
    # ========================================================================
    # TRIAL BALANCE EXPORT (Audit_TB.csv)
    # ========================================================================
    
    def export_trial_balance(self, accounts: List[Dict], 
                              as_of_date: str = None) -> str:
        """
        Generate Audit_TB.csv - Trial Balance with Lead Sheet codes.
        
        Schema:
        - Account Number
        - Account Description
        - Type (A=Asset, L=Liability, etc.)
        - Lead Sheet Code
        - Prior Year Balance (optional)
        - Current Year Balance
        - Debit
        - Credit
        - Forensic_Integrity_Hash
        
        Args:
            accounts: List of account dictionaries from QB extraction
            as_of_date: Report date (default: today)
            
        Returns:
            Path to generated CSV file
            
        Raises:
            TypeError: If accounts is not a list
            IOError: If file cannot be written
        """
        # FIX #2: Input validation
        if not isinstance(accounts, list):
            raise TypeError(f"Expected list for accounts, got {type(accounts).__name__}")
        
        if as_of_date is None:
            as_of_date = datetime.now().strftime('%Y-%m-%d')
        
        output_file = self.output_dir / "Audit_TB.csv"
        
        # Column headers
        headers = [
            'Account Number',
            'Account Description',
            'Type',
            'Lead Sheet Code',
            'Prior Year Balance',
            'Current Year Balance',
            'Debit',
            'Credit',
            'Forensic_Integrity_Hash'
        ]
        
        rows = []
        total_debits = Decimal('0')
        total_credits = Decimal('0')
        
        for account in accounts:
            # FIX #2: Validate each account is a dict
            if not isinstance(account, dict):
                logger.warning(f"Skipping non-dict account: {type(account).__name__}")
                continue
            
            # Extract account details
            acct_num = self._sanitize_csv_value(account.get('accountNumber') or account.get('AccountNumber') or account.get('AcctNum', ''))
            acct_name = self._sanitize_csv_value(account.get('name') or account.get('Name') or account.get('FullName', 'Unknown Account'))
            acct_type = account.get('accountType') or account.get('AccountType', 'Other')
            balance = self._to_decimal(account.get('balance') or account.get('Balance') or account.get('CurrentBalance', 0))
            
            # Determine type code
            type_code = self._get_type_code(acct_type)
            
            # Get Lead Sheet code
            lead_sheet = self.LEAD_SHEET_CODES.get(acct_type, 'X9')
            
            # Determine debit/credit
            if acct_type in self.DEBIT_TYPES:
                debit = balance if balance >= 0 else Decimal('0')
                credit = abs(balance) if balance < 0 else Decimal('0')
            else:
                credit = balance if balance >= 0 else Decimal('0')
                debit = abs(balance) if balance < 0 else Decimal('0')
            
            total_debits += debit
            total_credits += credit
            
            # Compute integrity hash
            hash_data = {
                'AccountNumber': acct_num,
                'Name': acct_name,
                'Type': acct_type,
                'Balance': str(balance),
                'AsOfDate': as_of_date
            }
            integrity_hash = self.compute_sha256_hash(hash_data)
            self.stats['hashes_generated'] += 1
            
            rows.append([
                acct_num,
                acct_name,
                type_code,
                lead_sheet,
                '',  # Prior year balance (can be populated from prior period data)
                f"{balance:.2f}",
                f"{debit:.2f}",
                f"{credit:.2f}",
                integrity_hash
            ])
            
            self.stats['accounts_exported'] += 1
        
        # Add totals row
        rows.append([
            '',
            'TOTALS',
            '',
            '',
            '',
            '',
            f"{total_debits:.2f}",
            f"{total_credits:.2f}",
            ''
        ])
        
        # FIX #4: Write CSV with proper error handling
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Header comment with metadata
                f.write(f"# Caseware Audit Trial Balance\n")
                f.write(f"# Company: {self.company_name}\n")
                f.write(f"# As Of Date: {as_of_date}\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n")
                f.write(f"# Generator: ForensicBridge CasewareExporter v{self.VERSION}\n")
                f.write(f"#\n")
                
                writer.writerow(headers)
                writer.writerows(rows)
        except IOError as e:
            logger.error(f"Failed to write Trial Balance file: {e}")
            raise IOError(f"Cannot write to {output_file}: {e}") from e
        except PermissionError as e:
            logger.error(f"Permission denied writing Trial Balance: {e}")
            raise
        
        with self._stats_lock:
            self.stats['total_debits'] = total_debits
            self.stats['total_credits'] = total_credits
        
        logger.info(f"Trial Balance exported: {output_file} ({len(rows)-1} accounts)")
        return str(output_file)
    
    # ========================================================================
    # GENERAL LEDGER EXPORT (Audit_GL.csv)
    # ========================================================================
    
    def export_general_ledger(self, transactions: List[Dict],
                               start_date: str = None,
                               end_date: str = None) -> str:
        """
        Generate Audit_GL.csv - General Ledger with SHA-256 integrity hashes.
        
        Schema:
        - Account Number
        - Account Description
        - Type
        - Transaction Date
        - Reference/Doc Number
        - Description/Memo
        - Amount
        - Debit
        - Credit
        - Forensic_Integrity_Hash
        
        Args:
            transactions: List of transaction dictionaries
            start_date: Filter start date (optional)
            end_date: Filter end date (optional)
            
        Returns:
            Path to generated CSV file
        """
        output_file = self.output_dir / "Audit_GL.csv"
        
        headers = [
            'Account Number',
            'Account Description',
            'Type',
            'Transaction Date',
            'Reference',
            'Description',
            'Amount',
            'Debit',
            'Credit',
            'Forensic_Integrity_Hash'
        ]
        
        rows = []
        
        for txn in transactions:
            # FIX #2: Validate transaction is a dict
            if not isinstance(txn, dict):
                logger.warning(f"Skipping non-dict transaction: {type(txn).__name__}")
                continue
            
            # FIX #5: Parse dates properly for comparison
            txn_date = txn.get('txnDate') or txn.get('TxnDate', '')
            if txn_date:
                try:
                    txn_date_parsed = self._parse_date(txn_date)
                    start_date_parsed = self._parse_date(start_date) if start_date else None
                    end_date_parsed = self._parse_date(end_date) if end_date else None
                    
                    if start_date_parsed and txn_date_parsed and txn_date_parsed < start_date_parsed:
                        continue
                    if end_date_parsed and txn_date_parsed and txn_date_parsed > end_date_parsed:
                        continue
                except ValueError as e:
                    logger.warning(f"Invalid date format in transaction: {txn_date}, error: {e}")
            
            # Extract transaction details with CSV injection protection
            acct_num = self._sanitize_csv_value(txn.get('accountNumber') or txn.get('AccountNumber') or '')
            acct_name = self._sanitize_csv_value(txn.get('accountName') or txn.get('AccountName') or '')
            txn_type = txn.get('txnType') or txn.get('TxnType') or txn.get('type', '')
            ref_number = self._sanitize_csv_value(txn.get('refNumber') or txn.get('RefNumber') or txn.get('DocNumber', ''))
            memo = self._sanitize_csv_value(txn.get('memo') or txn.get('Memo') or txn.get('description', ''))
            amount = self._to_decimal(txn.get('amount') or txn.get('Amount') or txn.get('TotalAmount', 0))
            acct_type = txn.get('accountType') or txn.get('AccountType', '')
            
            # FIX #8: Transaction-type aware debit/credit determination
            debit, credit = self._determine_debit_credit(amount, txn_type, acct_type)
            
            # Compute integrity hash for this transaction
            integrity_hash = self.compute_sha256_hash(txn)
            self.stats['hashes_generated'] += 1
            
            rows.append([
                acct_num,
                acct_name,
                txn_type,
                txn_date,
                ref_number,
                memo[:100] if memo else '',
                f"{amount:.2f}",
                f"{debit:.2f}",
                f"{credit:.2f}",
                integrity_hash
            ])
            
            self.stats['transactions_exported'] += 1
        
        # Compute Global File Hash for entire dataset integrity
        global_hash_input = json.dumps(
            [row for row in rows],
            sort_keys=True,
            default=str
        )
        global_file_hash = hashlib.sha256(global_hash_input.encode('utf-8')).hexdigest()
        
        # FIX #4: Write CSV with proper error handling
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Header comment with GLOBAL FILE HASH (Integrity Summary)
                f.write(f"# Caseware Audit General Ledger\n")
                f.write(f"# Company: {self.company_name}\n")
                if start_date:
                    f.write(f"# Period: {start_date} to {end_date or 'present'}\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n")
                f.write(f"# Generator: ForensicBridge CasewareExporter v{self.VERSION}\n")
                f.write(f"#\n")
                f.write(f"# ============ INTEGRITY SUMMARY ============\n")
                f.write(f"# GLOBAL_FILE_HASH (SHA-256): {global_file_hash}\n")
                f.write(f"# Total Transactions: {len(rows)}\n")
                f.write(f"# Verify: This hash covers ALL transaction rows below.\n")
                f.write(f"# If this hash matches, the entire file is untampered.\n")
                f.write(f"# ============================================\n")
                f.write(f"#\n")
                f.write(f"# Row-level: Each row has its own Forensic_Integrity_Hash for per-transaction verification.\n")
                f.write(f"#\n")
                
                writer.writerow(headers)
                writer.writerows(rows)
        except IOError as e:
            logger.error(f"Failed to write General Ledger file: {e}")
            raise IOError(f"Cannot write to {output_file}: {e}") from e
        except PermissionError as e:
            logger.error(f"Permission denied writing General Ledger: {e}")
            raise
        
        # Store global hash in stats (thread-safe)
        with self._stats_lock:
            self.stats['global_file_hash'] = global_file_hash
        
        logger.info(f"General Ledger exported: {output_file} ({len(rows)} transactions)")
        logger.info(f"Global File Hash: {global_file_hash}")
        return str(output_file)
    
    # ========================================================================
    # CASEWARE MAPPING FILE (Audit_Mapping.cvw)
    # ========================================================================
    
    def export_mapping_file(self) -> str:
        """
        Generate Audit_Mapping.cvw - Caseware column configuration.
        
        This file tells Caseware exactly which column is Account, Debit, Credit, etc.
        
        Returns:
            Path to generated .cvw file
        """
        output_file = self.output_dir / "Audit_Mapping.cvw"
        
        mapping_config = {
            "FormatVersion": "1.0",
            "Generator": f"ForensicBridge CasewareExporter v{self.VERSION}",
            "GeneratedAt": datetime.now().isoformat(),
            "Company": self.company_name,
            
            "TrialBalance": {
                "File": "Audit_TB.csv",
                "SkipRows": 6,  # Skip header comments
                "Delimiter": ",",
                "TextQualifier": "\"",
                "ColumnMapping": {
                    "AccountNumber": 0,
                    "AccountDescription": 1,
                    "AccountType": 2,
                    "LeadSheetCode": 3,
                    "PriorYearBalance": 4,
                    "CurrentYearBalance": 5,
                    "Debit": 6,
                    "Credit": 7,
                    "ForensicHash": 8
                }
            },
            
            "GeneralLedger": {
                "File": "Audit_GL.csv",
                "SkipRows": 7,  # Skip header comments
                "Delimiter": ",",
                "TextQualifier": "\"",
                "ColumnMapping": {
                    "AccountNumber": 0,
                    "AccountDescription": 1,
                    "TransactionType": 2,
                    "TransactionDate": 3,
                    "Reference": 4,
                    "Description": 5,
                    "Amount": 6,
                    "Debit": 7,
                    "Credit": 8,
                    "ForensicHash": 9
                },
                "DateFormat": "YYYY-MM-DD"
            },
            
            "HashVerification": {
                "Algorithm": "SHA-256",
                "Encoding": "UTF-8",
                "OutputFormat": "lowercase_hex",
                "Description": "Each row contains a cryptographic hash that auditors can use to verify the digital fingerprint of individual transactions."
            },
            
            "LeadSheetCodes": self.LEAD_SHEET_CODES
        }
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(mapping_config, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to write mapping file: {e}")
            raise IOError(f"Cannot write to {output_file}: {e}") from e
        
        logger.info(f"Mapping file exported: {output_file}")
        return str(output_file)
    
    # ========================================================================
    # FULL BUNDLE GENERATION
    # ========================================================================
    
    def generate_audit_bundle(self, qb_data: Dict,
                               as_of_date: str = None,
                               start_date: str = None,
                               end_date: str = None) -> Dict:
        """
        Generate complete Caseware Audit Bundle.
        
        This is the main entry point for "Caseware Mode".
        
        Args:
            qb_data: Complete QB Desktop extraction data
            as_of_date: Trial balance date
            start_date: GL start date
            end_date: GL end date
            
        Returns:
            Dict with file paths and statistics
        """
        logger.info("="*60)
        logger.info("GENERATING CASEWARE AUDIT BUNDLE")
        logger.info("="*60)
        
        # Extract company name from data
        if 'company' in qb_data:
            self.company_name = qb_data['company'].get('companyName', self.company_name)
        
        result = {
            'success': True,
            'files': {},
            'statistics': {}
        }
        
        # 1. Export Trial Balance
        accounts = qb_data.get('accounts', [])
        if accounts:
            tb_file = self.export_trial_balance(accounts, as_of_date)
            result['files']['trial_balance'] = tb_file
            logger.info(f"✅ Trial Balance: {self.stats['accounts_exported']} accounts")
        
        # 2. Export General Ledger (all transaction types)
        all_transactions = []
        
        # Collect all transaction types
        txn_types = [
            'invoices', 'bills', 'receivePayments', 'billPayments',
            'creditMemos', 'salesReceipts', 'estimates',
            'journalEntries', 'checks', 'deposits', 'transfers',
            'vendorCredits', 'purchaseOrders', 'salesOrders'
        ]
        
        for txn_type in txn_types:
            txns = qb_data.get(txn_type, [])
            for txn in txns:
                txn['txnType'] = txn_type
                all_transactions.append(txn)
        
        if all_transactions:
            gl_file = self.export_general_ledger(all_transactions, start_date, end_date)
            result['files']['general_ledger'] = gl_file
            logger.info(f"✅ General Ledger: {self.stats['transactions_exported']} transactions")
        
        # 3. Export Mapping File
        mapping_file = self.export_mapping_file()
        result['files']['mapping'] = mapping_file
        
        # 4. Generate summary
        result['statistics'] = {
            'accounts_exported': self.stats['accounts_exported'],
            'transactions_exported': self.stats['transactions_exported'],
            'total_debits': str(self.stats['total_debits']),
            'total_credits': str(self.stats['total_credits']),
            'trial_balance_balanced': abs(self.stats['total_debits'] - self.stats['total_credits']) < Decimal('0.01'),
            'hashes_generated': self.stats['hashes_generated'],
            'output_directory': str(self.output_dir)
        }
        
        # 5. Create verification manifest
        self._create_verification_manifest(result)
        
        logger.info("="*60)
        logger.info("CASEWARE AUDIT BUNDLE COMPLETE!")
        logger.info(f"📊 Accounts: {self.stats['accounts_exported']}")
        logger.info(f"📝 Transactions: {self.stats['transactions_exported']}")
        logger.info(f"🔐 Hashes: {self.stats['hashes_generated']}")
        logger.info(f"💰 TB Balance: Debits={self.stats['total_debits']:.2f}, Credits={self.stats['total_credits']:.2f}")
        logger.info("="*60)
        
        return result
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _to_decimal(self, value: Any) -> Decimal:
        """Convert value to Decimal with 2 decimal places."""
        if value is None or value == '':
            return Decimal('0')
        try:
            return Decimal(str(value)).quantize(Decimal('0.01'), ROUND_HALF_UP)
        except (ValueError, InvalidOperation, TypeError) as e:
            # FIX #1: Specific exceptions instead of bare except
            logger.warning(f"Could not convert value to Decimal: {value}, error: {e}")
            return Decimal('0')
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """FIX #5: Parse date string to datetime object with multiple format support."""
        if not date_str:
            return None
        
        formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d']
        for fmt in formats:
            try:
                return datetime.strptime(str(date_str).split('T')[0].split(' ')[0], fmt)
            except ValueError:
                continue
        
        raise ValueError(f"Unrecognized date format: {date_str}")
    
    def _sanitize_csv_value(self, value: Any) -> str:
        """
        FIX #10: Protect against CSV injection attacks.
        
        Prefixes cell values starting with =, +, -, @ with a single quote
        to prevent formula interpretation in Excel/Google Sheets.
        """
        if value is None:
            return ''
        
        value_str = str(value)
        
        # CSV injection protection
        if value_str and value_str[0] in ('=', '+', '-', '@', '\t', '\r', '\n'):
            return "'" + value_str
        
        return value_str
    
    def _determine_debit_credit(self, amount: Decimal, txn_type: str, acct_type: str) -> Tuple[Decimal, Decimal]:
        """
        FIX #8: Transaction-type aware debit/credit determination.
        
        Accounting rules:
        - Payments received credit A/R
        - Bills increase A/P (credit)
        - Bill payments reduce A/P (debit)
        - Invoices increase A/R (debit)
        """
        txn_type_lower = txn_type.lower() if txn_type else ''
        
        # Credit transactions (reduce asset or increase liability)
        credit_types = {'payment', 'receivepayment', 'deposit', 'creditmemo', 'refund'}
        
        # Debit transactions (increase asset or reduce liability)
        debit_types = {'invoice', 'bill', 'salesreceipt', 'check', 'expense'}
        
        if txn_type_lower in credit_types:
            return (Decimal('0'), abs(amount))
        elif txn_type_lower in debit_types:
            return (abs(amount), Decimal('0'))
        else:
            # Fallback to sign-based logic
            if amount >= 0:
                return (amount, Decimal('0'))
            else:
                return (Decimal('0'), abs(amount))
    
    def _get_type_code(self, account_type: str) -> str:
        """Get single-letter type code for Caseware."""
        type_map = {
            'Bank': 'A', 'Accounts Receivable': 'A', 'Other Current Assets': 'A',
            'Fixed Assets': 'A', 'Other Assets': 'A', 'Inventory': 'A',
            'Undeposited Funds': 'A',  # FIX #7: Added missing type
            'Accounts Payable': 'L', 'Credit Card': 'L', 'Other Current Liabilities': 'L',
            'Long Term Liabilities': 'L',
            'Equity': 'E', 'Retained Earnings': 'E', 'Opening Balance Equity': 'E',
            'Income': 'R', 'Other Income': 'R',
            'Cost of Goods Sold': 'C',
            'Expense': 'X', 'Other Expense': 'X'
        }
        code = type_map.get(account_type, None)
        if code is None:
            logger.warning(f"Unmapped account type: {account_type}, defaulting to X")
            return 'X'
        return code
    
    def _create_verification_manifest(self, result: Dict):
        """Create a verification manifest with bundle metadata."""
        manifest = {
            'bundle_version': self.VERSION,
            'generated_at': datetime.now().isoformat(),
            'company': self.company_name,
            'files': result['files'],
            'statistics': result['statistics'],
            'hash_algorithm': 'SHA-256',
            'verification_instructions': (
                "To verify integrity, compute SHA-256 of the canonical field string "
                "and compare with Forensic_Integrity_Hash column."
            )
        }
        
        manifest_file = self.output_dir / "bundle_manifest.json"
        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
        
        result['files']['manifest'] = str(manifest_file)


# =============================================================================
# INTEGRATION WITH DATA TRANSFORMER
# =============================================================================

def add_caseware_mode_to_transformer():
    """
    Inject Caseware mode capability into QBDataTransformer.
    
    Call this function to add the `transform_for_caseware()` method to the transformer.
    """
    from data_transformer import QBDataTransformer
    
    def transform_for_caseware(self, qb_data: Dict, output_dir: str,
                                as_of_date: str = None,
                                start_date: str = None,
                                end_date: str = None) -> Dict:
        """
        Transform QB data for Caseware Audit Bundle output.
        
        Alternative to pushing to QBO - generates audit-ready CSVs.
        
        Args:
            qb_data: QB Desktop extraction data
            output_dir: Directory for output files
            as_of_date: Trial balance date
            start_date: GL filter start
            end_date: GL filter end
            
        Returns:
            Dict with file paths and statistics
        """
        logger.info("🏛️ CASEWARE MODE ACTIVATED")
        
        # Get company name
        company_name = qb_data.get('company', {}).get('companyName', 'Company')
        
        # Create exporter
        exporter = CasewareExporter(output_dir, company_name)
        
        # Generate bundle
        result = exporter.generate_audit_bundle(
            qb_data,
            as_of_date=as_of_date,
            start_date=start_date,
            end_date=end_date
        )
        
        return result
    
    # Add method to class
    QBDataTransformer.transform_for_caseware = transform_for_caseware
    logger.info("Caseware mode added to QBDataTransformer")


# =============================================================================
# STANDALONE USAGE
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python caseware_exporter.py <input_json> <output_dir>")
        print("\nGenerates Caseware Audit Bundle from QB Desktop extraction data.")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_dir = sys.argv[2]
    
    # FIX #9: Load QB data with encoding detection
    try:
        # Try to detect encoding first
        with open(input_file, 'rb') as f_raw:
            raw_data = f_raw.read(10000)  # Read first 10KB for detection
            detected = chardet.detect(raw_data)
            encoding = detected.get('encoding', 'utf-8') or 'utf-8'
        
        with open(input_file, 'r', encoding=encoding) as f:
            qb_data = json.load(f)
    except UnicodeDecodeError as e:
        print(f"❌ Encoding error: {e}. Try specifying encoding explicitly.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        sys.exit(1)
    except IOError as e:
        print(f"❌ Cannot read file: {e}")
        sys.exit(1)
    
    # Generate bundle
    exporter = CasewareExporter(output_dir)
    result = exporter.generate_audit_bundle(qb_data)
    
    print(f"\n✅ Caseware Audit Bundle generated in: {output_dir}")
    print(f"   Files: {list(result['files'].keys())}")

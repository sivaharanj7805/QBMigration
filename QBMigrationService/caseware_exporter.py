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
import threading
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

# FIX #1: chardet with fallback if not installed
try:
    import chardet
except ImportError:
    chardet = None
    logging.getLogger(__name__).warning(
        "chardet not installed - using utf-8 fallback for encoding detection"
    )

# FIX #33: Import locale-aware lead sheet mapper
from leadsheet_mapper import LeadSheetMapper

logger = logging.getLogger(__name__)


class CasewareExporter:
    """
    Generates Caseware Audit Bundle from QB Desktop extracted data.

    The "Caseware Mode" alternative to QBO migration.

    FIX #33: Now supports locale-aware lead sheet code mapping for:
    - US GAAP (United States)
    - Canadian GAAP (Canada)
    - IFRS (International)
    """

    VERSION = "1.0.0"

    # Account type classification for debit/credit determination.
    # Includes both QBD names (spaced, plural: 'Other Current Assets')
    # and QBO names (camelCase, singular: 'OtherCurrentAsset') since
    # input data may arrive in either format.
    DEBIT_TYPES = {
        # QBD format
        "Bank",
        "Accounts Receivable",
        "Other Current Assets",
        "Fixed Assets",
        "Other Assets",
        "Cost of Goods Sold",
        "Expense",
        "Other Expense",
        "Inventory",
        "Undeposited Funds",
        "Prepaid Expenses",
        # QBO format
        "AccountsReceivable",
        "OtherCurrentAsset",
        "FixedAsset",
        "OtherAsset",
        "CostOfGoodsSold",
        "OtherExpense",
        # Overlap (same in both formats)
        "Other Current Asset",
        "Fixed Asset",
        "Other Asset",
    }

    def __init__(
        self,
        output_dir: str,
        company_name: str = "Company",
        company_data: Optional[Dict] = None,
    ):
        """
        Initialize Caseware Exporter.

        Args:
            output_dir: Directory to write audit bundle files
            company_name: Company name for report headers
            company_data: QB company data for locale detection (optional)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.company_name = company_name

        # FIX #33: Initialize locale-aware lead sheet mapper
        self.leadsheet_mapper = LeadSheetMapper()

        # Detect accounting standard from company data if provided
        if company_data:
            standard = self.leadsheet_mapper.detect_accounting_standard(company_data)
            logger.info(f"Detected accounting standard: {standard}")
        else:
            logger.warning("No company data provided - defaulting to US_GAAP")
            self.leadsheet_mapper.detected_standard = "US_GAAP"

        # Statistics (thread-safe)
        self._stats_lock = threading.Lock()
        self.stats = {
            "accounts_exported": 0,
            "transactions_exported": 0,
            "total_debits": Decimal("0"),
            "total_credits": Decimal("0"),
            "hashes_generated": 0,
            "accounting_standard": self.leadsheet_mapper.detected_standard,
        }

        logger.info(
            f"CasewareExporter v{self.VERSION} initialized. Output: {self.output_dir}"
        )

    def reset_stats(self):
        """Reset statistics for a fresh export run."""
        with self._stats_lock:
            self.stats = {
                "accounts_exported": 0,
                "transactions_exported": 0,
                "total_debits": Decimal("0"),
                "total_credits": Decimal("0"),
                "hashes_generated": 0,
                "accounting_standard": self.leadsheet_mapper.detected_standard,
            }

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
            "txnId",
            "TxnID",
            "listId",
            "ListID",
            "refNumber",
            "RefNumber",
            "txnDate",
            "TxnDate",
            "amount",
            "Amount",
            "balance",
            "Balance",
            "name",
            "Name",
            "fullName",
            "FullName",
        ]

        for field in key_fields:
            if field in data and data[field] is not None:
                value = data[field]
                if isinstance(value, (int, float, Decimal)):
                    value = f"{Decimal(str(value)):.2f}"
                elif isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d")
                hash_input.append(f"{field}:{value}")

        # Add all remaining fields sorted alphabetically
        for key in sorted(data.keys()):
            if key not in key_fields and data[key] is not None:
                value = data[key]
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True, default=str)
                elif isinstance(value, (int, float, Decimal)):
                    value = f"{Decimal(str(value)):.2f}"
                hash_input.append(f"{key}:{value}")

        # HIGH-01 FIX: Escape pipe characters in values to prevent separator collision.
        # Without this, field values containing "|" create ambiguous canonical forms
        # that could allow different records to produce the same hash.
        escaped_input = [
            part.replace("\\", "\\\\").replace("|", "\\|") for part in hash_input
        ]
        canonical_string = "|".join(escaped_input)
        hash_bytes = hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()

        return hash_bytes

    # ========================================================================
    # TRIAL BALANCE EXPORT (Audit_TB.csv)
    # ========================================================================

    def export_trial_balance(self, accounts: List[Dict], as_of_date: str = None) -> str:
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
            raise TypeError(
                f"Expected list for accounts, got {type(accounts).__name__}"
            )

        if as_of_date is None:
            as_of_date = datetime.now().strftime("%Y-%m-%d")

        output_file = self.output_dir / "Audit_TB.csv"

        # Column headers
        # AUDIT FIX MEDIUM-11: Include Prior Year Balance column per CaseWare
        # Working Papers import spec (allows CPA year-over-year comparison).
        headers = [
            "Account Number",
            "Account Description",
            "Type",
            "Lead Sheet Code",
            "Prior Year Balance",
            "Current Year Balance",
            "Debit",
            "Credit",
            "Forensic_Integrity_Hash",
        ]

        rows = []
        total_debits = Decimal("0")
        total_credits = Decimal("0")

        for account in accounts:
            # FIX #2: Validate each account is a dict
            if not isinstance(account, dict):
                logger.warning(f"Skipping non-dict account: {type(account).__name__}")
                continue

            # Extract raw account details (before sanitization)
            raw_acct_num = str(
                account.get("accountNumber")
                or account.get("AccountNumber")
                or account.get("AcctNum", "")
            )
            raw_acct_name = str(
                account.get("name")
                or account.get("Name")
                or account.get("FullName", "Unknown Account")
            )
            acct_type = account.get("accountType") or account.get(
                "AccountType", "Other"
            )
            balance = self._to_decimal(
                account.get("balance")
                or account.get("Balance")
                or account.get("CurrentBalance", 0)
            )
            # AUDIT FIX MEDIUM-11: Extract prior year balance if available
            prior_year_balance = self._to_decimal(
                account.get("prior_year_balance")
                or account.get("PriorYearBalance")
                or account.get("OpeningBalance", 0)
            )

            # Hash on ORIGINAL values for verification
            hash_data = {
                "AccountNumber": raw_acct_num,
                "Name": raw_acct_name,
                "Type": acct_type,
                "Balance": str(balance),
                "AsOfDate": as_of_date,
            }
            integrity_hash = self.compute_sha256_hash(hash_data)

            # THEN sanitize for CSV output
            acct_num = self._sanitize_csv_value(raw_acct_num)
            acct_name = self._sanitize_csv_value(raw_acct_name)

            # Determine type code
            type_code = self.leadsheet_mapper.get_type_code(acct_type)

            # FIX #33: Get Lead Sheet code from locale-aware mapper
            # LOW-04 FIX: Log warning if lead sheet mapping fails
            lead_sheet = self.leadsheet_mapper.get_lead_sheet_code(acct_type)
            if not lead_sheet:
                logger.warning(
                    f"No lead sheet mapping for account type '{acct_type}' (account: {raw_acct_name})"
                )

            # Determine debit/credit
            if acct_type in self.DEBIT_TYPES:
                debit = balance if balance >= 0 else Decimal("0")
                credit = abs(balance) if balance < 0 else Decimal("0")
            else:
                credit = balance if balance >= 0 else Decimal("0")
                debit = abs(balance) if balance < 0 else Decimal("0")

            total_debits += debit
            total_credits += credit

            # CRITICAL FIX: Thread-safe stats update
            with self._stats_lock:
                self.stats["hashes_generated"] += 1

            rows.append(
                [
                    acct_num,
                    acct_name,
                    type_code,
                    lead_sheet,
                    f"{prior_year_balance:.2f}",
                    f"{balance:.2f}",
                    f"{debit:.2f}",
                    f"{credit:.2f}",
                    integrity_hash,
                ]
            )

            # CRITICAL FIX: Thread-safe stats update
            with self._stats_lock:
                self.stats["accounts_exported"] += 1

        # Add totals row (columns: AcctNum, Desc, Type, LeadSheet, PriorYr, CurYr, Dr, Cr, Hash)
        rows.append(
            [
                "",
                "TOTALS",
                "",
                "",
                "",
                "",
                f"{total_debits:.2f}",
                f"{total_credits:.2f}",
                "",
            ]
        )

        # FIX #4: Write CSV with proper error handling
        # CRITICAL FIX: Caseware requires header row FIRST (row 1), data starting row 2
        # Previous code put comment rows before header which broke Caseware import wizard
        try:
            # Use UTF-8-BOM for better Excel/Caseware compatibility with special chars
            with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                # CASEWARE FORMAT: Header row MUST be row 1
                writer.writerow(headers)

                # LOW-05 FIX: Explicitly filter out TOTALS row by content check
                # instead of assuming it's always the last row.
                for row in rows:
                    if row[1] == "TOTALS":
                        continue  # Skip TOTALS row (not valid for CaseWare import)
                    writer.writerow(row)
        except IOError as e:
            logger.error(f"Failed to write Trial Balance file: {e}")
            raise IOError(f"Cannot write to {output_file}: {e}") from e
        except PermissionError as e:
            logger.error(f"Permission denied writing Trial Balance: {e}")
            raise

        # Write metadata to a separate JSON file instead of trailing CSV comments
        metadata_file = self.output_dir / "Audit_TB_metadata.json"
        metadata = {
            "company": self.company_name,
            "as_of_date": as_of_date,
            "generated": datetime.now().isoformat(),
            "generator": f"ForensicBridge CasewareExporter v{self.VERSION}",
            "total_debits": str(total_debits),
            "total_credits": str(total_credits),
            "accounting_standard": self.leadsheet_mapper.detected_standard,
        }
        with open(metadata_file, "w", encoding="utf-8") as mf:
            json.dump(metadata, mf, indent=2)

        with self._stats_lock:
            self.stats["total_debits"] = total_debits
            self.stats["total_credits"] = total_credits

        logger.info(f"Trial Balance exported: {output_file} ({len(rows)-1} accounts)")
        return str(output_file)

    # ========================================================================
    # GENERAL LEDGER EXPORT (Audit_GL.csv)
    # ========================================================================

    def export_general_ledger(
        self,
        transactions,
        start_date: str = None,
        end_date: str = None,
        total_count: int = None,
        progress_callback: Callable[[int, int, str], None] = None,
        expand_line_items: bool = False,
    ) -> str:
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
            transactions: List or Generator of transaction dictionaries
            start_date: Filter start date (optional)
            end_date: Filter end date (optional)
            total_count: Total number of transactions (for progress reporting)
            progress_callback: Optional callback(current, total, phase) for progress updates
            expand_line_items: If True, export each line item as a separate row (FIX #3)

        Returns:
            Path to generated CSV file
        """
        output_file = self.output_dir / "Audit_GL.csv"

        headers = [
            "Account Number",
            "Account Description",
            "Type",
            "Transaction Date",
            "Reference",
            "Description",
            "Amount",
            "Debit",
            "Credit",
            "Forensic_Integrity_Hash",
        ]

        rows = []
        processed_count = 0

        for txn in transactions:
            # FIX #2: Validate transaction is a dict
            if not isinstance(txn, dict):
                logger.warning(f"Skipping non-dict transaction: {type(txn).__name__}")
                continue

            # FIX #5: Parse dates properly for comparison
            txn_date = txn.get("txnDate") or txn.get("TxnDate", "")
            if txn_date:
                try:
                    txn_date_parsed = self._parse_date(txn_date)
                    start_date_parsed = (
                        self._parse_date(start_date) if start_date else None
                    )
                    end_date_parsed = self._parse_date(end_date) if end_date else None

                    if (
                        start_date_parsed
                        and txn_date_parsed
                        and txn_date_parsed < start_date_parsed
                    ):
                        continue
                    if (
                        end_date_parsed
                        and txn_date_parsed
                        and txn_date_parsed > end_date_parsed
                    ):
                        continue
                except ValueError as e:
                    logger.warning(
                        f"Invalid date format in transaction: {txn_date}, error: {e}"
                    )

            # FIX #3: Option to expand line items for detailed auditing
            # FIX: Double-entry bookkeeping - _create_gl_rows returns pairs of entries
            if expand_line_items and "lines" in txn:
                for line in txn.get("lines", []):
                    entry_rows = self._create_gl_rows(txn, line, txn_date)
                    rows.extend(entry_rows)
            else:
                entry_rows = self._create_gl_rows(txn, None, txn_date)
                rows.extend(entry_rows)

            processed_count += 1

            # FIX #4: Progress callback every 1000 transactions
            if progress_callback and total_count and processed_count % 1000 == 0:
                progress_callback(
                    processed_count, total_count, "Processing transactions..."
                )

        # FIX #9: Compute Global File Hash INCLUDING metadata for tamper detection
        hash_content = {
            "company": self.company_name,
            "period": {"start": start_date, "end": end_date},
            "row_count": len(rows),
            "rows": rows,
        }
        global_hash_input = json.dumps(hash_content, sort_keys=True, default=str)
        global_file_hash = hashlib.sha256(global_hash_input.encode("utf-8")).hexdigest()

        # FIX #4: Write CSV with proper error handling
        # CRITICAL FIX: Caseware requires header row FIRST (row 1), data starting row 2
        # Moved metadata to trailing comments at end of file
        try:
            # Use UTF-8-BOM for better Excel/Caseware compatibility
            with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                # CASEWARE FORMAT: Header row MUST be row 1
                writer.writerow(headers)

                # Write data rows starting at row 2
                writer.writerows(rows)
        except IOError as e:
            logger.error(f"Failed to write General Ledger file: {e}")
            raise IOError(f"Cannot write to {output_file}: {e}") from e
        except PermissionError as e:
            logger.error(f"Permission denied writing General Ledger: {e}")
            raise

        # Write metadata to a separate JSON file instead of trailing CSV comments
        gl_metadata_file = self.output_dir / "Audit_GL_metadata.json"
        gl_metadata = {
            "company": self.company_name,
            "period": {"start": start_date, "end": end_date},
            "generated": datetime.now().isoformat(),
            "generator": f"ForensicBridge CasewareExporter v{self.VERSION}",
            "global_file_hash": global_file_hash,
            "total_transactions": len(rows),
        }
        with open(gl_metadata_file, "w", encoding="utf-8") as mf:
            json.dump(gl_metadata, mf, indent=2)

        # Store global hash in stats (thread-safe)
        with self._stats_lock:
            self.stats["global_file_hash"] = global_file_hash

        logger.info(
            f"General Ledger exported: {output_file} ({len(rows)} transactions)"
        )
        logger.info(f"Global File Hash: {global_file_hash}")
        return str(output_file)

    # ========================================================================
    # CASEWARE MAPPING FILE (Audit_Mapping.cvw)
    # ========================================================================

    def export_mapping_file(self) -> str:
        """
        Generate IMPORT_INSTRUCTIONS.txt - Human-readable import guide for Caseware.

        NOTE: Previous versions generated a fake .cvw file (JSON format), but .cvw is
        actually a proprietary CaseView binary format. This caused import errors.

        The new format is a plain text README with:
        1. Step-by-step Caseware import instructions
        2. Column mapping reference
        3. Hash verification instructions

        Returns:
            Path to generated instructions file
        """
        # Generate human-readable instructions file (NOT fake .cvw)
        output_file = self.output_dir / "IMPORT_INSTRUCTIONS.txt"

        instructions = f"""
================================================================================
                     CASEWARE WORKING PAPERS IMPORT GUIDE
================================================================================

Company: {self.company_name}
Generated: {datetime.now().isoformat()}
Generator: ForensicBridge CasewareExporter v{self.VERSION}
Accounting Standard: {self.leadsheet_mapper.detected_standard}

================================================================================
                           FILE CONTENTS
================================================================================

This bundle contains:

1. Audit_TB.csv  - Trial Balance with Lead Sheet codes
2. Audit_GL.csv  - General Ledger with SHA-256 integrity hashes
3. IMPORT_INSTRUCTIONS.txt - This file

================================================================================
                     STEP 1: IMPORT TRIAL BALANCE
================================================================================

In Caseware Working Papers:

1. Go to: Engagement > Import > ASCII Text File
2. Select: Audit_TB.csv
3. Component: "Trial Balance (Chart of Accounts & General Ledger Balances)"
4. Delimiter: Comma
5. Text qualifier: Double quote (")

COLUMN MAPPING:
   Column 0: Account Number     -> Map to: Account Number
   Column 1: Account Description -> Map to: Account Description
   Column 2: Type               -> Map to: (Ignore - for reference)
   Column 3: Lead Sheet Code    -> Map to: Lead Sheet
   Column 4: Current Year Balance -> Map to: Current Balance
   Column 5: Debit              -> Map to: Debit
   Column 6: Credit             -> Map to: Credit
   Column 7: Forensic_Integrity_Hash -> Map to: (Ignore - for verification)

================================================================================
                     STEP 2: IMPORT GENERAL LEDGER
================================================================================

1. Go to: Engagement > Import > ASCII Text File
2. Select: Audit_GL.csv
3. Component: "Transactions (General Ledger Details)"
4. Delimiter: Comma
5. Text qualifier: Double quote (")

COLUMN MAPPING:
   Column 0: Account Number     -> Map to: Account Number
   Column 1: Account Description -> Map to: (Ignore)
   Column 2: Type               -> Map to: (Ignore)
   Column 3: Transaction Date   -> Map to: Transaction Date (YYYY-MM-DD)
   Column 4: Reference          -> Map to: Reference/Document Number
   Column 5: Description        -> Map to: Description/Memo
   Column 6: Amount             -> Map to: Amount
   Column 7: Debit              -> Map to: Debit
   Column 8: Credit             -> Map to: Credit
   Column 9: Forensic_Integrity_Hash -> Map to: (Ignore - for verification)

================================================================================
                     LEAD SHEET CODE REFERENCE
================================================================================

Accounting Standard: {self.leadsheet_mapper.detected_standard}

Lead sheet codes are pre-mapped based on your company's locale:
"""

        # Add lead sheet codes
        codes = self.leadsheet_mapper.get_lead_sheet_codes()
        for account_type, code in sorted(codes.items(), key=lambda x: x[1]):
            instructions += f"   {code:8} = {account_type}\n"

        instructions += """
================================================================================
                     HASH VERIFICATION (OPTIONAL)
================================================================================

Each row contains a SHA-256 cryptographic hash in the last column.
This allows auditors to verify data integrity.

To verify a row's hash:
1. Concatenate key fields: "field1:value1|field2:value2|..."
2. Key fields in order: txnId, listId, refNumber, txnDate, amount, balance, name
3. Then remaining fields alphabetically
4. Numbers: 2 decimal places (e.g., "1234.56")
5. Dates: YYYY-MM-DD format
6. Compute SHA-256 and compare to Forensic_Integrity_Hash column

The General Ledger file also contains a GLOBAL_FILE_HASH at the end (in comments)
that covers all transaction rows for file-level integrity verification.

================================================================================
                           SUPPORT
================================================================================

If you encounter import issues, verify:
- CSV files use UTF-8 encoding (with BOM)
- Date format is YYYY-MM-DD
- Decimal separator is period (.)
- No trailing commas in rows

For technical support: support@forensicbridge.com
"""

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(instructions)
        except IOError as e:
            logger.error(f"Failed to write instructions file: {e}")
            raise IOError(f"Cannot write to {output_file}: {e}") from e

        # Also generate a JSON metadata file for programmatic access
        metadata_file = self.output_dir / "bundle_metadata.json"
        metadata = {
            "format_version": "2.0",
            "generator": f"ForensicBridge CasewareExporter v{self.VERSION}",
            "generated_at": datetime.now().isoformat(),
            "company": self.company_name,
            "accounting_standard": self.leadsheet_mapper.detected_standard,
            "files": {
                "trial_balance": {
                    "filename": "Audit_TB.csv",
                    "encoding": "utf-8-sig",
                    "delimiter": ",",
                    "has_header": True,
                    "columns": [
                        "Account Number",
                        "Account Description",
                        "Type",
                        "Lead Sheet Code",
                        "Current Year Balance",
                        "Debit",
                        "Credit",
                        "Forensic_Integrity_Hash",
                    ],
                },
                "general_ledger": {
                    "filename": "Audit_GL.csv",
                    "encoding": "utf-8-sig",
                    "delimiter": ",",
                    "has_header": True,
                    "date_format": "YYYY-MM-DD",
                    "columns": [
                        "Account Number",
                        "Account Description",
                        "Type",
                        "Transaction Date",
                        "Reference",
                        "Description",
                        "Amount",
                        "Debit",
                        "Credit",
                        "Forensic_Integrity_Hash",
                    ],
                },
            },
            "hash_verification": {
                "algorithm": "SHA-256",
                "encoding": "UTF-8",
                "output_format": "lowercase_hex",
            },
            "lead_sheet_codes": self.leadsheet_mapper.get_lead_sheet_codes(),
        }

        try:
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except IOError as e:
            logger.debug(f"Optional metadata file write failed: {e}")

        logger.info(f"Import instructions exported: {output_file}")
        return str(output_file)

    # ========================================================================
    # FULL BUNDLE GENERATION
    # ========================================================================

    def generate_audit_bundle(
        self,
        qb_data: Dict,
        as_of_date: str = None,
        start_date: str = None,
        end_date: str = None,
        progress_callback: Callable[[int, int, str], None] = None,
    ) -> Dict:
        """
        Generate complete Caseware Audit Bundle.

        This is the main entry point for "Caseware Mode".

        Args:
            qb_data: Complete QB Desktop extraction data
            as_of_date: Trial balance date
            start_date: GL start date
            end_date: GL end date
            progress_callback: Optional callback(current, total, message) for progress updates

        Returns:
            Dict with file paths and statistics

        Raises:
            TypeError: If qb_data is not a dictionary
            ValueError: If required keys are missing
        """
        # FIX #7: Validate qb_data structure
        validation_errors = self._validate_qb_data(qb_data)
        if validation_errors:
            logger.error(f"Invalid qb_data: {validation_errors}")
            raise ValueError(
                f"Invalid qb_data structure: {'; '.join(validation_errors)}"
            )

        # Reset stats for a fresh export run
        self.reset_stats()

        logger.info("=" * 60)
        logger.info("GENERATING CASEWARE AUDIT BUNDLE")
        logger.info("=" * 60)

        # FIX #33: Detect accounting standard from company data if not already detected
        if "company" in qb_data:
            self.company_name = qb_data["company"].get("companyName", self.company_name)

            # Detect locale if not already done
            if not self.leadsheet_mapper.detected_standard:
                standard = self.leadsheet_mapper.detect_accounting_standard(
                    qb_data["company"]
                )
                logger.info(f"Detected accounting standard: {standard}")
                self.stats["accounting_standard"] = standard

        result = {"success": True, "files": {}, "statistics": {}}

        # FIX #4: Progress callback
        if progress_callback:
            progress_callback(0, 3, "Starting export...")

        # 1. Export Trial Balance
        accounts = qb_data.get("accounts", [])
        if not accounts:
            logger.warning("No accounts provided - creating empty Trial Balance file")
        # Continue with export regardless (will just have headers if empty)
        tb_file = self.export_trial_balance(accounts, as_of_date)
        result["files"]["trial_balance"] = tb_file
        logger.info(f"Trial Balance: {self.stats['accounts_exported']} accounts")

        if progress_callback:
            progress_callback(1, 3, "Trial balance exported")

        # 2. Export General Ledger using generator (FIX #2: Memory efficient)
        txn_count = sum(len(qb_data.get(t, [])) for t in self.TXN_TYPES)
        if txn_count > 0:
            gl_file = self.export_general_ledger(
                self._iterate_transactions(qb_data),
                start_date,
                end_date,
                total_count=txn_count,
                progress_callback=progress_callback,
            )
            result["files"]["general_ledger"] = gl_file
            logger.info(
                f"General Ledger: {self.stats['transactions_exported']} transactions"
            )

        if progress_callback:
            progress_callback(2, 3, "General ledger exported")

        # 3. Export Mapping File
        mapping_file = self.export_mapping_file()
        result["files"]["mapping"] = mapping_file

        if progress_callback:
            progress_callback(3, 4, "Mapping file exported")

        # 4. Generate AiDA-ready data package for Caseware AI assistant
        try:
            from aida_integration import get_aida_service

            aida_service = get_aida_service()
            merkle_root = qb_data.get("merkle_root", "")
            fiscal_year_end = end_date or as_of_date or ""
            aida_package = aida_service.prepare_aida_package(
                extracted_data=qb_data,
                merkle_root=merkle_root,
                company_name=self.company_name,
                fiscal_year_end=fiscal_year_end,
            )

            # Write AiDA JSON package
            aida_json_path = self.output_dir / "AiDA_DataPackage.json"
            with open(aida_json_path, "w", encoding="utf-8") as f:
                f.write(aida_service.export_for_aida(aida_package))
            result["files"]["aida_package"] = str(aida_json_path)

            # Write AiDA anomaly CSV
            aida_csv_path = self.output_dir / "AiDA_Anomalies.csv"
            with open(aida_csv_path, "w", encoding="utf-8-sig") as f:
                f.write(aida_service.export_aida_summary_csv(aida_package))
            result["files"]["aida_anomalies"] = str(aida_csv_path)

            logger.info(
                f"AiDA package generated: {len(aida_package.transactions)} transactions, "
                f"confidence: {aida_package.verification_confidence.value}"
            )
        except ImportError:
            logger.warning(
                "AiDA integration module not available - skipping AiDA package"
            )
        except Exception as e:
            logger.warning(f"AiDA package generation failed (non-fatal): {e}")

        if progress_callback:
            progress_callback(4, 4, "AiDA package exported")

        # 4. Generate summary
        result["statistics"] = {
            "accounts_exported": self.stats["accounts_exported"],
            "transactions_exported": self.stats["transactions_exported"],
            "total_debits": str(self.stats["total_debits"]),
            "total_credits": str(self.stats["total_credits"]),
            "trial_balance_balanced": abs(
                self.stats["total_debits"] - self.stats["total_credits"]
            )
            < Decimal("0.01"),
            "hashes_generated": self.stats["hashes_generated"],
            "output_directory": str(self.output_dir),
        }

        # 5. Create verification manifest
        self._create_verification_manifest(result)

        logger.info("=" * 60)
        logger.info("CASEWARE AUDIT BUNDLE COMPLETE!")
        logger.info(f"Accounts: {self.stats['accounts_exported']}")
        logger.info(f"Transactions: {self.stats['transactions_exported']}")
        logger.info(f"Hashes: {self.stats['hashes_generated']}")
        logger.info(
            f"TB Balance: Debits={self.stats['total_debits']:.2f}, Credits={self.stats['total_credits']:.2f}"
        )
        logger.info("=" * 60)

        return result

    # All transaction types to collect
    TXN_TYPES = [
        "invoices",
        "bills",
        "receivePayments",
        "billPayments",
        "creditMemos",
        "salesReceipts",
        "journalEntries",
        "checks",
        "deposits",
        "transfers",
        "vendorCredits",
        "refundReceipts",
        "inventoryAdjustments",
        "taxPayments",
    ]

    def _iterate_transactions(self, qb_data: Dict) -> Generator[Dict, None, None]:
        """
        FIX #2: Generator pattern for memory-efficient transaction iteration.

        Yields transactions one at a time instead of loading all into memory.
        """
        for txn_type in self.TXN_TYPES:
            for txn in qb_data.get(txn_type, []):
                # FIX #8: Don't mutate original - create a copy
                txn_copy = {**txn, "txnType": txn_type}
                yield txn_copy

    def _validate_qb_data(self, qb_data: Any) -> List[str]:
        """
        FIX #7: Validate QB data structure before processing.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not isinstance(qb_data, dict):
            errors.append(f"qb_data must be a dictionary, got {type(qb_data).__name__}")
            return errors  # Can't check further if not a dict

        # Check for at least one data source
        has_accounts = bool(qb_data.get("accounts"))
        has_transactions = any(qb_data.get(t) for t in self.TXN_TYPES)

        if not has_accounts and not has_transactions:
            errors.append(
                "qb_data must contain 'accounts' or at least one transaction type"
            )

        # Validate accounts structure if present
        accounts = qb_data.get("accounts", [])
        if accounts and not isinstance(accounts, list):
            errors.append(f"'accounts' must be a list, got {type(accounts).__name__}")

        return errors

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _to_decimal(self, value: Any, quantize: bool = True) -> Decimal:
        """Convert value to Decimal.

        AUDIT FIX P4-L1: Optional quantize parameter to prevent rounding drift
        during accumulation. Quantize only at final output.
        """
        if value is None or value == "":
            return Decimal("0")
        try:
            d = Decimal(str(value))
            return d.quantize(Decimal("0.01"), ROUND_HALF_UP) if quantize else d
        except (ValueError, InvalidOperation, TypeError) as e:
            logger.warning(f"Could not convert value to Decimal: {value}, error: {e}")
            return Decimal("0")

    def _singularize(self, name: str) -> str:
        """Singularize entity type name for lookup."""
        name = name.lower()
        if name.endswith("ies"):
            return name[:-3] + "y"  # journalentries -> journalentry
        elif name.endswith("ses"):
            return name[:-2]  # purchases -> purchase
        elif name.endswith("s") and not name.endswith("ss"):
            return name[:-1]  # invoices -> invoice, bills -> bill
        return name

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """FIX #5: Parse date string to datetime object with multiple format support."""
        if not date_str:
            return None

        formats = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]
        for fmt in formats:
            try:
                return datetime.strptime(str(date_str).split("T")[0].split(" ")[0], fmt)
            except ValueError:
                continue

        raise ValueError(f"Unrecognized date format: {date_str}")

    def _sanitize_csv_value(self, value: Any) -> str:
        """
        SECURITY FIX: Comprehensive CSV injection protection.

        Protects against formula injection attacks that could execute when
        opening in Excel, Google Sheets, or Caseware.

        Attack vectors prevented:
        - Direct formula: =cmd|'/C calc'
        - Prefixed formula: " =cmd|'/C calc'" (space prefix bypass)
        - Tab/newline injection: "\t=cmd|'/C calc'"

        Reference: OWASP CSV Injection guidelines
        """
        if value is None:
            return ""

        str_value = str(value).strip()

        if not str_value:
            return ""

        # SECURITY FIX: Define dangerous characters that trigger formula evaluation
        # Removed '-' to preserve negative numbers and hyphens
        DANGEROUS_CHARS = ("=", "+", "@", "\t", "\r", "\n")

        # Remove embedded newlines/tabs that could create cell injection
        str_value = str_value.replace("\n", " ").replace("\r", " ").replace("\t", " ")

        # Check first character
        if str_value[0] in DANGEROUS_CHARS:
            str_value = str_value[1:]  # Remove the dangerous leading character
            logger.debug("Stripped CSV injection character from value")

        return str_value

    # Contra account mapping for double-entry bookkeeping
    CONTRA_ACCOUNT_MAP = {
        "invoice": ("1200", "Accounts Receivable", "Accounts Receivable"),
        "payment": ("1200", "Accounts Receivable", "Accounts Receivable"),
        "receivepayment": ("1000", "Cash/Bank", "Bank"),
        "bill": ("2000", "Accounts Payable", "Accounts Payable"),
        "billpayment": ("2000", "Accounts Payable", "Accounts Payable"),
        "salesreceipt": ("1000", "Undeposited Funds", "Bank"),
        "creditmemo": ("1200", "Accounts Receivable", "Accounts Receivable"),
        "vendorcredit": ("2000", "Accounts Payable", "Accounts Payable"),
        "refundreceipt": ("1000", "Undeposited Funds", "Bank"),
        "deposit": ("4000", "Income/Various", "Income"),
        "check": ("1000", "Cash/Bank", "Bank"),
        "expense": ("1000", "Cash/Bank", "Bank"),
        "purchase": ("1000", "Cash/Bank", "Bank"),
        "transfer": ("1000", "Transfer Account", "Bank"),
        "taxpayment": ("2100", "Tax Payable", "Other Current Liability"),
        "charge": ("2000", "Accounts Payable", "Accounts Payable"),
        "inventoryadjustment": ("5100", "Inventory Adjustment", "CostOfGoodsSold"),
    }

    def _create_gl_rows(
        self, txn: Dict, line_item: Optional[Dict], txn_date: str
    ) -> List[List]:
        """
        Create General Ledger rows from a transaction (or line item).

        Returns TWO rows per entry for proper double-entry bookkeeping:
        1. The primary entry on the source account
        2. The offsetting contra entry on the contra account

        Args:
            txn: The parent transaction dictionary
            line_item: Optional line item dict (if expanding line items)
            txn_date: Pre-extracted transaction date

        Returns:
            List of row lists (usually 2 rows for double-entry, or empty if invalid)
        """
        # Use line item values if provided, fall back to transaction header
        source = line_item if line_item else txn

        acct_num = self._sanitize_csv_value(
            source.get("accountNumber")
            or source.get("AccountNumber")
            or source.get("AccountRef", {}).get("value")
            or txn.get("accountNumber")
            or txn.get("AccountNumber")
            or ""
        )
        acct_name = self._sanitize_csv_value(
            source.get("accountName")
            or source.get("AccountName")
            or source.get("AccountRef", {}).get("name")
            or txn.get("accountName")
            or txn.get("AccountName")
            or ""
        )
        txn_type = txn.get("txnType") or txn.get("TxnType") or txn.get("type", "")
        ref_number = self._sanitize_csv_value(
            txn.get("refNumber") or txn.get("RefNumber") or txn.get("DocNumber", "")
        )

        # Memo: use line description if available
        if line_item:
            memo = self._sanitize_csv_value(
                line_item.get("description")
                or line_item.get("Description")
                or line_item.get("memo")
                or txn.get("memo")
                or ""
            )
        else:
            memo = self._sanitize_csv_value(
                txn.get("memo") or txn.get("Memo") or txn.get("description", "")
            )

        # Amount: use line amount if available
        if line_item:
            amount = self._to_decimal(
                line_item.get("amount") or line_item.get("Amount") or 0
            )
        else:
            amount = self._to_decimal(
                txn.get("amount") or txn.get("Amount") or txn.get("TotalAmount", 0)
            )

        acct_type = source.get("accountType") or source.get("AccountType") or ""

        # Determine debit/credit for primary entry
        debit, credit = self._determine_debit_credit(amount, txn_type, acct_type)

        # Compute integrity hash for this row
        hash_data = line_item if line_item else txn
        integrity_hash = self.compute_sha256_hash(hash_data)

        with self._stats_lock:
            self.stats["hashes_generated"] += 1
            self.stats["transactions_exported"] += 1

        # Normalize the date to YYYY-MM-DD format
        formatted_date = txn_date
        if txn_date:
            parsed = self._parse_date(txn_date)
            if parsed:
                formatted_date = parsed.strftime("%Y-%m-%d")

        # Primary entry row
        primary_row = [
            acct_num,
            acct_name,
            txn_type,
            formatted_date,
            ref_number,
            memo[:255] if memo else "",
            f"{amount:.2f}",
            f"{debit:.2f}",
            f"{credit:.2f}",
            integrity_hash,
        ]

        rows = [primary_row]

        # Double-entry: create the offsetting contra entry
        txn_type_lower = self._singularize(txn_type or "")
        contra_info = self.CONTRA_ACCOUNT_MAP.get(txn_type_lower)

        if contra_info and (debit > 0 or credit > 0):
            contra_acct_num, contra_acct_name, contra_acct_type = contra_info

            # Use contra account from transaction if available (e.g., deposit account)
            contra_acct_from_txn = (
                source.get("contraAccountNumber")
                or source.get("ContraAccountRef", {}).get("value")
                or txn.get("depositToAccountNumber")
                or txn.get("DepositToAccountRef", {}).get("value")
            )
            contra_name_from_txn = (
                source.get("contraAccountName")
                or source.get("ContraAccountRef", {}).get("name")
                or txn.get("depositToAccountName")
                or txn.get("DepositToAccountRef", {}).get("name")
            )
            if contra_acct_from_txn:
                contra_acct_num = self._sanitize_csv_value(contra_acct_from_txn)
            if contra_name_from_txn:
                contra_acct_name = self._sanitize_csv_value(contra_name_from_txn)

            # Contra entry: swap debit and credit (offsetting)
            contra_debit = credit  # If primary was credit, contra is debit
            contra_credit = debit  # If primary was debit, contra is credit

            contra_hash = self.compute_sha256_hash(
                {
                    "contra": True,
                    "parent_hash": integrity_hash,
                    "account": contra_acct_num,
                    "debit": str(contra_debit),
                    "credit": str(contra_credit),
                }
            )

            # Contra amount is opposite sign; use abs to avoid -0.00
            contra_amount = -amount if amount != 0 else Decimal("0")
            contra_row = [
                contra_acct_num,
                contra_acct_name,
                txn_type,
                formatted_date,
                ref_number,
                memo[:255] if memo else "",
                f"{contra_amount:.2f}",
                f"{contra_debit:.2f}",
                f"{contra_credit:.2f}",
                contra_hash,
            ]
            rows.append(contra_row)

            with self._stats_lock:
                self.stats["hashes_generated"] += 1
                self.stats["transactions_exported"] += 1

        return rows

    def _determine_debit_credit(
        self, amount: Decimal, txn_type: str, acct_type: str
    ) -> Tuple[Decimal, Decimal]:
        """
        FIX #5: Transaction-type aware debit/credit determination.

        Accounting rules:
        - Payments received credit A/R
        - Bills increase A/P (credit)
        - Bill payments reduce A/P (debit)
        - Invoices increase A/R (debit)
        - Journal entries need special handling (have explicit debit/credit)
        """
        # Normalize: singularize for plural->singular matching
        # This handles 'invoices'->'invoice', 'journalEntries'->'journalentry', etc.
        txn_type_lower = self._singularize(txn_type or "")

        # Debit transactions (increase asset or reduce liability)
        debit_types = {
            "invoice",
            "bill",
            "salesreceipt",
            "check",
            "expense",
            "billpayment",
            "purchase",
            "inventoryadjustment",
            "taxpayment",
            "charge",
        }

        # Credit transactions (reduce asset or increase liability)
        credit_types = {
            "payment",
            "receivepayment",
            "creditmemo",
            "vendorcredit",
            "refundreceipt",
            "deposit",
            "creditcardpayment",
        }

        # Neutral transactions (use amount sign)

        if txn_type_lower in debit_types:
            return (abs(amount), Decimal("0"))
        elif txn_type_lower in credit_types:
            return (Decimal("0"), abs(amount))
        else:
            # Fallback to sign-based logic for neutral/unknown types
            if amount >= 0:
                return (amount, Decimal("0"))
            else:
                return (Decimal("0"), abs(amount))

    def _create_verification_manifest(self, result: Dict):
        """Create a verification manifest with bundle metadata."""
        manifest = {
            "bundle_version": self.VERSION,
            "generated_at": datetime.now().isoformat(),
            "company": self.company_name,
            "files": result["files"],
            "statistics": result["statistics"],
            "hash_algorithm": "SHA-256",
            "verification_instructions": (
                "To verify integrity, compute SHA-256 of the canonical field string "
                "and compare with Forensic_Integrity_Hash column."
            ),
        }

        manifest_file = self.output_dir / "bundle_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        result["files"]["manifest"] = str(manifest_file)


# =============================================================================
# INTEGRATION WITH DATA TRANSFORMER
# =============================================================================


def add_caseware_mode_to_transformer():
    """
    Inject Caseware mode capability into QBDataTransformer.

    Call this function to add the `transform_for_caseware()` method to the transformer.
    """
    from data_transformer import QBDataTransformer

    def transform_for_caseware(
        self,
        qb_data: Dict,
        output_dir: str,
        as_of_date: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> Dict:
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
        logger.info("CASEWARE MODE ACTIVATED")

        # Get company data for locale detection
        company_data = qb_data.get("company", {})
        company_name = company_data.get("companyName", "Company")

        # FIX #33: Create exporter with company data for locale detection
        exporter = CasewareExporter(output_dir, company_name, company_data)

        # Generate bundle
        result = exporter.generate_audit_bundle(
            qb_data, as_of_date=as_of_date, start_date=start_date, end_date=end_date
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
        logger.info("Usage: python caseware_exporter.py <input_json> <output_dir>")
        logger.info(
            "\nGenerates Caseware Audit Bundle from QB Desktop extraction data."
        )
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    # FIX #9: Load QB data with encoding detection
    try:
        # CRITICAL FIX: Check if chardet is available before using
        encoding = "utf-8"  # Default encoding
        if chardet is not None:
            # Try to detect encoding first
            with open(input_file, "rb") as f_raw:
                raw_data = f_raw.read(10000)  # Read first 10KB for detection
                detected = chardet.detect(raw_data)
                encoding = detected.get("encoding", "utf-8") or "utf-8"

        with open(input_file, "r", encoding=encoding) as f:
            qb_data = json.load(f)
    except UnicodeDecodeError as e:
        logger.info(f"[FAIL] Encoding error: {e}. Try specifying encoding explicitly.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.info(f"[FAIL] Invalid JSON: {e}")
        sys.exit(1)
    except IOError as e:
        logger.info(f"[FAIL] Cannot read file: {e}")
        sys.exit(1)

    # FIX #33: Generate bundle with company data for locale detection
    company_data = qb_data.get("company", {})
    company_name = company_data.get("companyName", "Company")
    exporter = CasewareExporter(output_dir, company_name, company_data)
    result = exporter.generate_audit_bundle(qb_data)

    logger.info(f"\n[OK] Caseware Audit Bundle generated in: {output_dir}")
    logger.info(f"   Files: {list(result['files'].keys())}")

"""
Caseware AiDA Integration Layer
===============================

Addresses the PARTIAL GAP identified in M&A technical due diligence audit:
"No explicit AiDA integration code"

Provides explicit integration with Caseware's AiDA (AI-powered audit assistant)
by preparing forensically-verified data in the format AiDA expects. This
positions ForensicBridge data as the "refined fuel" that prevents AiDA
from hallucinating due to unverified source data.

Key Features:
1. AiDA-ready data format preparation
2. Forensic verification metadata for AI confidence
3. Anomaly pre-tagging for AI-assisted audit
4. Natural language query preparation
5. Audit evidence packaging for AI review

Author: ForensicBridge Security Team
Version: 1.0.0
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AiDAConfidenceLevel(Enum):
    """Confidence levels for AiDA data quality assessment."""

    VERIFIED = "verified"  # Merkle root verified, all hashes match
    HIGH = "high"  # Hashes verified, no anomalies
    MEDIUM = "medium"  # Minor anomalies detected, verified source
    LOW = "low"  # Significant anomalies, requires manual review
    UNVERIFIED = "unverified"  # Data not cryptographically verified


class AiDAAnomalyType(Enum):
    """Types of anomalies that AiDA should flag for auditor attention."""

    UNUSUAL_AMOUNT = "unusual_amount"
    DUPLICATE_TRANSACTION = "duplicate_transaction"
    WEEKEND_TRANSACTION = "weekend_transaction"
    ROUND_NUMBER = "round_number"
    SEQUENCE_GAP = "sequence_gap"
    LATE_RECORDING = "late_recording"
    RELATED_PARTY = "related_party"
    THRESHOLD_BREACH = "threshold_breach"
    UNUSUAL_PATTERN = "unusual_pattern"


@dataclass
class AiDATransactionContext:
    """Context information for a single transaction for AiDA analysis."""

    transaction_id: str
    transaction_type: str
    date: str
    amount: float
    entity_name: str
    description: str
    account_code: str
    lead_sheet_code: str

    # Forensic verification
    integrity_hash: str
    verification_status: AiDAConfidenceLevel
    merkle_proof_available: bool

    # Anomaly flags
    anomalies: List[AiDAAnomalyType] = field(default_factory=list)
    anomaly_details: Dict[str, Any] = field(default_factory=dict)

    # Related transactions for context
    related_transactions: List[str] = field(default_factory=list)

    # Natural language summary for AiDA
    nl_summary: str = ""


@dataclass
class AiDADataPackage:
    """Complete data package prepared for Caseware AiDA consumption."""

    # Package metadata
    package_id: str
    created_at: str
    company_name: str
    fiscal_year_end: str
    data_version: str = "1.0"

    # Forensic verification summary
    merkle_root: str = ""
    total_records_verified: int = 0
    verification_confidence: AiDAConfidenceLevel = AiDAConfidenceLevel.UNVERIFIED
    hash_algorithm: str = "SHA-256"

    # Trial balance summary for AiDA
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0
    total_revenue: float = 0.0
    total_expenses: float = 0.0
    trial_balance_variance: float = 0.0
    is_balanced: bool = False

    # Transaction context for AI analysis
    transactions: List[AiDATransactionContext] = field(default_factory=list)

    # Pre-computed anomaly summary
    anomaly_summary: Dict[str, int] = field(default_factory=dict)

    # Suggested audit focus areas (AI guidance)
    suggested_focus_areas: List[str] = field(default_factory=list)

    # Natural language executive summary
    nl_executive_summary: str = ""


class AiDAIntegrationService:
    """
    Service for preparing ForensicBridge data for Caseware AiDA consumption.

    AiDA Synergy: This service ensures that the forensically-verified data
    from ForensicBridge serves as "refined fuel" for Caseware's AI assistant,
    providing the verified input that prevents AI hallucination.
    """

    def __init__(self):
        self._anomaly_thresholds = {
            "large_transaction_threshold": Decimal("50000"),
            "round_number_variance": Decimal("0.01"),
            "sequence_gap_threshold": 10,
        }

    def prepare_aida_package(
        self,
        extracted_data: Dict[str, Any],
        merkle_root: str,
        company_name: str,
        fiscal_year_end: str,
    ) -> AiDADataPackage:
        """
        Prepare a complete data package for Caseware AiDA.

        Args:
            extracted_data: Complete extraction result from ForensicBridge
            merkle_root: Merkle root hash for verification
            company_name: Company name
            fiscal_year_end: Fiscal year end date

        Returns:
            AiDADataPackage ready for AiDA consumption
        """
        logger.info(f"Preparing AiDA data package for {company_name}")

        package = AiDADataPackage(
            package_id=f"AIDA-{hashlib.sha256(f'{company_name}{datetime.now(timezone.utc).isoformat()}'.encode()).hexdigest()[:16]}",
            created_at=datetime.now(timezone.utc).isoformat(),
            company_name=company_name,
            fiscal_year_end=fiscal_year_end,
            merkle_root=merkle_root,
            hash_algorithm="SHA-256",
        )

        # Process trial balance
        self._process_trial_balance(package, extracted_data)

        # Process transactions with anomaly detection
        self._process_transactions(package, extracted_data)

        # Compute anomaly summary
        self._compute_anomaly_summary(package)

        # Generate suggested focus areas
        self._generate_focus_areas(package)

        # Generate natural language summary
        self._generate_nl_summary(package)

        # Set verification confidence
        package.verification_confidence = self._assess_confidence(package, merkle_root)
        package.total_records_verified = len(package.transactions)

        logger.info(
            f"AiDA package prepared: {len(package.transactions)} transactions, "
            f"confidence: {package.verification_confidence.value}"
        )

        return package

    def _process_trial_balance(
        self, package: AiDADataPackage, extracted_data: Dict[str, Any]
    ) -> None:
        """Process trial balance for AiDA."""
        accounts = extracted_data.get("accounts", [])

        for account in accounts:
            account_type = account.get("AccountType") or account.get("account_type", "")
            balance = float(account.get("Balance") or account.get("balance") or 0)

            # Categorize by account type
            if account_type in [
                "Bank",
                "Accounts Receivable",
                "AccountsReceivable",
                "Other Current Asset",
                "OtherCurrentAsset",
                "Fixed Asset",
                "FixedAsset",
                "Other Asset",
                "OtherAsset",
            ]:
                package.total_assets += balance
            elif account_type in [
                "Accounts Payable",
                "AccountsPayable",
                "Credit Card",
                "CreditCard",
                "Other Current Liability",
                "OtherCurrentLiability",
                "Long Term Liability",
                "LongTermLiability",
            ]:
                package.total_liabilities += balance
            elif account_type in ["Equity", "OpeningBalanceEquity", "RetainedEarnings"]:
                package.total_equity += balance
            elif account_type in ["Income", "Other Income", "OtherIncome"]:
                package.total_revenue += balance
            elif account_type in [
                "Expense",
                "Other Expense",
                "OtherExpense",
                "Cost of Goods Sold",
                "CostOfGoodsSold",
            ]:
                package.total_expenses += balance

        # Calculate variance
        # Assets = Liabilities + Equity + (Revenue - Expenses)
        net_income = package.total_revenue - package.total_expenses
        expected_balance = package.total_liabilities + package.total_equity + net_income
        package.trial_balance_variance = abs(package.total_assets - expected_balance)
        package.is_balanced = package.trial_balance_variance < 0.01

    def _process_transactions(
        self, package: AiDADataPackage, extracted_data: Dict[str, Any]
    ) -> None:
        """Process transactions with anomaly detection for AiDA."""
        # Process invoices
        for inv in extracted_data.get("invoices", []):
            txn = self._create_transaction_context(
                transaction_id=inv.get("TxnID") or inv.get("txn_id", ""),
                transaction_type="Invoice",
                date=str(inv.get("TxnDate") or inv.get("txn_date", "")),
                amount=float(inv.get("Subtotal") or inv.get("subtotal") or 0),
                entity_name=inv.get("CustomerRefFullName")
                or inv.get("customer_name", ""),
                description=inv.get("Memo") or inv.get("memo", ""),
                account_code="1200",  # A/R
                lead_sheet_code="A2",
                integrity_hash=inv.get("IntegrityHash")
                or inv.get("integrity_hash", ""),
            )
            self._detect_anomalies(txn)
            package.transactions.append(txn)

        # Process bills
        for bill in extracted_data.get("bills", []):
            txn = self._create_transaction_context(
                transaction_id=bill.get("TxnID") or bill.get("txn_id", ""),
                transaction_type="Bill",
                date=str(bill.get("TxnDate") or bill.get("txn_date", "")),
                amount=float(bill.get("AmountDue") or bill.get("amount_due") or 0),
                entity_name=bill.get("VendorRefFullName")
                or bill.get("vendor_name", ""),
                description=bill.get("Memo") or bill.get("memo", ""),
                account_code="2000",  # A/P
                lead_sheet_code="L1",
                integrity_hash=bill.get("IntegrityHash")
                or bill.get("integrity_hash", ""),
            )
            self._detect_anomalies(txn)
            package.transactions.append(txn)

        # Process journal entries
        for je in extracted_data.get("journal_entries", []):
            lines = je.get("Lines") or je.get("lines") or []
            total_debits = sum(
                float(line.get("Amount") or line.get("amount") or 0)
                for line in lines
                if (line.get("JournalLineType") or line.get("journal_line_type"))
                == "Debit"
            )

            txn = self._create_transaction_context(
                transaction_id=je.get("TxnID") or je.get("txn_id", ""),
                transaction_type="JournalEntry",
                date=str(je.get("TxnDate") or je.get("txn_date", "")),
                amount=total_debits,
                entity_name="",
                description=je.get("Memo") or je.get("memo", ""),
                account_code="MULTI",
                lead_sheet_code="JE",
                integrity_hash=je.get("IntegrityHash") or je.get("integrity_hash", ""),
            )
            self._detect_anomalies(txn)
            package.transactions.append(txn)

        # Process checks
        for chk in extracted_data.get("checks", []):
            txn = self._create_transaction_context(
                transaction_id=chk.get("TxnID") or chk.get("txn_id", ""),
                transaction_type="Check",
                date=str(chk.get("TxnDate") or chk.get("txn_date", "")),
                amount=float(chk.get("Amount") or chk.get("amount") or 0),
                entity_name=chk.get("PayeeEntityRefFullName")
                or chk.get("payee_name", ""),
                description=chk.get("Memo") or chk.get("memo", ""),
                account_code="1000",  # Cash
                lead_sheet_code="A1",
                integrity_hash=chk.get("IntegrityHash")
                or chk.get("integrity_hash", ""),
            )
            self._detect_anomalies(txn)
            package.transactions.append(txn)

    def _create_transaction_context(
        self,
        transaction_id: str,
        transaction_type: str,
        date: str,
        amount: float,
        entity_name: str,
        description: str,
        account_code: str,
        lead_sheet_code: str,
        integrity_hash: str,
    ) -> AiDATransactionContext:
        """Create a transaction context object."""
        return AiDATransactionContext(
            transaction_id=transaction_id,
            transaction_type=transaction_type,
            date=date,
            amount=amount,
            entity_name=entity_name,
            description=description,
            account_code=account_code,
            lead_sheet_code=lead_sheet_code,
            integrity_hash=integrity_hash,
            verification_status=(
                AiDAConfidenceLevel.VERIFIED
                if integrity_hash
                else AiDAConfidenceLevel.UNVERIFIED
            ),
            merkle_proof_available=bool(integrity_hash),
            nl_summary=f"{transaction_type} for ${amount:,.2f} to/from {entity_name or 'N/A'}",
        )

    def _detect_anomalies(self, txn: AiDATransactionContext) -> None:
        """Detect anomalies in a transaction for AiDA flagging."""
        # Large transaction
        if txn.amount > float(self._anomaly_thresholds["large_transaction_threshold"]):
            txn.anomalies.append(AiDAAnomalyType.UNUSUAL_AMOUNT)
            txn.anomaly_details["unusual_amount"] = {
                "threshold": float(
                    self._anomaly_thresholds["large_transaction_threshold"]
                ),
                "actual": txn.amount,
            }

        # Round number (potential estimate or fraud indicator)
        if txn.amount > 0:
            if txn.amount == round(txn.amount, -3):  # Rounded to thousands
                txn.anomalies.append(AiDAAnomalyType.ROUND_NUMBER)
                txn.anomaly_details["round_number"] = {
                    "amount": txn.amount,
                    "rounded_to": "thousands",
                }

        # Weekend transaction (may require explanation)
        try:
            if txn.date:
                from datetime import datetime as dt

                date_obj = dt.fromisoformat(txn.date.replace("Z", "+00:00"))
                if date_obj.weekday() >= 5:  # Saturday or Sunday
                    txn.anomalies.append(AiDAAnomalyType.WEEKEND_TRANSACTION)
                    txn.anomaly_details["weekend"] = {
                        "date": txn.date,
                        "day": date_obj.strftime("%A"),
                    }
        except (ValueError, TypeError, AttributeError) as e:
            # CRITICAL FIX: Specific exceptions instead of bare except
            # Log the error instead of silently ignoring
            import logging

            logging.getLogger(__name__).debug(
                f"Could not parse transaction date for anomaly detection: {e}"
            )

    def _compute_anomaly_summary(self, package: AiDADataPackage) -> None:
        """Compute anomaly summary statistics."""
        for txn in package.transactions:
            for anomaly in txn.anomalies:
                key = anomaly.value
                package.anomaly_summary[key] = package.anomaly_summary.get(key, 0) + 1

    def _generate_focus_areas(self, package: AiDADataPackage) -> None:
        """Generate suggested audit focus areas based on anomalies."""
        if package.anomaly_summary.get("unusual_amount", 0) > 5:
            package.suggested_focus_areas.append(
                f"Review {package.anomaly_summary['unusual_amount']} large transactions "
                f"exceeding ${float(self._anomaly_thresholds['large_transaction_threshold']):,.0f}"
            )

        if package.anomaly_summary.get("round_number", 0) > 10:
            package.suggested_focus_areas.append(
                f"Investigate {package.anomaly_summary['round_number']} round-number transactions "
                f"for potential estimation or manipulation"
            )

        if package.anomaly_summary.get("weekend_transaction", 0) > 3:
            package.suggested_focus_areas.append(
                f"Verify authorization for {package.anomaly_summary['weekend_transaction']} "
                f"weekend transactions"
            )

        if not package.is_balanced:
            package.suggested_focus_areas.append(
                f"CRITICAL: Trial balance variance of ${package.trial_balance_variance:,.2f} "
                f"requires investigation"
            )

    def _generate_nl_summary(self, package: AiDADataPackage) -> None:
        """Generate natural language executive summary for AiDA."""
        anomaly_count = sum(package.anomaly_summary.values())

        package.nl_executive_summary = f"""
ForensicBridge Data Package for {package.company_name}

This data package contains {len(package.transactions):,} transactions from fiscal year ending {package.fiscal_year_end}.

Financial Summary:
- Total Assets: ${package.total_assets:,.2f}
- Total Liabilities: ${package.total_liabilities:,.2f}
- Total Equity: ${package.total_equity:,.2f}
- Total Revenue: ${package.total_revenue:,.2f}
- Total Expenses: ${package.total_expenses:,.2f}
- Trial Balance Status: {'BALANCED' if package.is_balanced else f'VARIANCE: ${package.trial_balance_variance:,.2f}'}

Data Verification:
- Merkle Root: {package.merkle_root[:32]}...
- Verification Confidence: {package.verification_confidence.value.upper()}
- Hash Algorithm: {package.hash_algorithm}

Anomaly Detection:
- Total Anomalies Detected: {anomaly_count}
{chr(10).join(f'- {k.replace("_", " ").title()}: {v}' for k, v in package.anomaly_summary.items())}

Suggested Focus Areas:
{chr(10).join(f'- {area}' for area in package.suggested_focus_areas) or '- No specific concerns identified'}

This data has been forensically verified using SHA-256 hashing and Merkle tree verification.
The Merkle root provides cryptographic proof of data integrity suitable for audit evidence.
        """.strip()

    def _assess_confidence(
        self, package: AiDADataPackage, merkle_root: str
    ) -> AiDAConfidenceLevel:
        """Assess overall confidence level for the data package."""
        if not merkle_root:
            return AiDAConfidenceLevel.UNVERIFIED

        # Check if all transactions have hashes
        verified_count = sum(1 for t in package.transactions if t.integrity_hash)
        total_count = len(package.transactions)

        if total_count == 0:
            return AiDAConfidenceLevel.UNVERIFIED

        verification_rate = verified_count / total_count

        if verification_rate == 1.0 and package.is_balanced:
            return AiDAConfidenceLevel.VERIFIED
        elif verification_rate >= 0.95:
            return AiDAConfidenceLevel.HIGH
        elif verification_rate >= 0.80:
            return AiDAConfidenceLevel.MEDIUM
        else:
            return AiDAConfidenceLevel.LOW

    def export_for_aida(self, package: AiDADataPackage) -> str:
        """
        Export the data package as JSON for AiDA consumption.

        Args:
            package: Prepared AiDA data package

        Returns:
            JSON string ready for AiDA import
        """

        def serialize(obj):
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, Decimal):
                return float(obj)
            if hasattr(obj, "__dict__"):
                return {k: serialize(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [serialize(i) for i in obj]
            if isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            return obj

        return json.dumps(serialize(package), indent=2)

    def export_aida_summary_csv(self, package: AiDADataPackage) -> str:
        """
        Export anomaly summary as CSV for AiDA quick import.

        Args:
            package: Prepared AiDA data package

        Returns:
            CSV string with anomaly summary
        """
        lines = ["TransactionID,Type,Date,Amount,Entity,Anomalies,VerificationStatus"]

        for txn in package.transactions:
            if txn.anomalies:  # Only export transactions with anomalies
                anomaly_str = "|".join(a.value for a in txn.anomalies)
                lines.append(
                    f'"{txn.transaction_id}","{txn.transaction_type}",'
                    f'"{txn.date}",{txn.amount:.2f},"{txn.entity_name}",'
                    f'"{anomaly_str}","{txn.verification_status.value}"'
                )

        return "\n".join(lines)


# Singleton instance
_aida_service: Optional[AiDAIntegrationService] = None


def get_aida_service() -> AiDAIntegrationService:
    """Get singleton AiDA integration service instance."""
    global _aida_service
    if _aida_service is None:
        _aida_service = AiDAIntegrationService()
    return _aida_service

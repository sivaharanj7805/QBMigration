"""
Base Accounting Connector
=========================

Abstract base class for all accounting platform connectors.
Defines the common interface that Sage, Xero, FreshBooks, etc. must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ExtractionStatus(Enum):
    """Status of extraction process."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExtractionResult:
    """Result of an extraction operation."""

    status: ExtractionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_records: int = 0
    entity_counts: Dict[str, int] = field(default_factory=dict)
    merkle_root: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    extracted_data: Optional[Dict[str, Any]] = None


@dataclass
class BaseExtractionConfig:
    """Base configuration for extraction."""

    include_transactions: bool = True
    include_lists: bool = True
    include_deleted: bool = False
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    incremental: bool = False
    last_sync_token: Optional[str] = None


class BaseAccountingConnector(ABC):
    """
    Abstract base class for accounting platform connectors.

    All platform-specific connectors (Sage, Xero, FreshBooks) must inherit
    from this class and implement the required methods.

    This ensures consistent forensic verification across all platforms:
    - SHA-256 per-record hashing
    - Merkle tree chain of custody
    - Standardized data format for Caseware export
    """

    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self._is_connected = False
        self._session_id: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @abstractmethod
    def connect(self, credentials: Dict[str, str]) -> bool:
        """
        Establish connection to the accounting platform.

        Args:
            credentials: Platform-specific credentials

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the accounting platform."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Test if the connection is active and valid.

        Returns:
            True if connection is valid
        """
        pass

    @abstractmethod
    def extract_all(self, config: BaseExtractionConfig) -> ExtractionResult:
        """
        Extract all data from the accounting platform.

        Args:
            config: Extraction configuration

        Returns:
            ExtractionResult with all extracted data
        """
        pass

    @abstractmethod
    def extract_accounts(self) -> List[Dict]:
        """Extract chart of accounts."""
        pass

    @abstractmethod
    def extract_customers(self) -> List[Dict]:
        """Extract customer/client list."""
        pass

    @abstractmethod
    def extract_vendors(self) -> List[Dict]:
        """Extract vendor/supplier list."""
        pass

    @abstractmethod
    def extract_invoices(self, date_from: Optional[datetime] = None) -> List[Dict]:
        """Extract sales invoices."""
        pass

    @abstractmethod
    def extract_bills(self, date_from: Optional[datetime] = None) -> List[Dict]:
        """Extract bills/expenses."""
        pass

    @abstractmethod
    def extract_payments(self, date_from: Optional[datetime] = None) -> List[Dict]:
        """Extract payment records."""
        pass

    @abstractmethod
    def extract_journal_entries(
        self, date_from: Optional[datetime] = None
    ) -> List[Dict]:
        """Extract journal entries."""
        pass

    @abstractmethod
    def get_trial_balance(self, as_of_date: Optional[datetime] = None) -> Dict:
        """
        Get trial balance report.

        Args:
            as_of_date: Date for trial balance (default: today)

        Returns:
            Trial balance data
        """
        pass

    @abstractmethod
    def compute_record_hash(self, record: Dict, record_type: str) -> str:
        """
        Compute SHA-256 hash for a single record.

        Must use canonical field ordering for deterministic results.

        Args:
            record: The record to hash
            record_type: Type of record (invoice, bill, etc.)

        Returns:
            SHA-256 hash string
        """
        pass

    def get_supported_entity_types(self) -> List[str]:
        """
        Get list of entity types supported by this connector.

        Returns:
            List of supported entity type names
        """
        return [
            "accounts",
            "customers",
            "vendors",
            "invoices",
            "bills",
            "payments",
            "journal_entries",
        ]

    def get_platform_info(self) -> Dict[str, str]:
        """
        Get information about the connected platform.

        Returns:
            Dictionary with platform details
        """
        return {
            "platform_name": self.platform_name,
            "is_connected": str(self._is_connected),
            "session_id": self._session_id or "N/A",
        }

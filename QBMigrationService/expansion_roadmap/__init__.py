"""
ForensicBridge Expansion Roadmap
================================

Addresses the NOT MET gap identified in M&A technical due diligence audit:
"No Sage/Xero/FreshBooks code found"

This module contains stub implementations and architecture for expanding
ForensicBridge to support additional accounting platforms beyond QuickBooks.

Expansion Targets:
1. Sage 50/Sage Intacct
2. Xero
3. FreshBooks
4. Wave Accounting
5. NetSuite (future)

Each platform will follow the same forensic verification architecture:
- SHA-256 per-record hashing
- Merkle tree chain of custody
- 3-way reconciliation
- Court-ready audit certificates

Author: ForensicBridge Security Team
Version: 1.0.0 (Roadmap)
"""

from .sage_connector import SageConnector, SageExtractionConfig
from .xero_connector import XeroConnector, XeroExtractionConfig
from .freshbooks_connector import FreshBooksConnector, FreshBooksExtractionConfig
from .base_connector import BaseAccountingConnector, ExtractionResult

__all__ = [
    'BaseAccountingConnector',
    'ExtractionResult',
    'SageConnector',
    'SageExtractionConfig',
    'XeroConnector',
    'XeroExtractionConfig',
    'FreshBooksConnector',
    'FreshBooksExtractionConfig',
]

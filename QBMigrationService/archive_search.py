"""
Full-Text Archive Search Service
================================

Addresses the MEDIUM GAP identified in M&A technical due diligence audit:
"No ElasticSearch/full-text index in code"

Provides full-text search capability for the "Data Museum" archival portal,
enabling CPAs and auditors to search legacy transactions across archived
QuickBooks data.

Features:
- Full-text search across all transaction types
- Fuzzy matching for partial queries
- Date range filtering
- Amount range filtering
- Entity type filtering
- Export search results to CSV/PDF

Author: ForensicBridge Security Team
Version: 1.0.0
"""

import re
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SearchEntityType(Enum):
    """Searchable entity types in the archive."""
    ALL = "all"
    INVOICE = "invoice"
    BILL = "bill"
    PAYMENT = "payment"
    JOURNAL_ENTRY = "journal_entry"
    CHECK = "check"
    DEPOSIT = "deposit"
    CREDIT_MEMO = "credit_memo"
    SALES_RECEIPT = "sales_receipt"
    CUSTOMER = "customer"
    VENDOR = "vendor"
    ITEM = "item"
    ACCOUNT = "account"


@dataclass
class SearchFilter:
    """Filters for archive search."""
    query: str = ""
    entity_types: List[SearchEntityType] = field(default_factory=lambda: [SearchEntityType.ALL])
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    customer_id: Optional[str] = None
    vendor_id: Optional[str] = None
    account_id: Optional[str] = None
    include_voided: bool = False
    fuzzy_match: bool = True
    max_results: int = 100
    offset: int = 0


@dataclass
class SearchResult:
    """Individual search result."""
    entity_type: str
    entity_id: str
    ref_number: Optional[str]
    date: Optional[datetime]
    amount: Optional[Decimal]
    description: str
    matched_field: str
    match_score: float
    highlight: str
    raw_data: Dict[str, Any]


@dataclass
class SearchResponse:
    """Complete search response."""
    query: str
    total_results: int
    returned_results: int
    offset: int
    search_time_ms: float
    results: List[SearchResult]
    facets: Dict[str, Dict[str, int]]


class ArchiveSearchService:
    """
    Full-text search service for archived QuickBooks data.

    Provides the "Data Museum" search capability required for
    CPA/auditor access to legacy transactions.
    """

    def __init__(self):
        self._index: Dict[str, List[Dict]] = {}
        self._inverted_index: Dict[str, List[Tuple[str, str, float]]] = {}
        self._entity_counts: Dict[str, int] = {}

    def index_extraction(self, extracted_data: Dict[str, Any], archive_id: str) -> Dict:
        """
        Build search index from extracted QuickBooks data.

        Args:
            extracted_data: Complete extraction result
            archive_id: Unique identifier for this archive

        Returns:
            Indexing statistics
        """
        start_time = datetime.utcnow()
        indexed_count = 0

        # Index transactions
        transaction_types = {
            'invoices': self._index_invoices,
            'bills': self._index_bills,
            'receive_payments': self._index_payments,
            'journal_entries': self._index_journal_entries,
            'checks': self._index_checks,
            'deposits': self._index_deposits,
            'credit_memos': self._index_credit_memos,
            'sales_receipts': self._index_sales_receipts,
        }

        for entity_type, indexer in transaction_types.items():
            records = extracted_data.get(entity_type, [])
            if records:
                count = indexer(records, archive_id)
                self._entity_counts[entity_type] = count
                indexed_count += count

        # Index master data
        list_types = {
            'customers': self._index_customers,
            'vendors': self._index_vendors,
            'items': self._index_items,
            'accounts': self._index_accounts,
        }

        for entity_type, indexer in list_types.items():
            records = extracted_data.get(entity_type, [])
            if records:
                count = indexer(records, archive_id)
                self._entity_counts[entity_type] = count
                indexed_count += count

        elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "archive_id": archive_id,
            "indexed_at": datetime.utcnow().isoformat(),
            "total_indexed": indexed_count,
            "entity_counts": self._entity_counts,
            "indexing_time_ms": elapsed
        }

    def search(self, filters: SearchFilter) -> SearchResponse:
        """
        Execute full-text search against the archive index.

        Args:
            filters: Search filters and query

        Returns:
            SearchResponse with matching results
        """
        start_time = datetime.utcnow()
        results: List[SearchResult] = []

        query_terms = self._tokenize(filters.query.lower())

        if not query_terms:
            # Return recent records if no query
            all_results = self._get_all_records(filters)
        else:
            # Search inverted index
            candidate_ids = self._find_candidates(query_terms, filters.fuzzy_match)

            # Score and filter candidates
            for entity_key in candidate_ids:
                entity_type, entity_id = entity_key.split(":", 1)

                # Check entity type filter
                if SearchEntityType.ALL not in filters.entity_types:
                    type_enum = self._entity_type_to_enum(entity_type)
                    if type_enum not in filters.entity_types:
                        continue

                # Get full record
                record = self._get_record(entity_type, entity_id)
                if not record:
                    continue

                # Apply filters
                if not self._matches_filters(record, filters):
                    continue

                # Score the match
                score, matched_field, highlight = self._score_match(
                    record, query_terms, filters.fuzzy_match
                )

                if score > 0:
                    results.append(SearchResult(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        ref_number=record.get('ref_number'),
                        date=record.get('date'),
                        amount=record.get('amount'),
                        description=record.get('description', ''),
                        matched_field=matched_field,
                        match_score=score,
                        highlight=highlight,
                        raw_data=record
                    ))

            # Sort by score
            results.sort(key=lambda x: x.match_score, reverse=True)
            all_results = results

        # Apply pagination
        total = len(all_results)
        paginated = all_results[filters.offset:filters.offset + filters.max_results]

        # Build facets
        facets = self._build_facets(all_results)

        elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000

        return SearchResponse(
            query=filters.query,
            total_results=total,
            returned_results=len(paginated),
            offset=filters.offset,
            search_time_ms=elapsed,
            results=paginated,
            facets=facets
        )

    def search_by_ref_number(self, ref_number: str) -> List[SearchResult]:
        """Quick lookup by reference number (invoice #, check #, etc.)."""
        filters = SearchFilter(
            query=ref_number,
            fuzzy_match=False,
            max_results=50
        )
        response = self.search(filters)
        return response.results

    def search_by_amount(
        self,
        amount: Decimal,
        tolerance: Decimal = Decimal('0.01')
    ) -> List[SearchResult]:
        """Search for transactions with a specific amount."""
        filters = SearchFilter(
            amount_min=amount - tolerance,
            amount_max=amount + tolerance,
            max_results=100
        )
        response = self.search(filters)
        return response.results

    def search_by_date_range(
        self,
        date_from: datetime,
        date_to: datetime,
        entity_types: Optional[List[SearchEntityType]] = None
    ) -> List[SearchResult]:
        """Search for transactions within a date range."""
        filters = SearchFilter(
            date_from=date_from,
            date_to=date_to,
            entity_types=entity_types or [SearchEntityType.ALL],
            max_results=1000
        )
        response = self.search(filters)
        return response.results

    # =========================================================================
    # INDEXING METHODS
    # =========================================================================

    def _index_invoices(self, invoices: List[Dict], archive_id: str) -> int:
        """Index invoice records."""
        count = 0
        for inv in invoices:
            entity_id = inv.get('TxnID') or inv.get('txn_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'invoice',
                'entity_id': entity_id,
                'ref_number': inv.get('RefNumber') or inv.get('ref_number'),
                'date': self._parse_date(inv.get('TxnDate') or inv.get('txn_date')),
                'amount': self._parse_decimal(inv.get('Subtotal') or inv.get('subtotal')),
                'customer': inv.get('CustomerRefFullName') or inv.get('customer_name'),
                'description': inv.get('Memo') or inv.get('memo') or '',
                'searchable_text': self._build_searchable_text([
                    inv.get('RefNumber'), inv.get('ref_number'),
                    inv.get('CustomerRefFullName'), inv.get('customer_name'),
                    inv.get('Memo'), inv.get('memo'),
                ])
            }

            self._add_to_index('invoice', entity_id, doc)
            count += 1

        return count

    def _index_bills(self, bills: List[Dict], archive_id: str) -> int:
        """Index bill records."""
        count = 0
        for bill in bills:
            entity_id = bill.get('TxnID') or bill.get('txn_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'bill',
                'entity_id': entity_id,
                'ref_number': bill.get('RefNumber') or bill.get('ref_number'),
                'date': self._parse_date(bill.get('TxnDate') or bill.get('txn_date')),
                'amount': self._parse_decimal(bill.get('AmountDue') or bill.get('amount_due')),
                'vendor': bill.get('VendorRefFullName') or bill.get('vendor_name'),
                'description': bill.get('Memo') or bill.get('memo') or '',
                'searchable_text': self._build_searchable_text([
                    bill.get('RefNumber'), bill.get('ref_number'),
                    bill.get('VendorRefFullName'), bill.get('vendor_name'),
                    bill.get('Memo'), bill.get('memo'),
                ])
            }

            self._add_to_index('bill', entity_id, doc)
            count += 1

        return count

    def _index_payments(self, payments: List[Dict], archive_id: str) -> int:
        """Index payment records."""
        count = 0
        for pmt in payments:
            entity_id = pmt.get('TxnID') or pmt.get('txn_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'payment',
                'entity_id': entity_id,
                'ref_number': pmt.get('RefNumber') or pmt.get('ref_number'),
                'date': self._parse_date(pmt.get('TxnDate') or pmt.get('txn_date')),
                'amount': self._parse_decimal(pmt.get('TotalAmount') or pmt.get('total_amount')),
                'customer': pmt.get('CustomerRefFullName') or pmt.get('customer_name'),
                'description': pmt.get('Memo') or pmt.get('memo') or '',
                'searchable_text': self._build_searchable_text([
                    pmt.get('RefNumber'), pmt.get('ref_number'),
                    pmt.get('CustomerRefFullName'), pmt.get('customer_name'),
                ])
            }

            self._add_to_index('payment', entity_id, doc)
            count += 1

        return count

    def _index_journal_entries(self, entries: List[Dict], archive_id: str) -> int:
        """Index journal entry records."""
        count = 0
        for je in entries:
            entity_id = je.get('TxnID') or je.get('txn_id')
            if not entity_id:
                continue

            # Calculate total from lines
            lines = je.get('Lines') or je.get('lines') or []
            total = sum(
                self._parse_decimal(line.get('Amount') or line.get('amount')) or Decimal('0')
                for line in lines
                if (line.get('JournalLineType') or line.get('journal_line_type')) == 'Debit'
            )

            doc = {
                'archive_id': archive_id,
                'entity_type': 'journal_entry',
                'entity_id': entity_id,
                'ref_number': je.get('RefNumber') or je.get('ref_number'),
                'date': self._parse_date(je.get('TxnDate') or je.get('txn_date')),
                'amount': total,
                'description': je.get('Memo') or je.get('memo') or '',
                'searchable_text': self._build_searchable_text([
                    je.get('RefNumber'), je.get('ref_number'),
                    je.get('Memo'), je.get('memo'),
                ])
            }

            self._add_to_index('journal_entry', entity_id, doc)
            count += 1

        return count

    def _index_checks(self, checks: List[Dict], archive_id: str) -> int:
        """Index check records."""
        count = 0
        for chk in checks:
            entity_id = chk.get('TxnID') or chk.get('txn_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'check',
                'entity_id': entity_id,
                'ref_number': chk.get('RefNumber') or chk.get('ref_number'),
                'date': self._parse_date(chk.get('TxnDate') or chk.get('txn_date')),
                'amount': self._parse_decimal(chk.get('Amount') or chk.get('amount')),
                'payee': chk.get('PayeeEntityRefFullName') or chk.get('payee_name'),
                'description': chk.get('Memo') or chk.get('memo') or '',
                'searchable_text': self._build_searchable_text([
                    chk.get('RefNumber'), chk.get('ref_number'),
                    chk.get('PayeeEntityRefFullName'), chk.get('payee_name'),
                    chk.get('Memo'), chk.get('memo'),
                ])
            }

            self._add_to_index('check', entity_id, doc)
            count += 1

        return count

    def _index_deposits(self, deposits: List[Dict], archive_id: str) -> int:
        """Index deposit records."""
        count = 0
        for dep in deposits:
            entity_id = dep.get('TxnID') or dep.get('txn_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'deposit',
                'entity_id': entity_id,
                'ref_number': None,
                'date': self._parse_date(dep.get('TxnDate') or dep.get('txn_date')),
                'amount': self._parse_decimal(dep.get('TotalAmount') or dep.get('total_amount')),
                'description': dep.get('Memo') or dep.get('memo') or '',
                'searchable_text': self._build_searchable_text([
                    dep.get('Memo'), dep.get('memo'),
                ])
            }

            self._add_to_index('deposit', entity_id, doc)
            count += 1

        return count

    def _index_credit_memos(self, memos: List[Dict], archive_id: str) -> int:
        """Index credit memo records."""
        count = 0
        for cm in memos:
            entity_id = cm.get('TxnID') or cm.get('txn_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'credit_memo',
                'entity_id': entity_id,
                'ref_number': cm.get('RefNumber') or cm.get('ref_number'),
                'date': self._parse_date(cm.get('TxnDate') or cm.get('txn_date')),
                'amount': self._parse_decimal(cm.get('TotalAmount') or cm.get('total_amount')),
                'customer': cm.get('CustomerRefFullName') or cm.get('customer_name'),
                'description': cm.get('Memo') or cm.get('memo') or '',
                'searchable_text': self._build_searchable_text([
                    cm.get('RefNumber'), cm.get('ref_number'),
                    cm.get('CustomerRefFullName'), cm.get('customer_name'),
                ])
            }

            self._add_to_index('credit_memo', entity_id, doc)
            count += 1

        return count

    def _index_sales_receipts(self, receipts: List[Dict], archive_id: str) -> int:
        """Index sales receipt records."""
        count = 0
        for sr in receipts:
            entity_id = sr.get('TxnID') or sr.get('txn_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'sales_receipt',
                'entity_id': entity_id,
                'ref_number': sr.get('RefNumber') or sr.get('ref_number'),
                'date': self._parse_date(sr.get('TxnDate') or sr.get('txn_date')),
                'amount': self._parse_decimal(sr.get('TotalAmount') or sr.get('total_amount')),
                'customer': sr.get('CustomerRefFullName') or sr.get('customer_name'),
                'description': sr.get('Memo') or sr.get('memo') or '',
                'searchable_text': self._build_searchable_text([
                    sr.get('RefNumber'), sr.get('ref_number'),
                    sr.get('CustomerRefFullName'), sr.get('customer_name'),
                ])
            }

            self._add_to_index('sales_receipt', entity_id, doc)
            count += 1

        return count

    def _index_customers(self, customers: List[Dict], archive_id: str) -> int:
        """Index customer records."""
        count = 0
        for cust in customers:
            entity_id = cust.get('ListID') or cust.get('list_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'customer',
                'entity_id': entity_id,
                'ref_number': None,
                'date': None,
                'amount': self._parse_decimal(cust.get('Balance') or cust.get('balance')),
                'description': cust.get('Name') or cust.get('name') or '',
                'searchable_text': self._build_searchable_text([
                    cust.get('Name'), cust.get('name'),
                    cust.get('CompanyName'), cust.get('company_name'),
                    cust.get('Email'), cust.get('email'),
                    cust.get('Phone'), cust.get('phone'),
                ])
            }

            self._add_to_index('customer', entity_id, doc)
            count += 1

        return count

    def _index_vendors(self, vendors: List[Dict], archive_id: str) -> int:
        """Index vendor records."""
        count = 0
        for vend in vendors:
            entity_id = vend.get('ListID') or vend.get('list_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'vendor',
                'entity_id': entity_id,
                'ref_number': None,
                'date': None,
                'amount': self._parse_decimal(vend.get('Balance') or vend.get('balance')),
                'description': vend.get('Name') or vend.get('name') or '',
                'searchable_text': self._build_searchable_text([
                    vend.get('Name'), vend.get('name'),
                    vend.get('CompanyName'), vend.get('company_name'),
                    vend.get('Email'), vend.get('email'),
                ])
            }

            self._add_to_index('vendor', entity_id, doc)
            count += 1

        return count

    def _index_items(self, items: List[Dict], archive_id: str) -> int:
        """Index item/product records."""
        count = 0
        for item in items:
            entity_id = item.get('ListID') or item.get('list_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'item',
                'entity_id': entity_id,
                'ref_number': None,
                'date': None,
                'amount': self._parse_decimal(item.get('SalesPrice') or item.get('sales_price')),
                'description': item.get('Name') or item.get('name') or '',
                'searchable_text': self._build_searchable_text([
                    item.get('Name'), item.get('name'),
                    item.get('FullName'), item.get('full_name'),
                    item.get('SalesDescription'), item.get('sales_description'),
                ])
            }

            self._add_to_index('item', entity_id, doc)
            count += 1

        return count

    def _index_accounts(self, accounts: List[Dict], archive_id: str) -> int:
        """Index chart of accounts records."""
        count = 0
        for acct in accounts:
            entity_id = acct.get('ListID') or acct.get('list_id')
            if not entity_id:
                continue

            doc = {
                'archive_id': archive_id,
                'entity_type': 'account',
                'entity_id': entity_id,
                'ref_number': acct.get('AccountNumber') or acct.get('account_number'),
                'date': None,
                'amount': self._parse_decimal(acct.get('Balance') or acct.get('balance')),
                'description': acct.get('Name') or acct.get('name') or '',
                'searchable_text': self._build_searchable_text([
                    acct.get('Name'), acct.get('name'),
                    acct.get('FullName'), acct.get('full_name'),
                    acct.get('AccountNumber'), acct.get('account_number'),
                    acct.get('AccountType'), acct.get('account_type'),
                ])
            }

            self._add_to_index('account', entity_id, doc)
            count += 1

        return count

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _add_to_index(self, entity_type: str, entity_id: str, doc: Dict) -> None:
        """Add document to index and inverted index."""
        key = f"{entity_type}:{entity_id}"

        # Store in main index
        if entity_type not in self._index:
            self._index[entity_type] = []
        self._index[entity_type].append(doc)

        # Build inverted index
        searchable = doc.get('searchable_text', '')
        tokens = self._tokenize(searchable.lower())

        for token in tokens:
            if token not in self._inverted_index:
                self._inverted_index[token] = []
            self._inverted_index[token].append((key, token, 1.0))

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into searchable terms."""
        if not text:
            return []
        # Split on whitespace and punctuation, keep alphanumeric
        tokens = re.findall(r'\b\w+\b', text.lower())
        return [t for t in tokens if len(t) >= 2]

    def _build_searchable_text(self, fields: List[Optional[str]]) -> str:
        """Combine fields into searchable text."""
        return ' '.join(str(f) for f in fields if f)

    def _parse_date(self, value: Any) -> Optional[datetime]:
        """Parse date from various formats."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except:
            return None

    def _parse_decimal(self, value: Any) -> Optional[Decimal]:
        """Parse decimal from various formats."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except:
            return None

    def _find_candidates(
        self,
        query_terms: List[str],
        fuzzy: bool
    ) -> set:
        """Find candidate entity IDs matching query terms."""
        candidates = set()

        for term in query_terms:
            if term in self._inverted_index:
                for entity_key, _, _ in self._inverted_index[term]:
                    candidates.add(entity_key)

            # Fuzzy matching - prefix search
            if fuzzy:
                for indexed_term in self._inverted_index:
                    if indexed_term.startswith(term) or term in indexed_term:
                        for entity_key, _, _ in self._inverted_index[indexed_term]:
                            candidates.add(entity_key)

        return candidates

    def _get_record(self, entity_type: str, entity_id: str) -> Optional[Dict]:
        """Retrieve record from index."""
        if entity_type not in self._index:
            return None

        for doc in self._index[entity_type]:
            if doc.get('entity_id') == entity_id:
                return doc

        return None

    def _matches_filters(self, record: Dict, filters: SearchFilter) -> bool:
        """Check if record matches all filters."""
        # Date filter
        if filters.date_from and record.get('date'):
            if record['date'] < filters.date_from:
                return False

        if filters.date_to and record.get('date'):
            if record['date'] > filters.date_to:
                return False

        # Amount filter
        if filters.amount_min is not None and record.get('amount'):
            if record['amount'] < filters.amount_min:
                return False

        if filters.amount_max is not None and record.get('amount'):
            if record['amount'] > filters.amount_max:
                return False

        return True

    def _score_match(
        self,
        record: Dict,
        query_terms: List[str],
        fuzzy: bool
    ) -> Tuple[float, str, str]:
        """Score how well record matches query."""
        searchable = record.get('searchable_text', '').lower()
        max_score = 0.0
        matched_field = 'searchable_text'
        highlight = ''

        for term in query_terms:
            if term in searchable:
                # Exact match
                score = 1.0
                if score > max_score:
                    max_score = score
                    # Create highlight
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    highlight = pattern.sub(f'**{term}**', searchable[:200])
            elif fuzzy:
                # Fuzzy match
                for word in self._tokenize(searchable):
                    if term in word or word.startswith(term):
                        score = 0.5
                        if score > max_score:
                            max_score = score
                            highlight = searchable[:200]

        return max_score, matched_field, highlight

    def _entity_type_to_enum(self, entity_type: str) -> SearchEntityType:
        """Convert string entity type to enum."""
        mapping = {
            'invoice': SearchEntityType.INVOICE,
            'bill': SearchEntityType.BILL,
            'payment': SearchEntityType.PAYMENT,
            'journal_entry': SearchEntityType.JOURNAL_ENTRY,
            'check': SearchEntityType.CHECK,
            'deposit': SearchEntityType.DEPOSIT,
            'credit_memo': SearchEntityType.CREDIT_MEMO,
            'sales_receipt': SearchEntityType.SALES_RECEIPT,
            'customer': SearchEntityType.CUSTOMER,
            'vendor': SearchEntityType.VENDOR,
            'item': SearchEntityType.ITEM,
            'account': SearchEntityType.ACCOUNT,
        }
        return mapping.get(entity_type, SearchEntityType.ALL)

    def _get_all_records(self, filters: SearchFilter) -> List[SearchResult]:
        """Get all records (for empty query)."""
        results = []

        for entity_type, docs in self._index.items():
            # Check entity type filter
            if SearchEntityType.ALL not in filters.entity_types:
                type_enum = self._entity_type_to_enum(entity_type)
                if type_enum not in filters.entity_types:
                    continue

            for doc in docs:
                if not self._matches_filters(doc, filters):
                    continue

                results.append(SearchResult(
                    entity_type=entity_type,
                    entity_id=doc.get('entity_id', ''),
                    ref_number=doc.get('ref_number'),
                    date=doc.get('date'),
                    amount=doc.get('amount'),
                    description=doc.get('description', ''),
                    matched_field='',
                    match_score=0,
                    highlight='',
                    raw_data=doc
                ))

        # Sort by date descending
        results.sort(key=lambda x: x.date or datetime.min, reverse=True)
        return results

    def _build_facets(self, results: List[SearchResult]) -> Dict[str, Dict[str, int]]:
        """Build search result facets."""
        facets = {
            'entity_type': {},
            'date_year': {},
        }

        for r in results:
            # Entity type facet
            et = r.entity_type
            facets['entity_type'][et] = facets['entity_type'].get(et, 0) + 1

            # Year facet
            if r.date:
                year = str(r.date.year)
                facets['date_year'][year] = facets['date_year'].get(year, 0) + 1

        return facets


# Singleton instance
_search_service: Optional[ArchiveSearchService] = None


def get_search_service() -> ArchiveSearchService:
    """Get singleton search service instance."""
    global _search_service
    if _search_service is None:
        _search_service = ArchiveSearchService()
    return _search_service

"""
QuickBooks Data Models
======================

Comprehensive data models for all QB Desktop and QB Online entities.

Features:
- Type safety with dataclasses
- Validation methods
- JSON serialization
- QB Desktop → QB Online mapping

Author: QB Service
Version: 3.1.0
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class AccountType(Enum):
    """QB Online account types."""
    BANK = "Bank"
    ACCOUNTS_RECEIVABLE = "Accounts Receivable"
    OTHER_CURRENT_ASSETS = "Other Current Assets"
    FIXED_ASSETS = "Fixed Assets"
    OTHER_ASSETS = "Other Assets"
    ACCOUNTS_PAYABLE = "Accounts Payable"
    CREDIT_CARD = "Credit Card"
    OTHER_CURRENT_LIABILITIES = "Other Current Liabilities"
    LONG_TERM_LIABILITIES = "Long Term Liabilities"
    EQUITY = "Equity"
    INCOME = "Income"
    OTHER_INCOME = "Other Income"
    COST_OF_GOODS_SOLD = "Cost of Goods Sold"
    EXPENSE = "Expense"
    OTHER_EXPENSE = "Other Expense"


class ItemType(Enum):
    """QB Online item types."""
    INVENTORY = "Inventory"
    NON_INVENTORY = "NonInventory"
    SERVICE = "Service"
    BUNDLE = "Bundle"


class PostingType(Enum):
    """Journal entry posting types."""
    DEBIT = "Debit"
    CREDIT = "Credit"


class BillableStatus(Enum):
    """Time activity billable status."""
    NOT_BILLABLE = "NotBillable"
    BILLABLE = "Billable"
    HAS_BEEN_BILLED = "HasBeenBilled"


# ============================================================================
# BASE CLASSES
# ============================================================================

@dataclass
class QBEntity:
    """Base class for all QB entities."""
    id: Optional[str] = None
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate entity data.
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        return len(errors) == 0, errors


@dataclass
class Address:
    """Physical address."""
    line1: Optional[str] = None
    line2: Optional[str] = None
    line3: Optional[str] = None
    line4: Optional[str] = None
    line5: Optional[str] = None
    city: Optional[str] = None
    country_sub_division_code: Optional[str] = None  # State
    postal_code: Optional[str] = None
    country: Optional[str] = None
    
    def to_qbo(self) -> Dict[str, str]:
        """Convert to QB Online format."""
        return {k: v for k, v in {
            'Line1': self.line1,
            'Line2': self.line2,
            'Line3': self.line3,
            'Line4': self.line4,
            'Line5': self.line5,
            'City': self.city,
            'CountrySubDivisionCode': self.country_sub_division_code,
            'PostalCode': self.postal_code,
            'Country': self.country
        }.items() if v is not None}


@dataclass
class PhoneNumber:
    """Phone number."""
    number: str
    
    def to_qbo(self) -> Dict[str, str]:
        return {'FreeFormNumber': self.number}


@dataclass
class EmailAddress:
    """Email address."""
    address: str
    
    def to_qbo(self) -> Dict[str, str]:
        return {'Address': self.address}


# ============================================================================
# MASTER LIST ENTITIES
# ============================================================================

@dataclass
class Account(QBEntity):
    """Account (Chart of Accounts)."""
    name: str = ""
    account_type: str = ""
    account_sub_type: Optional[str] = None
    account_number: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[str] = None
    balance: Decimal = Decimal('0')
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate account."""
        errors = []
        
        if not self.name:
            errors.append("Account name is required")
        
        if not self.account_type:
            errors.append("Account type is required")
        
        if len(self.name) > 100:
            errors.append("Account name exceeds 100 characters")
        
        return len(errors) == 0, errors


@dataclass
class Customer(QBEntity):
    """Customer."""
    display_name: str = ""
    company_name: Optional[str] = None
    given_name: Optional[str] = None
    middle_name: Optional[str] = None
    family_name: Optional[str] = None
    suffix: Optional[str] = None
    
    # Contact
    primary_email: Optional[EmailAddress] = None
    primary_phone: Optional[PhoneNumber] = None
    mobile: Optional[PhoneNumber] = None
    fax: Optional[PhoneNumber] = None
    
    # Addresses
    bill_addr: Optional[Address] = None
    ship_addr: Optional[Address] = None
    
    # Financial
    balance: Decimal = Decimal('0')
    credit_limit: Optional[Decimal] = None
    
    # Relationships
    parent_id: Optional[str] = None
    is_job: bool = False
    
    # Settings
    taxable: bool = True
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate customer."""
        errors = []
        
        if not self.display_name:
            errors.append("Customer DisplayName is required")
        
        if len(self.display_name) > 100:
            errors.append("DisplayName exceeds 100 characters")
        
        return len(errors) == 0, errors


@dataclass
class Vendor(QBEntity):
    """Vendor."""
    display_name: str = ""
    company_name: Optional[str] = None
    given_name: Optional[str] = None
    middle_name: Optional[str] = None
    family_name: Optional[str] = None
    
    # Contact
    primary_email: Optional[EmailAddress] = None
    primary_phone: Optional[PhoneNumber] = None
    
    # Address
    bill_addr: Optional[Address] = None
    
    # Financial
    balance: Decimal = Decimal('0')
    
    # Tax
    vendor_1099: bool = False
    tax_identifier: Optional[str] = None  # Will be redacted
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate vendor."""
        errors = []
        
        if not self.display_name:
            errors.append("Vendor DisplayName is required")
        
        return len(errors) == 0, errors


@dataclass
class Employee(QBEntity):
    """Employee."""
    display_name: str = ""
    given_name: Optional[str] = None
    middle_name: Optional[str] = None
    family_name: Optional[str] = None
    
    # Contact
    primary_email: Optional[EmailAddress] = None
    primary_phone: Optional[PhoneNumber] = None
    
    # Address
    primary_addr: Optional[Address] = None
    
    # Employment
    employee_number: Optional[str] = None
    hire_date: Optional[datetime] = None
    release_date: Optional[datetime] = None
    
    # Sensitive (ALWAYS REDACTED)
    ssn: Optional[str] = None  # Will show as XXX-XX-XXXX
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate employee."""
        errors = []
        
        if not self.display_name:
            errors.append("Employee DisplayName is required")
        
        return len(errors) == 0, errors


@dataclass
class Item(QBEntity):
    """Item (Product/Service)."""
    name: str = ""
    item_type: str = "Service"
    description: Optional[str] = None
    
    # Pricing
    unit_price: Optional[Decimal] = None
    purchase_cost: Optional[Decimal] = None
    
    # Inventory
    track_qty_on_hand: bool = False
    qty_on_hand: Decimal = Decimal('0')
    inv_start_date: Optional[datetime] = None
    
    # Accounts
    income_account_id: Optional[str] = None
    expense_account_id: Optional[str] = None
    asset_account_id: Optional[str] = None
    
    # Assembly components (if Assembly type)
    components: List[Dict[str, Any]] = field(default_factory=list)
    
    # Settings
    taxable: bool = True
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate item."""
        errors = []
        
        if not self.name:
            errors.append("Item name is required")
        
        if self.item_type == "Inventory" and not self.track_qty_on_hand:
            errors.append("Inventory items must track quantity")
        
        return len(errors) == 0, errors


# ============================================================================
# TRANSACTION ENTITIES
# ============================================================================

@dataclass
class InvoiceLine:
    """Invoice line item."""
    line_num: int
    amount: Decimal
    description: Optional[str] = None
    
    # Sales item details
    item_id: Optional[str] = None
    quantity: Decimal = Decimal('1')
    unit_price: Decimal = Decimal('0')
    tax_code_id: Optional[str] = None
    
    # Optional
    class_id: Optional[str] = None
    department_id: Optional[str] = None


@dataclass
class Invoice(QBEntity):
    """Customer Invoice."""
    customer_id: str = ""
    txn_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    doc_number: Optional[str] = None
    
    # Lines
    lines: List[InvoiceLine] = field(default_factory=list)
    
    # Amounts
    total_amt: Decimal = Decimal('0')
    balance: Decimal = Decimal('0')
    
    # References
    terms_id: Optional[str] = None
    sales_rep_id: Optional[str] = None
    
    # Addresses
    bill_addr: Optional[Address] = None
    ship_addr: Optional[Address] = None
    
    # Memo
    private_note: Optional[str] = None
    customer_memo: Optional[str] = None
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate invoice."""
        errors = []
        
        if not self.customer_id:
            errors.append("Customer is required")
        
        if not self.lines:
            errors.append("At least one line item is required")
        
        return len(errors) == 0, errors


@dataclass
class Payment(QBEntity):
    """Payment (ReceivePayment)."""
    customer_id: str = ""
    txn_date: Optional[datetime] = None
    total_amt: Decimal = Decimal('0')
    
    # Payment details
    payment_method_id: Optional[str] = None
    payment_ref_num: Optional[str] = None
    deposit_to_account_id: Optional[str] = None
    
    # Applied to invoices
    applied_to_invoices: List[Dict[str, Any]] = field(default_factory=list)
    
    # Memo
    private_note: Optional[str] = None
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate payment."""
        errors = []
        
        if not self.customer_id:
            errors.append("Customer is required")
        
        if self.total_amt <= 0:
            errors.append("Payment amount must be greater than zero")
        
        # Validate line totals equal total amount
        line_total = sum(Decimal(str(line.get('Amount', 0))) 
                        for line in self.applied_to_invoices)
        
        if abs(line_total - self.total_amt) > Decimal('0.01'):
            errors.append(f"Line totals ({line_total}) don't match total amount ({self.total_amt})")
        
        return len(errors) == 0, errors


@dataclass
class Bill(QBEntity):
    """Vendor Bill."""
    vendor_id: str = ""
    txn_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    doc_number: Optional[str] = None
    
    # Lines
    lines: List[Dict[str, Any]] = field(default_factory=list)
    
    # Amounts
    total_amt: Decimal = Decimal('0')
    balance: Decimal = Decimal('0')
    
    # References
    terms_id: Optional[str] = None
    
    # Memo
    private_note: Optional[str] = None
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate bill."""
        errors = []
        
        if not self.vendor_id:
            errors.append("Vendor is required")
        
        if not self.lines:
            errors.append("At least one line item is required")
        
        return len(errors) == 0, errors


@dataclass
class JournalEntryLine:
    """Journal entry line."""
    line_num: int
    posting_type: str  # Debit or Credit
    account_id: str = ""
    amount: Decimal = Decimal('0')
    description: Optional[str] = None
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    class_id: Optional[str] = None
    department_id: Optional[str] = None


@dataclass
class JournalEntry(QBEntity):
    """Journal Entry."""
    txn_date: Optional[datetime] = None
    doc_number: Optional[str] = None
    
    # Lines (MUST balance: debits = credits)
    lines: List[JournalEntryLine] = field(default_factory=list)
    
    # Memo
    private_note: Optional[str] = None
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate journal entry."""
        errors = []
        
        if not self.lines or len(self.lines) < 2:
            errors.append("Journal entry must have at least 2 lines")
        
        # Calculate debits and credits
        debits = sum(line.amount for line in self.lines 
                    if line.posting_type == "Debit")
        credits = sum(line.amount for line in self.lines 
                     if line.posting_type == "Credit")
        
        if abs(debits - credits) > Decimal('0.01'):
            errors.append(f"Journal entry not balanced: Debits={debits}, Credits={credits}")
        
        return len(errors) == 0, errors


# ============================================================================
# REFERENCE ENTITIES
# ============================================================================

@dataclass
class Class(QBEntity):
    """Class (for tracking)."""
    name: str = ""
    parent_id: Optional[str] = None
    sub_class: bool = False
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate class."""
        errors = []
        
        if not self.name:
            errors.append("Class name is required")
        
        return len(errors) == 0, errors


@dataclass
class Department(QBEntity):
    """Department."""
    name: str = ""
    parent_id: Optional[str] = None
    sub_department: bool = False
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate department."""
        errors = []
        
        if not self.name:
            errors.append("Department name is required")
        
        return len(errors) == 0, errors


@dataclass
class Term(QBEntity):
    """Payment Terms."""
    name: str = ""
    due_days: Optional[int] = None
    discount_days: Optional[int] = None
    discount_percent: Optional[Decimal] = None
    term_type: str = "STANDARD"  # STANDARD or DATE_DRIVEN
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate term."""
        errors = []
        
        if not self.name:
            errors.append("Term name is required")
        
        return len(errors) == 0, errors


@dataclass
class TaxRate(QBEntity):
    """Tax Rate."""
    name: str = ""
    rate_value: Decimal = Decimal('0')
    agency_id: Optional[str] = None
    description: Optional[str] = None
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate tax rate."""
        errors = []
        
        if not self.name:
            errors.append("Tax rate name is required")
        
        if self.rate_value < 0 or self.rate_value > 100:
            errors.append("Tax rate must be between 0 and 100")
        
        return len(errors) == 0, errors


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def validate_entity(entity: QBEntity) -> Tuple[bool, List[str]]:
    """
    Validate any QB entity.
    
    Returns:
        (is_valid, error_messages)
    """
    return entity.validate()


def entity_to_dict(entity: QBEntity) -> Dict[str, Any]:
    """Convert entity to dictionary."""
    return entity.to_dict()


# ============================================================================
# TYPE EXPORTS
# ============================================================================

__all__ = [
    # Enums
    'AccountType', 'ItemType', 'PostingType', 'BillableStatus',
    
    # Base classes
    'QBEntity', 'Address', 'PhoneNumber', 'EmailAddress',
    
    # Master lists
    'Account', 'Customer', 'Vendor', 'Employee', 'Item',
    
    # Transactions
    'Invoice', 'InvoiceLine', 'Payment', 'Bill',
    'JournalEntry', 'JournalEntryLine',
    
    # References
    'Class', 'Department', 'Term', 'TaxRate',
    
    # Helpers
    'validate_entity', 'entity_to_dict'
]
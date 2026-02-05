"""
QuickBooks JSON Schemas
=======================

JSON Schema validation for QB Desktop and QB Online data.

$25M FIXES APPLIED:
✓ data_hash_sha256 REQUIRED in encrypted data
✓ Linked transaction schemas (prevents payment→invoice failures)
✓ Hash integrity validation

Features:
- Input data validation
- Output data validation
- API request/response validation
- Linked transaction validation (CRITICAL)
- Type checking
- Forensic hash validation

Author: QB Service
Version: 3.2.0 (Enterprise Security Edition)
"""

from typing import Any, Dict, List, Tuple

# ============================================================================
# QB DESKTOP INPUT SCHEMAS
# ============================================================================

QBD_ACCOUNT_SCHEMA = {
    "type": "object",
    "required": ["Name", "AccountType"],
    "properties": {
        "Name": {"type": "string", "maxLength": 100},
        "AccountType": {"type": "string"},
        "AccountNumber": {"type": "string", "maxLength": 7},
        "Description": {"type": "string", "maxLength": 200},
        "ParentRef": {"type": "string"},
        "Balance": {"type": "number"},
        "IsActive": {"type": "boolean"},
    },
}

QBD_CUSTOMER_SCHEMA = {
    "type": "object",
    "required": ["Name"],
    "properties": {
        "Name": {"type": "string", "maxLength": 100},
        "CompanyName": {"type": "string", "maxLength": 100},
        "FirstName": {"type": "string", "maxLength": 25},
        "LastName": {"type": "string", "maxLength": 25},
        "Email": {"type": "string", "format": "email"},
        "Phone": {"type": "string"},
        "BillAddress": {"type": "object"},
        "Balance": {"type": "number"},
        "IsActive": {"type": "boolean"},
    },
}

QBD_INVOICE_SCHEMA = {
    "type": "object",
    "required": ["CustomerRef", "InvoiceLines"],
    "properties": {
        "CustomerRef": {"type": "string"},
        "TxnDate": {"type": "string", "format": "date"},
        "DueDate": {"type": "string", "format": "date"},
        "RefNumber": {"type": "string"},
        "InvoiceLines": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["ItemRef", "Amount"],
                "properties": {
                    "ItemRef": {"type": "string"},
                    "Quantity": {"type": "number"},
                    "Rate": {"type": "number"},
                    "Amount": {"type": "number"},
                },
            },
        },
    },
}

# ============================================================================
# QB ONLINE OUTPUT SCHEMAS
# ============================================================================

QBO_ACCOUNT_SCHEMA = {
    "type": "object",
    "required": ["Name", "AccountType"],
    "properties": {
        "Name": {"type": "string"},
        "AccountType": {"type": "string"},
        "AccountSubType": {"type": "string"},
        "AcctNum": {"type": "string"},
        "Description": {"type": "string"},
        "ParentRef": {"type": "object", "properties": {"value": {"type": "string"}}},
        "Active": {"type": "boolean"},
    },
}

QBO_CUSTOMER_SCHEMA = {
    "type": "object",
    "required": ["DisplayName"],
    "properties": {
        "DisplayName": {"type": "string"},
        "CompanyName": {"type": "string"},
        "GivenName": {"type": "string"},
        "FamilyName": {"type": "string"},
        "PrimaryEmailAddr": {
            "type": "object",
            "properties": {"Address": {"type": "string"}},
        },
        "PrimaryPhone": {
            "type": "object",
            "properties": {"FreeFormNumber": {"type": "string"}},
        },
        "Active": {"type": "boolean"},
    },
}

QBO_INVOICE_SCHEMA = {
    "type": "object",
    "required": ["CustomerRef", "Line"],
    "properties": {
        "CustomerRef": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "string"}},
        },
        "TxnDate": {"type": "string"},
        "DueDate": {"type": "string"},
        "DocNumber": {"type": "string"},
        "Line": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["DetailType", "Amount"],
                "properties": {
                    "DetailType": {"type": "string"},
                    "Amount": {"type": "number"},
                    "SalesItemLineDetail": {"type": "object"},
                },
            },
        },
    },
}

# ============================================================================
# LINKED TRANSACTION SCHEMAS - $25M FIX (Prevents #1 failure point)
# ============================================================================

LINKED_TRANSACTION_SCHEMA = {
    "type": "object",
    "required": ["TxnType", "TxnId"],
    "properties": {
        "TxnType": {
            "type": "string",
            "enum": [
                "Invoice",
                "Payment",
                "Bill",
                "BillPayment",
                "Estimate",
                "SalesReceipt",
                "CreditMemo",
                "VendorCredit",
                "JournalEntry",
            ],
            "description": "Type of linked transaction (CRITICAL for payment→invoice links)",
        },
        "TxnId": {
            "type": "string",
            "minLength": 1,
            "description": "ID of the linked transaction (must not be empty)",
        },
        "TxnLineId": {
            "type": "string",
            "description": "Optional: Specific line item being linked",
        },
    },
}

QBO_PAYMENT_SCHEMA = {
    "type": "object",
    "required": ["CustomerRef", "TotalAmt"],
    "properties": {
        "CustomerRef": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "string"}},
        },
        "TotalAmt": {"type": "number"},
        "TxnDate": {"type": "string"},
        "Line": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["Amount", "LinkedTxn"],
                "properties": {
                    "Amount": {"type": "number"},
                    "LinkedTxn": {
                        "type": "array",
                        "minItems": 1,
                        "items": LINKED_TRANSACTION_SCHEMA,
                        "description": "CRITICAL: Links payment to invoice (prevents unapplied payments)",
                    },
                },
            },
        },
    },
}

QBO_BILL_PAYMENT_SCHEMA = {
    "type": "object",
    "required": ["VendorRef", "TotalAmt"],
    "properties": {
        "VendorRef": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "string"}},
        },
        "TotalAmt": {"type": "number"},
        "Line": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["Amount", "LinkedTxn"],
                "properties": {
                    "Amount": {"type": "number"},
                    "LinkedTxn": {
                        "type": "array",
                        "minItems": 1,
                        "items": LINKED_TRANSACTION_SCHEMA,
                        "description": "CRITICAL: Links payment to bill",
                    },
                },
            },
        },
    },
}

QBO_CREDIT_MEMO_APPLICATION_SCHEMA = {
    "type": "object",
    "required": ["Amount", "LinkedTxn"],
    "properties": {
        "Amount": {"type": "number"},
        "LinkedTxn": {
            "type": "array",
            "items": LINKED_TRANSACTION_SCHEMA,
            "description": "Links credit memo to invoice",
        },
    },
}

# ============================================================================
# ENCRYPTED DATA SCHEMA - $25M FIX APPLIED
# ============================================================================

ENCRYPTED_DATA_SCHEMA = {
    "type": "object",
    "required": ["iv", "tag", "ciphertext", "key", "data_hash_sha256"],
    "properties": {
        "iv": {
            "type": "string",
            "description": "Base64-encoded initialization vector (12 bytes)",
        },
        "tag": {
            "type": "string",
            "description": "Base64-encoded GCM authentication tag (16 bytes)",
        },
        "ciphertext": {
            "type": "string",
            "description": "Base64-encoded encrypted data",
        },
        "key": {
            "type": "string",
            "description": "Base64-encoded encryption key (32 bytes)",
        },
        "data_hash_sha256": {
            "type": "string",
            "pattern": "^[a-fA-F0-9]{64}$",
            "description": "SHA-256 hash of plaintext (64 hex chars) - FORENSIC INTEGRITY",
        },
        "algorithm": {
            "type": "string",
            "enum": ["AES-256-GCM"],
            "description": "Encryption algorithm used",
        },
        "version": {"type": "string", "description": "Encryption format version"},
    },
}

# ============================================================================
# MIGRATION REQUEST SCHEMA
# ============================================================================

MIGRATION_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["encrypted_data", "migration_id"],
    "properties": {
        "encrypted_data": {"oneOf": [{"type": "string"}, ENCRYPTED_DATA_SCHEMA]},
        "migration_id": {"type": "string", "pattern": "^[a-zA-Z0-9_-]+$"},
        "options": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "enum": ["US", "CA", "UK", "AU", "IN", "FR"],
                },
                "enable_multi_currency": {"type": "boolean"},
                "skip_verification": {"type": "boolean"},
            },
        },
    },
}

# ============================================================================
# MIGRATION RESPONSE SCHEMA - $25M FIX APPLIED
# ============================================================================

MIGRATION_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["success", "migration_id"],
    "properties": {
        "success": {"type": "boolean"},
        "migration_id": {"type": "string"},
        "message": {"type": "string"},
        "data_integrity": {
            "type": "object",
            "properties": {
                "source_hash_sha256": {
                    "type": "string",
                    "pattern": "^[a-fA-F0-9]{64}$",
                },
                "destination_hash_sha256": {
                    "type": "string",
                    "pattern": "^[a-fA-F0-9]{64}$",
                },
                "hash_verified": {"type": "boolean"},
                "verification_status": {
                    "type": "string",
                    "enum": ["PASSED", "FAILED", "NOT_AVAILABLE"],
                },
            },
            "required": ["hash_verified", "verification_status"],
        },
        "summary": {
            "type": "object",
            "properties": {
                "total_entities": {"type": "integer"},
                "successful": {"type": "integer"},
                "failed": {"type": "integer"},
                "duration_seconds": {"type": "number"},
            },
        },
        "trial_balance": {
            "type": "object",
            "properties": {
                "debits": {"type": "string"},
                "credits": {"type": "string"},
                "balanced": {"type": "boolean"},
            },
        },
        "errors": {"type": "array", "items": {"type": "string"}},
    },
}

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================


def validate_qbd_data(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate QB Desktop data structure"""
    errors = []

    if not isinstance(data, dict):
        return False, ["Data must be a dictionary"]

    for entity_type in ["Accounts", "Customers", "Vendors", "Items", "Invoices"]:
        if entity_type in data:
            if not isinstance(data[entity_type], list):
                errors.append(f"{entity_type} must be a list")

    has_data = any(
        entity_type in data and len(data[entity_type]) > 0
        for entity_type in ["Accounts", "Customers", "Vendors", "Items"]
    )

    if not has_data:
        errors.append("Data must contain at least one entity type")

    return len(errors) == 0, errors


def validate_qbo_data(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate QB Online data structure"""
    errors = []

    if not isinstance(data, dict):
        return False, ["Data must be a dictionary"]

    if "entities" not in data:
        errors.append("Missing 'entities' field")

    return len(errors) == 0, errors


def validate_encrypted_data(data: Any) -> Tuple[bool, List[str]]:
    """$25M FIX: Validate encrypted data WITH REQUIRED HASH"""
    errors = []

    if isinstance(data, str):
        parts = data.split(":")
        if len(parts) not in [3, 4]:
            errors.append("Invalid encrypted string format")
        else:
            errors.append("WARNING: Legacy format. Upgrade to JSON with hash.")
    elif isinstance(data, dict):
        required_fields = ["iv", "tag", "ciphertext", "key", "data_hash_sha256"]
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing REQUIRED field: {field}")

        if "data_hash_sha256" in data:
            import re

            hash_value = data["data_hash_sha256"]
            if not isinstance(hash_value, str):
                errors.append("data_hash_sha256 must be a string")
            elif not re.match(r"^[a-fA-F0-9]{64}$", hash_value):
                errors.append("data_hash_sha256 must be 64 hex characters")
    else:
        errors.append("Encrypted data must be string or dict")

    return len(errors) == 0, errors


def validate_linked_transaction(linked_txn: Dict) -> Tuple[bool, List[str]]:
    """
    $25M FIX: Validate linked transaction structure

    Prevents #1 cause of migration failures: broken payment→invoice links
    """
    errors = []

    if not isinstance(linked_txn, dict):
        return False, ["Linked transaction must be a dictionary"]

    if "TxnType" not in linked_txn:
        errors.append("Missing TxnType in linked transaction")

    if "TxnId" not in linked_txn:
        errors.append("Missing TxnId in linked transaction")

    valid_types = [
        "Invoice",
        "Payment",
        "Bill",
        "BillPayment",
        "Estimate",
        "SalesReceipt",
        "CreditMemo",
        "VendorCredit",
        "JournalEntry",
    ]

    if linked_txn.get("TxnType") not in valid_types:
        errors.append(f"Invalid TxnType: {linked_txn.get('TxnType')}")

    if linked_txn.get("TxnId") == "" or linked_txn.get("TxnId") is None:
        errors.append("TxnId cannot be empty - this creates unapplied payments")

    return len(errors) == 0, errors


def validate_payment_links(payment: Dict) -> Tuple[bool, List[str]]:
    """
    $25M FIX: Validate payment has proper invoice links

    Critical for AR accuracy. Prevents "both invoice and payment show as open" syndrome.
    """
    errors = []

    if "Line" not in payment:
        return False, ["Payment must have Line array"]

    for i, line in enumerate(payment["Line"]):
        if "LinkedTxn" not in line:
            errors.append(
                f"Line {i} missing LinkedTxn array - payment will be unapplied"
            )
            continue

        if not isinstance(line["LinkedTxn"], list):
            errors.append(f"Line {i} LinkedTxn must be an array")
            continue

        if len(line["LinkedTxn"]) == 0:
            errors.append(f"Line {i} has empty LinkedTxn - creates unapplied payment")

        for j, linked_txn in enumerate(line["LinkedTxn"]):
            valid, link_errors = validate_linked_transaction(linked_txn)
            if not valid:
                errors.extend([f"Line {i} LinkedTxn {j}: {e}" for e in link_errors])

    return len(errors) == 0, errors


def validate_migration_id(migration_id: str) -> Tuple[bool, List[str]]:
    """Validate migration ID format"""
    errors = []

    if not migration_id:
        errors.append("Migration ID is required")

    if not isinstance(migration_id, str):
        errors.append("Migration ID must be a string")

    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", migration_id):
        errors.append("Migration ID contains invalid characters")

    if len(migration_id) > 100:
        errors.append("Migration ID too long (max 100 characters)")

    return len(errors) == 0, errors


def validate_region(region: str) -> Tuple[bool, List[str]]:
    """Validate region code"""
    valid_regions = ["US", "CA", "UK", "AU", "IN", "FR"]

    if region.upper() not in valid_regions:
        return False, [f"Invalid region. Must be one of: {', '.join(valid_regions)}"]

    return True, []


def validate_hash_integrity(
    source_hash: str, destination_hash: str
) -> Tuple[bool, List[str]]:
    """$25M FIX: Validate hash integrity"""
    errors = []

    import re

    hash_pattern = r"^[a-fA-F0-9]{64}$"

    if not re.match(hash_pattern, source_hash):
        errors.append("Invalid source hash format")

    if not re.match(hash_pattern, destination_hash):
        errors.append("Invalid destination hash format")

    if source_hash != destination_hash:
        errors.append(
            f"HASH MISMATCH - DATA INTEGRITY COMPROMISED\n"
            f"  Source:      {source_hash}\n"
            f"  Destination: {destination_hash}"
        )

    return len(errors) == 0, errors


# ============================================================================
# SCHEMA REGISTRY
# ============================================================================

SCHEMAS = {
    # QB Desktop
    "qbd_account": QBD_ACCOUNT_SCHEMA,
    "qbd_customer": QBD_CUSTOMER_SCHEMA,
    "qbd_invoice": QBD_INVOICE_SCHEMA,
    # QB Online
    "qbo_account": QBO_ACCOUNT_SCHEMA,
    "qbo_customer": QBO_CUSTOMER_SCHEMA,
    "qbo_invoice": QBO_INVOICE_SCHEMA,
    "qbo_payment": QBO_PAYMENT_SCHEMA,
    "qbo_bill_payment": QBO_BILL_PAYMENT_SCHEMA,
    # Linked Transactions (CRITICAL)
    "linked_transaction": LINKED_TRANSACTION_SCHEMA,
    "credit_memo_application": QBO_CREDIT_MEMO_APPLICATION_SCHEMA,
    # Migration
    "encrypted_data": ENCRYPTED_DATA_SCHEMA,
    "migration_request": MIGRATION_REQUEST_SCHEMA,
    "migration_response": MIGRATION_RESPONSE_SCHEMA,
}


def get_schema(schema_name: str) -> Dict[str, Any]:
    """Get schema by name"""
    return SCHEMAS.get(schema_name, {})


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Schemas
    "QBD_ACCOUNT_SCHEMA",
    "QBD_CUSTOMER_SCHEMA",
    "QBD_INVOICE_SCHEMA",
    "QBO_ACCOUNT_SCHEMA",
    "QBO_CUSTOMER_SCHEMA",
    "QBO_INVOICE_SCHEMA",
    "QBO_PAYMENT_SCHEMA",
    "QBO_BILL_PAYMENT_SCHEMA",
    "LINKED_TRANSACTION_SCHEMA",
    "QBO_CREDIT_MEMO_APPLICATION_SCHEMA",
    "ENCRYPTED_DATA_SCHEMA",
    "MIGRATION_REQUEST_SCHEMA",
    "MIGRATION_RESPONSE_SCHEMA",
    # Validation functions
    "validate_qbd_data",
    "validate_qbo_data",
    "validate_encrypted_data",
    "validate_migration_id",
    "validate_region",
    "validate_hash_integrity",
    "validate_linked_transaction",
    "validate_payment_links",
    # Helpers
    "get_schema",
    "SCHEMAS",
]

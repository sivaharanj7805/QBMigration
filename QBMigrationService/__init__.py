"""
QBMigrationService - QuickBooks Desktop to Online Migration Service
===================================================================

This package provides enterprise-grade migration functionality for:
- Data extraction from QuickBooks Desktop
- Secure encryption and transfer
- Transformation to QuickBooks Online format
- Verification and audit trail generation

Main Components:
- orchestrator: Main entry point for migrations
- qbo_client: QuickBooks Online API client
- data_transformer: Entity transformation (31 types)
- encryption: AES-256-GCM encryption
- verifier: Migration verification with Merkle trees
- security: Security utilities and pre-migration scan
- oauth_manager: OAuth 2.0 token management

Version: 3.2.0
"""

__version__ = "3.2.0"
__author__ = "QBMigration Team"

# Expose main classes for convenient imports
from .orchestrator import MigrationOrchestrator
from .encryption import EncryptionManager
from .security import SecurityManager, SecurityError
from .config import (
    ENVIRONMENT,
    REGION,
    BASE_URL,
    sanitize_migration_id,
    validate_production_access,
)

__all__ = [
    "MigrationOrchestrator",
    "EncryptionManager",
    "SecurityManager",
    "SecurityError",
    "ENVIRONMENT",
    "REGION",
    "BASE_URL",
    "sanitize_migration_id",
    "validate_production_access",
    "__version__",
]

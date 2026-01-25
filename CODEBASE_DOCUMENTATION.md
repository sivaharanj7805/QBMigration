# ForensicBridge - Complete Codebase Documentation

**Version:** 1.0
**Last Updated:** January 25, 2026
**License:** Proprietary (ForensicBridge Inc.)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Design](#2-architecture--design)
3. [Complete Code Inventory](#3-complete-code-inventory)
4. [Functionality Breakdown](#4-functionality-breakdown)
5. [Code Deep Dive](#5-code-deep-dive)
6. [Data Structures & Models](#6-data-structures--models)
7. [External Integrations](#7-external-integrations)
8. [Configuration & Setup](#8-configuration--setup)
9. [Build & Deployment](#9-build--deployment)
10. [Running the Application](#10-running-the-application)
11. [Testing](#11-testing)
12. [Security](#12-security)
13. [Performance](#13-performance)
14. [Error Handling & Logging](#14-error-handling--logging)
15. [API Documentation](#15-api-documentation)
16. [Database](#16-database)
17. [Monitoring & Observability](#17-monitoring--observability)
18. [Maintenance & Troubleshooting](#18-maintenance--troubleshooting)
19. [Development Workflow](#19-development-workflow)
20. [Dependencies Analysis](#20-dependencies-analysis)
21. [Glossary](#21-glossary)
22. [Appendices](#22-appendices)

---

## 1. Project Overview

### 1.1 Name and Purpose

**ForensicBridge** is an enterprise-grade QuickBooks Desktop to QuickBooks Online migration platform designed specifically for accounting firms and CPAs. The platform provides forensic-grade data integrity verification throughout the migration process, ensuring penny-perfect accuracy with cryptographic audit trails.

### 1.2 Problem Statement

Accounting firms face significant challenges when migrating client data from QuickBooks Desktop to QuickBooks Online:

1. **Data Integrity Risks**: Traditional migration tools cannot guarantee data accuracy
2. **Audit Trail Gaps**: No cryptographic verification of migrated data
3. **Compliance Requirements**: CPAs need verifiable proof of accurate migration
4. **Scale Limitations**: Manual migrations are time-consuming and error-prone
5. **Security Concerns**: Sensitive financial data requires enterprise-grade protection

ForensicBridge solves these problems by providing:
- SHA-256 cryptographic hashing of all migrated data
- Real-time trial balance reconciliation
- Forensic audit certificates for CPA sign-off
- Zero data footprint architecture (data auto-deletes after migration)
- Support for both QBO migration and Caseware audit bundle export

### 1.3 Target Audience

- **Primary**: Certified Public Accountants (CPAs) and accounting firms
- **Secondary**: Chartered Professional Accountants (Canada)
- **Tertiary**: Enterprise finance departments

### 1.4 Project History

- **January 2026**: Initial release v1.0
- Developed by ForensicBridge Inc., headquartered in Ontario, Canada

### 1.5 License

Proprietary software licensed under ForensicBridge EULA. See `AcquisitionDocuments/EULA.md` for complete terms.

**License Tiers:**
| Tier | Migrations/Month | Transaction Limit | Price |
|------|------------------|-------------------|-------|
| Starter | 5 | 5,000 | $497 |
| Business | 25 | 25,000 | $997 |
| Professional | 50 | 100,000 | $1,997 |
| Enterprise | Unlimited | 500,000 | $3,997 |
| Forensic | Unlimited | Unlimited | $7,997 |

### 1.6 Current Status

Production-ready with all 47 audit issues resolved (100/100 audit score).

---

## 2. Architecture & Design

### 2.1 System Architecture

ForensicBridge employs a distributed, microservices-inspired architecture with four main components:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ForensicBridge Architecture                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │   QBDesktop     │     │   QBMigration   │     │   QBMigration   │       │
│  │    Reader       │────▶│     Server      │────▶│    Service      │       │
│  │   (C#/.NET)     │     │  (Python/Flask) │     │   (Python)      │       │
│  └─────────────────┘     └────────┬────────┘     └────────┬────────┘       │
│         │                         │                       │                 │
│         │                         │                       │                 │
│         ▼                         ▼                       ▼                 │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │  QuickBooks     │     │   PostgreSQL    │     │  QuickBooks     │       │
│  │   Desktop       │     │   + Redis       │     │    Online       │       │
│  │    (SDK)        │     │                 │     │    (API)        │       │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘       │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │              ForensicBridge Dashboard (Next.js/React)            │       │
│  │                     https://app.forensicbridge.ca                │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                        AWS Infrastructure                        │       │
│  │    S3 │ EC2 │ RDS │ ElastiCache │ WAF │ CloudWatch │ Secrets    │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Overview

#### 2.2.1 QBDesktopReader (Windows/.NET)
- **Language**: C# (.NET Framework)
- **Purpose**: Extract data from QuickBooks Desktop company files
- **Key Features**:
  - QuickBooks SDK integration
  - AES-256-GCM encryption
  - SHA-256 forensic hashing
  - Streaming pipeline for large files
  - HMAC-SHA256 authentication

#### 2.2.2 QBMigrationServer (Python/Flask)
- **Language**: Python 3.9+
- **Framework**: Flask with SQLAlchemy ORM
- **Purpose**: REST API backend, user management, migration orchestration
- **Key Features**:
  - JWT authentication
  - Stripe payment integration
  - AWS resource management
  - WebSocket real-time updates
  - Rate limiting with Flask-Limiter

#### 2.2.3 QBMigrationService (Python)
- **Language**: Python 3.9+
- **Purpose**: Core migration logic, QBO API client, data transformation
- **Key Features**:
  - Premium QBO API client with rate limiting
  - Thread-safe batch processing
  - Data transformation and mapping
  - Caseware export functionality
  - Forensic validation

#### 2.2.4 ForensicBridge Dashboard (Next.js/React)
- **Language**: TypeScript
- **Framework**: Next.js 14 with React 18
- **Purpose**: Web-based user interface
- **Key Features**:
  - Real-time migration progress (Pizza Tracker)
  - Reconciliation Shield visualization
  - Audit certificate downloads
  - Drag-and-drop file upload
  - Responsive design with Tailwind CSS

### 2.3 Design Patterns

| Pattern | Usage | Location |
|---------|-------|----------|
| **Singleton** | API client instances | `api.ts`, `qbo_client.py` |
| **Factory** | Migration credit creation | `migration_credit.py` |
| **Observer** | Real-time status updates | WebSocket handlers |
| **Strategy** | Export formats (QBO/Caseware) | `caseware_exporter.py` |
| **Chain of Responsibility** | Request validation | Flask middleware |
| **Repository** | Database access | SQLAlchemy models |
| **Builder** | EC2 instance configuration | `aws_manager.py` |
| **Template Method** | Migration phases | `orchestrator.py` |

### 2.4 Data Flow

```
1. EXTRACTION PHASE
   QuickBooks Desktop → QBDesktopReader
   └── Connect via QB SDK
   └── Extract entities (Customers, Vendors, Invoices, etc.)
   └── Compute SHA-256 hashes per entity
   └── Encrypt with AES-256-GCM
   └── Generate encryption metadata

2. UPLOAD PHASE
   QBDesktopReader → AWS S3 (via QBMigrationServer)
   └── Chunked upload (5MB chunks)
   └── Server-side encryption (SSE-AES256)
   └── Store encryption metadata separately

3. PROCESSING PHASE
   AWS EC2 (ephemeral) → QBMigrationService
   └── Download encrypted data from S3
   └── Retrieve credentials from Secrets Manager
   └── Decrypt with AES-256-GCM
   └── Transform data for QBO format
   └── Batch upload to QuickBooks Online API

4. VERIFICATION PHASE
   QBMigrationService → QBMigrationServer
   └── Compute destination hashes
   └── Compare source vs destination
   └── Generate trial balance reconciliation
   └── Create forensic audit certificate

5. CLEANUP PHASE
   AWS → Zero Data Footprint
   └── Delete S3 objects
   └── Terminate EC2 instance
   └── Purge Secrets Manager credentials
   └── 24-hour lifecycle policy fallback
```

### 2.5 Technology Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Frontend** | Next.js | 14.x |
| **Frontend** | React | 18.x |
| **Frontend** | TypeScript | 5.x |
| **Frontend** | Tailwind CSS | 3.x |
| **Frontend** | TanStack Query | 5.x |
| **Frontend** | Zod | 3.x |
| **Backend API** | Python | 3.9+ |
| **Backend API** | Flask | 2.x |
| **Backend API** | SQLAlchemy | 2.x |
| **Backend API** | Flask-Login | 0.6.x |
| **Backend API** | Flask-Limiter | 3.x |
| **Migration Service** | Python | 3.9+ |
| **Migration Service** | boto3 | 1.x |
| **Migration Service** | cryptography | 41.x |
| **Desktop Client** | C# | .NET Framework 4.8 |
| **Desktop Client** | QuickBooks SDK | 15.x |
| **Database** | PostgreSQL | 14+ |
| **Cache** | Redis | 7.x |
| **Cloud** | AWS | - |
| **Payments** | Stripe | - |

---

## 3. Complete Code Inventory

### 3.1 Directory Structure

```
QBMigration/
├── QBDesktopReader/           # C# Windows application
│   ├── Program.cs             # Entry point
│   ├── QBDataExtractor.cs     # Core extraction logic
│   ├── Models.cs              # Data models
│   ├── EncryptionManager.cs   # AES-256-GCM encryption
│   ├── ForensicHashingService.cs  # SHA-256 hashing
│   ├── QBSessionManager.cs    # QuickBooks SDK session
│   ├── StreamingPipeline.cs   # Large file handling
│   └── README.md              # Component documentation
│
├── QBMigrationServer/         # Python Flask API server
│   ├── app.py                 # Flask application factory
│   ├── run.py                 # Development server runner
│   ├── config.py              # Configuration classes
│   ├── extensions.py          # Flask extensions
│   ├── tasks.py               # Celery task definitions
│   ├── api/                   # API blueprints
│   │   ├── __init__.py
│   │   ├── auth.py            # Authentication endpoints
│   │   ├── migrations.py      # Migration CRUD
│   │   ├── dashboard_api.py   # Dashboard data
│   │   ├── upload.py          # File upload handling
│   │   ├── payments.py        # Stripe integration
│   │   ├── qbo.py             # QBO OAuth flow
│   │   ├── webhooks.py        # Webhook receivers
│   │   ├── health.py          # Health check endpoints
│   │   └── legal.py           # Legal document endpoints
│   ├── models/                # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── database.py        # Database connection
│   │   ├── user.py            # User model
│   │   ├── migration.py       # Migration model
│   │   ├── migration_credit.py # Credit/billing model
│   │   ├── license.py         # License model
│   │   └── project.py         # Project model
│   ├── utils/                 # Utility modules
│   │   ├── __init__.py
│   │   ├── aws_manager.py     # AWS operations
│   │   ├── auth.py            # Auth utilities
│   │   ├── validators.py      # Input validation
│   │   ├── error_sanitizer.py # Error message sanitization
│   │   ├── secrets_manager.py # AWS Secrets Manager
│   │   └── notifications.py   # Email notifications
│   ├── workers/               # Background workers
│   │   ├── __init__.py
│   │   └── migration_worker.py
│   └── tests/                 # Test suite
│       ├── conftest.py
│       ├── test_basic.py
│       ├── test_complete.py
│       └── test_dashboard_api.py
│
├── QBMigrationService/        # Python migration engine
│   ├── main.py                # Service entry point
│   ├── config.py              # Configuration
│   ├── qbo_client.py          # Premium QBO API client
│   ├── data_transformer.py    # Data transformation
│   ├── orchestrator.py        # Migration orchestration
│   ├── encryption.py          # Encryption utilities
│   ├── verifier.py            # Data verification
│   ├── caseware_exporter.py   # Caseware bundle export
│   ├── models.py              # Data models
│   ├── schemas.py             # Pydantic schemas
│   ├── exceptions.py          # Custom exceptions
│   ├── audit_logger.py        # Audit logging
│   └── tests/                 # Test suite
│       ├── test_qbo_client.py
│       ├── test_integration.py
│       └── test_e2e_flow.py
│
├── forensicbridge-dashboard/  # Next.js frontend
│   ├── package.json           # Dependencies
│   ├── next.config.js         # Next.js configuration
│   ├── tailwind.config.js     # Tailwind configuration
│   ├── tsconfig.json          # TypeScript config
│   ├── src/
│   │   ├── app/               # App router pages
│   │   │   ├── layout.tsx     # Root layout
│   │   │   ├── page.tsx       # Landing page
│   │   │   └── (dashboard)/   # Dashboard routes
│   │   │       ├── page.tsx   # Dashboard home
│   │   │       └── migrations/
│   │   │           ├── page.tsx
│   │   │           └── [id]/page.tsx
│   │   ├── components/        # React components
│   │   │   ├── dashboard/
│   │   │   │   ├── PizzaTracker.tsx
│   │   │   │   ├── ReconciliationShield.tsx
│   │   │   │   ├── AuditCertCard.tsx
│   │   │   │   └── ForensicIntegrityPulse.tsx
│   │   │   └── ui/            # Shared UI components
│   │   └── lib/               # Utilities
│   │       ├── api.ts         # API client
│   │       ├── schemas.ts     # Zod schemas
│   │       └── hooks/         # React hooks
│   └── public/                # Static assets
│
├── aws/                       # AWS infrastructure
│   ├── cloudformation.yaml    # CloudFormation template
│   └── lambda/
│       └── s3_trigger.py      # S3 event handler
│
├── shared/                    # Shared utilities
│   ├── __init__.py
│   ├── api_version.py         # API versioning
│   ├── error_codes.py         # Error code constants
│   └── logging_config.py      # Logging configuration
│
├── AcquisitionDocuments/      # Legal/business docs
│   ├── EULA.md                # End User License Agreement
│   └── Technical_Whitepaper.md
│
└── tests/                     # Integration tests
    ├── test_full_system.py
    └── run_all_tests.py
```

### 3.2 File Count by Type

| Extension | Count | Purpose |
|-----------|-------|---------|
| `.py` | 85+ | Python source files |
| `.cs` | 7 | C# source files |
| `.tsx` | 20+ | React TypeScript components |
| `.ts` | 10+ | TypeScript utilities |
| `.yaml/.yml` | 5 | Configuration files |
| `.json` | 10+ | Package/config files |
| `.md` | 5+ | Documentation |

### 3.3 Environment Variables

#### QBMigrationServer (.env)
```bash
# Flask Configuration
FLASK_ENV=production
SECRET_KEY=<32-byte-hex-secret>
JWT_SECRET_KEY=<32-byte-hex-secret>

# Database
DATABASE_URL=postgresql://user:pass@host:5432/forensicbridge
REDIS_URL=redis://host:6379/0

# AWS Configuration
AWS_REGION=ca-central-1
AWS_S3_BUCKET=forensicbridge-migrations
AWS_EC2_AMI_ID=ami-xxxxxxxxx
AWS_EC2_INSTANCE_TYPE=t3.medium
AWS_IAM_INSTANCE_PROFILE=ForensicBridgeWorker

# Stripe
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# QuickBooks OAuth
QBO_CLIENT_ID=ABxxxxxxx
QBO_CLIENT_SECRET=xxxxxxxx
QBO_REDIRECT_URI=https://api.forensicbridge.ca/api/qbo/callback

# Security
WEBHOOK_SECRET=<32-byte-hex-secret>
ENCRYPTION_KEY=<32-byte-hex-key>
```

#### forensicbridge-dashboard (.env.local)
```bash
NEXT_PUBLIC_API_URL=https://api.forensicbridge.ca
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_xxx
```

---

## 4. Functionality Breakdown

### 4.1 Core Features

#### 4.1.1 Data Extraction (QBDesktopReader)
- Connect to QuickBooks Desktop via SDK
- Extract all entity types:
  - Customers
  - Vendors
  - Items (Inventory, Service, Non-Inventory)
  - Accounts (Chart of Accounts)
  - Invoices
  - Bills
  - Payments
  - Journal Entries
  - Estimates
  - Purchase Orders
  - Sales Orders
- Compute SHA-256 hash per entity
- Encrypt data with AES-256-GCM
- Stream large files in chunks

#### 4.1.2 Migration Processing (QBMigrationService)
- Decrypt uploaded data
- Transform QB Desktop format → QBO format
- Handle field mapping differences
- Batch upload to QBO API (50-100 entities/batch)
- Retry failed entities with exponential backoff
- Track SyncToken for updates
- Generate destination hashes

#### 4.1.3 Verification & Reconciliation
- Compare source vs destination hashes
- Trial balance reconciliation
- Penny-perfect accuracy verification
- Generate forensic audit certificate (PDF)
- Discrepancy detection and reporting

#### 4.1.4 Caseware Export Mode
- Alternative to QBO migration
- Export standardized audit bundle:
  - GL_Transactions.csv
  - Trial_Balance.csv
  - Chart_of_Accounts.csv
  - Entity_Mappings.json
- Compatible with Caseware Working Papers

### 4.2 API Endpoints

#### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | User registration |
| POST | `/api/auth/login` | User login |
| POST | `/api/auth/logout` | User logout |
| GET | `/api/auth/me` | Get current user |
| POST | `/api/auth/refresh` | Refresh JWT token |

#### Migrations
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/migrations` | List user migrations |
| GET | `/api/migrations/:id` | Get migration details |
| GET | `/api/migrations/:id/status` | Get migration status |
| GET | `/api/migrations/:id/live-status` | Real-time status |
| POST | `/api/migrations/:id/start` | Start migration |
| POST | `/api/migrations/:id/cancel` | Cancel migration |
| POST | `/api/migrations/:id/retry` | Retry failed migration |
| DELETE | `/api/migrations/:id` | Delete migration |

#### Verification
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/migrations/:id/trial-balance` | Get trial balance |
| GET | `/api/migrations/:id/audit-certificate` | Download certificate |
| GET | `/api/migrations/:id/audit-certificate/preview` | Preview certificate |

#### Upload
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload/initiate` | Start upload session |
| POST | `/api/upload/chunk` | Upload file chunk |
| POST | `/api/upload/complete` | Finalize upload |

#### Payments
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/payments/create-checkout-session` | Create Stripe session |
| POST | `/api/payments/webhook` | Stripe webhook |
| GET | `/api/payments/credits` | Get user credits |

### 4.3 CLI Commands

#### QBDesktopReader
```bash
# Basic extraction
QBDesktopReader.exe --company "Company.QBW" --output "encrypted_data.bin"

# With specific entities
QBDesktopReader.exe --company "Company.QBW" --entities "Customers,Invoices,Payments"

# Upload to server
QBDesktopReader.exe --company "Company.QBW" --upload --server "https://api.forensicbridge.ca"
```

#### QBMigrationService
```bash
# Run migration worker
python main.py --migration-id "abc123" --encrypted-data "data.bin" --credentials "creds.json"

# Generate Caseware bundle
python caseware_exporter.py --migration-id "abc123" --output "caseware_bundle.zip"
```

### 4.4 Business Logic

#### Credit System
1. Users purchase migration credits by tier
2. Each tier has a transaction limit
3. Credits are consumed when migration completes
4. Best-fit algorithm selects smallest suitable credit
5. Unused credits never expire

#### Migration Workflow
1. **Upload**: User uploads encrypted QB file
2. **Validate**: Server validates file format and size
3. **Store**: File stored in S3 with encryption
4. **Provision**: EC2 instance created for processing
5. **Process**: Migration service transforms and uploads data
6. **Verify**: Trial balance reconciliation
7. **Cleanup**: All data deleted (zero footprint)

---

## 5. Code Deep Dive

### 5.1 QBDesktopReader

#### Program.cs (Entry Point)
```csharp
// Main entry point for the desktop reader
// Initializes QuickBooks SDK connection
// Orchestrates extraction, encryption, and upload
```

Key responsibilities:
- Parse command line arguments
- Initialize QB SDK session
- Coordinate extraction pipeline
- Handle errors and cleanup

#### QBDataExtractor.cs
Core extraction logic:
- `ExtractCustomers()` - Pull customer list
- `ExtractInvoices()` - Pull invoices with line items
- `ExtractAccounts()` - Pull chart of accounts
- Uses QB SDK IQueryMsg for efficient queries
- Implements pagination for large datasets

#### EncryptionManager.cs
```csharp
// AES-256-GCM encryption implementation
public class EncryptionManager
{
    // Key derivation from user password
    public byte[] DeriveKey(string password, byte[] salt);

    // Encrypt data with authenticated encryption
    public EncryptedPackage Encrypt(byte[] data, byte[] key);

    // Generate secure random IV
    private byte[] GenerateIV();
}
```

#### ForensicHashingService.cs
```csharp
// SHA-256 hashing for forensic verification
public class ForensicHashingService
{
    // Hash individual entity
    public string HashEntity(object entity);

    // Compute Merkle root for batch
    public string ComputeMerkleRoot(List<string> hashes);

    // Generate chain-of-custody record
    public ChainOfCustodyRecord CreateRecord(string hash, DateTime timestamp);
}
```

### 5.2 QBMigrationServer

#### app.py (Flask Application Factory)
```python
def create_app(config_class=None):
    """Create and configure Flask application"""
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config_class or Config)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(migrations_bp)
    app.register_blueprint(dashboard_bp)

    return app
```

#### api/migrations.py
Key functions:

```python
@migrations_bp.route('/api/migrations', methods=['GET'])
@login_required
def list_migrations():
    """
    List migrations with pagination and filtering.

    Security:
    - SQL injection prevention via regex validation
    - Status filter whitelist validation
    - User-scoped queries only
    """

@migrations_bp.route('/api/migrations/<migration_id>/start', methods=['POST'])
@login_required
def start_migration(migration_id):
    """
    Start migration on ephemeral AWS instance.

    Steps:
    1. Validate migration status
    2. Check migration credits
    3. Store QBO credentials in Secrets Manager
    4. Create EC2 instance
    5. Update migration status
    """
```

#### utils/aws_manager.py
```python
class AWSMigrationManager:
    """
    Manage ephemeral AWS instances for migrations.

    Features:
    - S3 file storage with encryption
    - EC2 instance provisioning
    - Secrets Manager integration
    - CloudWatch metrics
    - Zero data footprint cleanup
    """

    def create_ec2_instance(self, migration_id, s3_uri, qbo_credentials, webhook_secret):
        """Create ephemeral EC2 instance with user data script"""

    def cleanup_migration(self, migration_id, instance_id=None):
        """Complete cleanup: S3, EC2, Secrets Manager"""
```

### 5.3 QBMigrationService

#### qbo_client.py (Premium QBO Client)
```python
class PremiumQBOClient:
    """
    Thread-safe QuickBooks Online API client.

    Features:
    - Rate limiting (500 req/min default)
    - Batch processing with parallel workers
    - SyncToken management for updates
    - Automatic retry with exponential backoff
    - SQLite state tracking for recovery
    """

    def batch_create_parallel(self, entity_type, entities):
        """
        Create entities in parallel batches.

        Args:
            entity_type: QBO entity type (Customer, Invoice, etc.)
            entities: List of entity dictionaries

        Returns:
            BatchResult with successes and failures
        """

    def query(self, query_string, max_results=1000):
        """
        Execute QBO query with automatic pagination.

        Args:
            query_string: QBO query (e.g., "SELECT * FROM Customer")
            max_results: Maximum results to return
        """
```

#### data_transformer.py
```python
class DataTransformer:
    """
    Transform QuickBooks Desktop data to QBO format.

    Handles:
    - Field name mapping
    - Data type conversions
    - Reference resolution
    - Validation against QBO rules
    """

    def transform_customer(self, qbd_customer):
        """Transform QB Desktop customer to QBO format"""

    def transform_invoice(self, qbd_invoice, customer_map, item_map):
        """Transform invoice with line item resolution"""
```

### 5.4 ForensicBridge Dashboard

#### src/lib/api.ts
```typescript
class ApiClient {
    private baseUrl: string;
    private token: string | null = null;
    private timeout: number;

    /**
     * Make authenticated API request with schema validation.
     *
     * Security:
     * - Zod schema validation prevents XSS
     * - Request timeout prevents hanging
     * - AbortController for cancellation
     */
    private async request<T>(
        endpoint: string,
        options: RequestInit = {},
        schema?: z.ZodSchema<T>
    ): Promise<ApiResponse<T>>
}
```

#### src/lib/schemas.ts
```typescript
// Zod schemas for runtime API validation

export const MigrationStatusSchema = z.object({
    migration_id: z.string(),
    status: z.enum(['pending', 'uploading', 'uploaded', 'provisioning',
                    'processing', 'completed', 'failed', 'cancelled']),
    progress_percent: z.number().min(0).max(100),
    current_step: z.string(),
    // ... additional fields
});

export const TrialBalanceSchema = z.object({
    source_trial_balance: z.number().optional().nullable(),
    destination_trial_balance: z.number().optional().nullable(),
    discrepancy: z.number().optional().nullable(),
    is_balanced: z.boolean().optional().nullable(),
    forensic_status: z.enum(['VERIFIED', 'DISCREPANCY_DETECTED', 'PENDING', 'NOT_AVAILABLE']),
});
```

#### src/app/(dashboard)/migrations/[id]/page.tsx
Key components:
- **PizzaTracker**: 5-phase visual progress indicator
- **ReconciliationShield**: Large green ✓ or red ⚠ for balance status
- **AuditCertCard**: Download audit certificate
- **CasewareBundleCard**: Download Caseware export
- **ForensicIntegrityPulse**: Terminal-style rolling log
- **DiscrepancyDoctor**: Interactive variance drill-down

---

## 6. Data Structures & Models

### 6.1 Database Models

#### User Model
```python
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    company_name = db.Column(db.String(255))

    # QBO OAuth tokens
    qbo_access_token = db.Column(db.Text)
    qbo_refresh_token = db.Column(db.Text)
    qbo_realm_id = db.Column(db.String(50))
    qbo_token_expires_at = db.Column(db.DateTime)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    # Relationships
    migrations = db.relationship('Migration', backref='user', lazy='dynamic')
    migration_credits = db.relationship('MigrationCredit', backref='user', lazy='dynamic')
```

#### Migration Model
```python
class Migration(db.Model):
    __tablename__ = 'migrations'

    id = db.Column(db.Integer, primary_key=True)
    migration_id = db.Column(db.String(36), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Status tracking
    status = db.Column(db.String(50), default='pending')
    progress_percent = db.Column(db.Integer, default=0)
    current_step = db.Column(db.String(100))

    # File information
    company_name = db.Column(db.String(255))
    qb_file_name = db.Column(db.String(255))
    file_size = db.Column(db.BigInteger)
    s3_uri = db.Column(db.String(500))

    # AWS tracking
    aws_instance_id = db.Column(db.String(50))

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    # Statistics
    total_transactions = db.Column(db.Integer)
    total_records = db.Column(db.Integer)

    # Forensic verification
    source_hash = db.Column(db.String(64))
    destination_hash = db.Column(db.String(64))
    trial_balance_verified = db.Column(db.Boolean, default=False)
```

#### MigrationCredit Model
```python
class MigrationCredit(db.Model):
    __tablename__ = 'migration_credits'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Credit tier
    tier_type = db.Column(db.String(50), nullable=False)  # starter, business, professional, enterprise, forensic
    transaction_limit = db.Column(db.Integer, nullable=False)
    price_cents = db.Column(db.Integer, nullable=False)

    # Stripe verification
    stripe_checkout_session_id = db.Column(db.String(255))
    stripe_payment_intent_id = db.Column(db.String(255))
    payment_status = db.Column(db.String(50), default='pending')

    # Usage
    status = db.Column(db.String(50), default='pending')  # pending, available, used, expired
    migration_id = db.Column(db.String(36))
    transactions_used = db.Column(db.Integer, default=0)

    TIER_CONFIG = {
        'starter': {'price_cents': 49700, 'transaction_limit': 5000},
        'business': {'price_cents': 99700, 'transaction_limit': 25000},
        'professional': {'price_cents': 199700, 'transaction_limit': 100000},
        'enterprise': {'price_cents': 399700, 'transaction_limit': 500000},
        'forensic': {'price_cents': 799700, 'transaction_limit': -1},  # Unlimited
    }
```

### 6.2 API Schemas (Zod)

```typescript
// Dashboard overview
export const DashboardOverviewSchema = z.object({
    overview: z.object({
        total_migrations: z.number().int().nonnegative(),
        completed_migrations: z.number().int().nonnegative(),
        failed_migrations: z.number().int().nonnegative(),
        in_progress: z.number().int().nonnegative(),
        success_rate: z.number().min(0).max(100),
        avg_duration_minutes: z.number().nonnegative(),
    }),
});

// User info
export const UserInfoSchema = z.object({
    id: z.number().int().positive(),
    email: z.string().email(),
    first_name: z.string(),
    last_name: z.string(),
    company_name: z.string().optional(),
    tier: z.string(),
    migrations_remaining: z.number().int().nonnegative(),
});
```

### 6.3 QBO Entity Structures

```python
# Customer structure for QBO API
QBO_CUSTOMER = {
    "DisplayName": str,        # Required, unique
    "CompanyName": str,
    "GivenName": str,
    "FamilyName": str,
    "PrimaryEmailAddr": {"Address": str},
    "PrimaryPhone": {"FreeFormNumber": str},
    "BillAddr": {
        "Line1": str,
        "City": str,
        "CountrySubDivisionCode": str,
        "PostalCode": str,
    },
    "Balance": Decimal,
    "Active": bool,
}

# Invoice structure for QBO API
QBO_INVOICE = {
    "CustomerRef": {"value": str},  # Customer ID
    "Line": [
        {
            "DetailType": "SalesItemLineDetail",
            "Amount": Decimal,
            "SalesItemLineDetail": {
                "ItemRef": {"value": str},
                "Qty": int,
                "UnitPrice": Decimal,
            }
        }
    ],
    "DueDate": str,  # YYYY-MM-DD
    "TxnDate": str,
    "DocNumber": str,
}
```

---

## 7. External Integrations

### 7.1 QuickBooks Desktop SDK

**Connection Method**: COM interop via QuickBooks SDK 15.x

**Supported Versions**:
- QuickBooks Desktop Pro 2019+
- QuickBooks Desktop Premier 2019+
- QuickBooks Desktop Enterprise 19.0+

**Authentication**: Single-user or multi-user mode with application certificate

**API Operations**:
- Query requests (IQueryMsg)
- Add requests (IAddMsg)
- Mod requests (IModMsg)
- Delete requests (IDelMsg)

### 7.2 QuickBooks Online API

**API Version**: v3 (Minor version 65+)

**Authentication**: OAuth 2.0 with refresh tokens

**Base URL**: `https://quickbooks.api.intuit.com/v3/company/{realmId}`

**Rate Limits**:
- 500 requests/minute (default)
- 10 concurrent requests
- Batch limit: 30 entities/batch

**Supported Entities**:
- Customer, Vendor, Employee
- Account, Item, Class, Department
- Invoice, Bill, Payment, JournalEntry
- Estimate, SalesReceipt, CreditMemo

### 7.3 Stripe Payments

**Integration Type**: Stripe Checkout Sessions

**Supported Payment Methods**:
- Credit/Debit cards
- Canadian Interac (where available)

**Webhook Events**:
- `checkout.session.completed`
- `payment_intent.succeeded`
- `payment_intent.payment_failed`

### 7.4 AWS Services

| Service | Purpose | Configuration |
|---------|---------|---------------|
| **S3** | Encrypted file storage | SSE-AES256, lifecycle policies |
| **EC2** | Ephemeral processing instances | t3.medium, auto-terminate |
| **RDS** | PostgreSQL database | Multi-AZ, encrypted |
| **ElastiCache** | Redis cache | Encryption in-transit |
| **Secrets Manager** | QBO credentials storage | Auto-rotation |
| **CloudWatch** | Metrics and logging | Custom namespace |
| **WAF** | Web application firewall | Rate limiting |
| **KMS** | Customer-managed encryption keys | Key rotation |

---

## 8. Configuration & Setup

### 8.1 Development Environment Setup

#### Prerequisites
- Python 3.9+
- Node.js 18+
- PostgreSQL 14+
- Redis 7+
- .NET Framework 4.8 (Windows only)
- QuickBooks Desktop (for QBDesktopReader testing)

#### Backend Setup
```bash
# Clone repository
git clone https://github.com/forensicbridge/QBMigration.git
cd QBMigration

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r QBMigrationServer/requirements.txt
pip install -r QBMigrationService/requirements.txt

# Set up database
createdb forensicbridge
python QBMigrationServer/init_database.py

# Configure environment
cp QBMigrationServer/.env.example QBMigrationServer/.env
# Edit .env with your settings

# Run development server
python QBMigrationServer/run.py
```

#### Frontend Setup
```bash
cd forensicbridge-dashboard

# Install dependencies
npm install

# Configure environment
cp .env.example .env.local
# Edit .env.local

# Run development server
npm run dev
```

### 8.2 Production Configuration

#### Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FLASK_ENV` | Yes | - | `production` or `development` |
| `SECRET_KEY` | Yes | - | Flask session encryption key |
| `JWT_SECRET_KEY` | Yes | - | JWT token signing key |
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `REDIS_URL` | Yes | - | Redis connection string |
| `AWS_REGION` | Yes | `ca-central-1` | AWS region |
| `AWS_S3_BUCKET` | Yes | - | S3 bucket for migrations |
| `STRIPE_SECRET_KEY` | Yes | - | Stripe API key |
| `QBO_CLIENT_ID` | Yes | - | QuickBooks OAuth client ID |
| `QBO_CLIENT_SECRET` | Yes | - | QuickBooks OAuth client secret |

---

## 9. Build & Deployment

### 9.1 Build Process

#### Backend (Python)
```bash
# Install production dependencies
pip install -r requirements.txt --no-dev

# Run database migrations
flask db upgrade

# Verify configuration
python -c "from config import Config; Config.validate()"
```

#### Frontend (Next.js)
```bash
cd forensicbridge-dashboard

# Install dependencies
npm ci

# Build production bundle
npm run build

# Output in .next/ directory
```

#### Desktop Client (C#)
```bash
# Using MSBuild
msbuild QBDesktopReader/QBDesktopReader.csproj /p:Configuration=Release

# Output: QBDesktopReader/bin/Release/QBDesktopReader.exe
```

### 9.2 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Production Deployment                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  CloudFront (CDN)                                           │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Next.js Static  │    │   WAF Rules     │                │
│  │  (S3 + CF)      │    │  (Rate Limit)   │                │
│  └─────────────────┘    └────────┬────────┘                │
│                                  │                          │
│                                  ▼                          │
│                    ┌─────────────────────────┐              │
│                    │    Application Load     │              │
│                    │       Balancer          │              │
│                    └───────────┬─────────────┘              │
│                                │                            │
│         ┌──────────────────────┼──────────────────────┐    │
│         ▼                      ▼                      ▼    │
│  ┌─────────────┐       ┌─────────────┐       ┌───────────┐│
│  │  Flask API  │       │  Flask API  │       │ Flask API ││
│  │  (ECS/EC2)  │       │  (ECS/EC2)  │       │ (ECS/EC2) ││
│  └──────┬──────┘       └──────┬──────┘       └─────┬─────┘│
│         │                     │                    │       │
│         └──────────────┬──────┴────────────────────┘       │
│                        │                                    │
│         ┌──────────────┼──────────────┐                    │
│         ▼              ▼              ▼                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │    RDS     │ │   Redis    │ │     S3     │             │
│  │ PostgreSQL │ │ ElastiCache│ │  Storage   │             │
│  └────────────┘ └────────────┘ └────────────┘             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 9.3 AWS CloudFormation

The `aws/cloudformation.yaml` template provisions:

1. **VPC Infrastructure**
   - VPC with CIDR 10.0.0.0/16
   - 2 public subnets (NAT Gateway)
   - 2 private subnets (application tier)
   - Internet Gateway
   - Route tables

2. **Database Layer**
   - RDS PostgreSQL (db.t3.medium)
   - Multi-AZ deployment
   - Encrypted storage (KMS)
   - Automated backups (7 days)

3. **Cache Layer**
   - ElastiCache Redis (cache.t3.small)
   - Encryption in-transit
   - Single node (can scale to cluster)

4. **Application Layer**
   - Application Load Balancer
   - Target groups with health checks
   - Auto Scaling group (optional)

5. **Security**
   - WAF Web ACL
   - Rate limiting rules (2000 req/5min general, 100 req/5min auth)
   - Security groups with least privilege
   - KMS customer-managed key

---

## 10. Running the Application

### 10.1 Development Mode

#### Start All Services
```bash
# Terminal 1: Backend API
cd QBMigrationServer
source ../venv/bin/activate
python run.py

# Terminal 2: Celery Worker (optional)
celery -A tasks worker --loglevel=info

# Terminal 3: Frontend
cd forensicbridge-dashboard
npm run dev

# Terminal 4: Redis (if not using Docker)
redis-server
```

#### Using Docker Compose
```bash
docker-compose up -d
```

### 10.2 Production Mode

#### With Gunicorn
```bash
cd QBMigrationServer
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

#### With systemd
```ini
# /etc/systemd/system/forensicbridge.service
[Unit]
Description=ForensicBridge API Server
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/forensicbridge/QBMigrationServer
Environment="PATH=/opt/forensicbridge/venv/bin"
ExecStart=/opt/forensicbridge/venv/bin/gunicorn -w 4 -b unix:/tmp/forensicbridge.sock "app:create_app()"

[Install]
WantedBy=multi-user.target
```

### 10.3 Health Checks

```bash
# API health check
curl https://api.forensicbridge.ca/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2026-01-25T10:00:00Z",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "aws": "ok"
  }
}
```

---

## 11. Testing

### 11.1 Test Structure

```
tests/
├── unit/
│   ├── test_models.py
│   ├── test_validators.py
│   └── test_transformers.py
├── integration/
│   ├── test_api_endpoints.py
│   ├── test_qbo_client.py
│   └── test_aws_manager.py
├── e2e/
│   ├── test_full_migration.py
│   └── test_user_journey.py
└── fixtures/
    ├── sample_qb_data.json
    └── mock_responses.json
```

### 11.2 Running Tests

```bash
# All tests
python -m pytest

# With coverage
python -m pytest --cov=QBMigrationServer --cov-report=html

# Specific test file
python -m pytest QBMigrationServer/tests/test_dashboard_api.py

# Specific test
python -m pytest -k "test_list_migrations"

# Verbose output
python -m pytest -v
```

### 11.3 Test Categories

| Category | Files | Purpose |
|----------|-------|---------|
| Unit | `test_basic.py` | Model and utility tests |
| Integration | `test_dashboard_api.py` | API endpoint tests |
| E2E | `test_e2e_flow.py` | Full workflow tests |
| Performance | `test_concurrent_uploads.py` | Load testing |
| Security | `test_license.py` | License validation |

### 11.4 CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest --cov
```

---

## 12. Security

### 12.1 Authentication & Authorization

#### JWT Token Authentication
- Access tokens: 15 minute expiry
- Refresh tokens: 7 day expiry
- Secure HttpOnly cookies
- CSRF protection

#### Password Security
- Argon2id hashing (memory-hard)
- Minimum 12 characters
- Complexity requirements enforced
- Breached password checking

### 12.2 Data Encryption

| Layer | Method | Key Management |
|-------|--------|----------------|
| In Transit | TLS 1.3 | AWS ACM |
| At Rest (S3) | AES-256-GCM | AWS KMS (CMK) |
| At Rest (RDS) | AES-256 | AWS KMS |
| Client Data | AES-256-GCM | User-derived key |

### 12.3 Input Validation

```python
# SQL injection prevention (api/migrations.py:15-57)
def validate_pagination_param(value, param_name, default, min_val, max_val):
    """
    Comprehensive SQL injection prevention.
    - Regex validation for pure integers
    - Range validation
    - Whitelist for status filters
    """
```

### 12.4 Security Headers

```python
# Flask security headers
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response
```

### 12.5 Rate Limiting

```python
# Flask-Limiter configuration
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Endpoint-specific limits
@limiter.limit("5 per minute")  # Login attempts
@limiter.limit("10 per minute")  # API calls
```

### 12.6 Secrets Management

- AWS Secrets Manager for QBO credentials
- AWS Systems Manager Parameter Store for webhook secrets
- No hardcoded credentials in code
- Automatic secret rotation

### 12.7 Zero Data Footprint

1. S3 objects deleted after processing
2. EC2 instances self-terminate
3. Secrets Manager entries purged
4. 24-hour lifecycle policy as fallback
5. Shred command for secure deletion

---

## 13. Performance

### 13.1 Optimization Strategies

#### Database
- Connection pooling (SQLAlchemy)
- Query optimization with indexes
- N+1 query prevention
- Read replicas for reporting

#### API
- Response caching (Redis)
- Pagination for large datasets
- Async operations where applicable
- CDN for static assets

#### QBO API
- Batch operations (30 entities/batch)
- Parallel workers (2-8 based on plan)
- Rate limit compliance
- Retry with exponential backoff

### 13.2 Benchmarks

| Operation | Target | Actual |
|-----------|--------|--------|
| API Response (p95) | <200ms | ~150ms |
| File Upload (100MB) | <60s | ~45s |
| Customer Migration (1000) | <5min | ~3min |
| Full Migration (10K txns) | <30min | ~20min |

### 13.3 Scaling Considerations

- Horizontal scaling via ALB + Auto Scaling
- Database read replicas
- Redis cluster mode
- S3 transfer acceleration
- CloudFront for global CDN

---

## 14. Error Handling & Logging

### 14.1 Error Handling Strategy

```python
# Custom exception hierarchy
class ForensicBridgeException(Exception):
    """Base exception for all ForensicBridge errors"""

class MigrationError(ForensicBridgeException):
    """Migration-specific errors"""

class QBOAPIError(ForensicBridgeException):
    """QuickBooks Online API errors"""

class EncryptionError(ForensicBridgeException):
    """Encryption/decryption errors"""
```

### 14.2 Error Sanitization

```python
# utils/error_sanitizer.py
def sanitize_error_message(error: Exception) -> str:
    """
    Remove sensitive information from error messages.

    Sanitizes:
    - API keys
    - Database credentials
    - File paths
    - Email addresses
    """
```

### 14.3 Logging Configuration

```python
# shared/logging_config.py
LOGGING_CONFIG = {
    'version': 1,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
        'json': {
            'class': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/forensicbridge/app.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'json'
        }
    },
    'loggers': {
        '': {
            'handlers': ['console', 'file'],
            'level': 'INFO'
        }
    }
}
```

### 14.4 Audit Logging

```python
# QBMigrationService/audit_logger.py
class AuditLogger:
    """
    Forensic audit trail logging.

    Records:
    - User actions
    - Data access
    - Migration events
    - Verification results
    """

    def log_event(self, event_type, user_id, migration_id, details):
        """Log auditable event with timestamp and hash"""
```

---

## 15. API Documentation

### 15.1 Authentication

All API endpoints (except `/api/auth/login` and `/api/auth/register`) require authentication.

**Headers:**
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### 15.2 Response Format

**Success Response:**
```json
{
    "success": true,
    "data": { ... }
}
```

**Error Response:**
```json
{
    "success": false,
    "error": "Error message",
    "error_code": "ERROR_CODE"
}
```

### 15.3 Endpoint Reference

#### POST /api/auth/login
Authenticate user and receive JWT tokens.

**Request:**
```json
{
    "email": "user@example.com",
    "password": "secure_password"
}
```

**Response (200):**
```json
{
    "success": true,
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
        "id": 1,
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe"
    }
}
```

#### GET /api/migrations
List migrations for authenticated user.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| page | int | 1 | Page number |
| per_page | int | 50 | Items per page (max 100) |
| status | string | - | Filter by status |

**Response (200):**
```json
{
    "success": true,
    "migrations": [
        {
            "id": 1,
            "migration_id": "abc123",
            "status": "completed",
            "company_name": "Acme Corp",
            "progress_percent": 100,
            "created_at": "2026-01-25T10:00:00Z"
        }
    ],
    "pagination": {
        "page": 1,
        "per_page": 50,
        "total_pages": 1,
        "total_items": 1
    }
}
```

#### POST /api/migrations/:id/start
Start migration processing.

**Request:**
```json
{
    "qbo_credentials": {
        "client_id": "ABxxxxxxx",
        "client_secret": "xxxxxxxx",
        "refresh_token": "xxxxxxxx",
        "realm_id": "1234567890"
    }
}
```

**Response (200):**
```json
{
    "success": true,
    "migration_id": "abc123",
    "instance_id": "i-0123456789abcdef",
    "status": "processing",
    "message": "Migration started on AWS"
}
```

#### GET /api/migrations/:id/trial-balance
Get trial balance reconciliation.

**Response (200):**
```json
{
    "source_trial_balance": 125847.32,
    "destination_trial_balance": 125847.32,
    "discrepancy": 0,
    "is_balanced": true,
    "forensic_status": "VERIFIED",
    "verification_timestamp": "2026-01-25T10:30:00Z",
    "source_hash": "7e2f8a9c...",
    "destination_hash": "7e2f8a9c...",
    "hash_match": true
}
```

---

## 16. Database

### 16.1 Schema Diagram

```
┌─────────────────┐     ┌─────────────────────┐
│     users       │     │    migrations       │
├─────────────────┤     ├─────────────────────┤
│ id (PK)         │──┐  │ id (PK)             │
│ email           │  │  │ migration_id        │
│ password_hash   │  └──│ user_id (FK)        │
│ first_name      │     │ status              │
│ last_name       │     │ progress_percent    │
│ company_name    │     │ company_name        │
│ qbo_access_token│     │ s3_uri              │
│ qbo_refresh_tok │     │ created_at          │
│ qbo_realm_id    │     │ completed_at        │
│ created_at      │     └─────────────────────┘
└─────────────────┘              │
         │                       │
         │     ┌─────────────────┴───────┐
         │     │  migration_credits      │
         │     ├─────────────────────────┤
         └─────│ user_id (FK)            │
               │ tier_type               │
               │ transaction_limit       │
               │ stripe_session_id       │
               │ status                  │
               │ migration_id            │
               └─────────────────────────┘
```

### 16.2 Indexes

```sql
-- Performance indexes
CREATE INDEX idx_migrations_user_id ON migrations(user_id);
CREATE INDEX idx_migrations_status ON migrations(status);
CREATE INDEX idx_migrations_created_at ON migrations(created_at DESC);
CREATE INDEX idx_credits_user_status ON migration_credits(user_id, status);
```

### 16.3 Migrations

Using Flask-Migrate (Alembic):

```bash
# Create migration
flask db migrate -m "Add new column"

# Apply migration
flask db upgrade

# Rollback
flask db downgrade
```

---

## 17. Monitoring & Observability

### 17.1 CloudWatch Metrics

**Custom Namespace: QBMigrations**

| Metric | Unit | Description |
|--------|------|-------------|
| `S3Upload` | Count | Successful S3 uploads |
| `S3UploadFailure` | Count | Failed S3 uploads |
| `EC2InstanceCreated` | Count | EC2 instances launched |
| `EC2InstanceCreationFailure` | Count | EC2 launch failures |
| `MigrationCleanup` | Count | Completed cleanups |
| `S3FilesDeleted` | Count | S3 objects deleted |

### 17.2 CloudWatch Alarms

```yaml
# From cloudformation.yaml
HighCPUAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: forensicbridge-high-cpu
    MetricName: CPUUtilization
    Threshold: 80
    Period: 300
    EvaluationPeriods: 2

DBConnectionsAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: forensicbridge-db-connections
    MetricName: DatabaseConnections
    Threshold: 90
    Period: 300
```

### 17.3 Logging

**Log Groups:**
- `/aws/forensicbridge/api` - API server logs
- `/aws/forensicbridge/worker` - Migration worker logs
- `/aws/forensicbridge/errors` - Error logs

**Log Retention:** 30 days

### 17.4 Health Endpoints

```
GET /health          - Basic health check
GET /health/detailed - Detailed status with component checks
GET /health/ready    - Kubernetes readiness probe
GET /health/live     - Kubernetes liveness probe
```

---

## 18. Maintenance & Troubleshooting

### 18.1 Common Issues

#### Migration Stuck in "Processing"
```bash
# Check EC2 instance status
aws ec2 describe-instances --filters "Name=tag:MigrationId,Values=<migration_id>"

# Check CloudWatch logs
aws logs get-log-events --log-group-name /aws/forensicbridge/worker

# Manual cleanup
python -c "from utils.aws_manager import AWSMigrationManager; AWSMigrationManager().cleanup_migration('<migration_id>')"
```

#### Database Connection Issues
```bash
# Check connection pool
SELECT * FROM pg_stat_activity WHERE datname = 'forensicbridge';

# Reset connections
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'forensicbridge' AND state = 'idle';
```

#### S3 Upload Failures
```bash
# Check bucket policy
aws s3api get-bucket-policy --bucket forensicbridge-migrations

# Verify IAM permissions
aws iam simulate-principal-policy --policy-source-arn <role_arn> --action-names s3:PutObject
```

### 18.2 Backup & Recovery

**Database Backups:**
- Automated RDS snapshots (daily, 7-day retention)
- Point-in-time recovery enabled
- Cross-region replication (optional)

**Recovery Procedure:**
```bash
# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
    --db-instance-identifier forensicbridge-restored \
    --db-snapshot-identifier <snapshot_id>
```

### 18.3 Maintenance Tasks

| Task | Frequency | Command |
|------|-----------|---------|
| Database vacuum | Weekly | `VACUUM ANALYZE;` |
| Log rotation | Daily | Automatic (logrotate) |
| Certificate renewal | 90 days | Automatic (ACM) |
| Dependency updates | Monthly | `pip-audit`, `npm audit` |

---

## 19. Development Workflow

### 19.1 Git Branching Strategy

```
main (production)
  │
  └── develop (staging)
        │
        ├── feature/TICKET-123-description
        ├── bugfix/TICKET-456-description
        └── hotfix/TICKET-789-description
```

### 19.2 Code Style

**Python:**
- PEP 8 compliance
- Black formatter
- isort for imports
- Type hints required

**TypeScript:**
- ESLint with Airbnb config
- Prettier formatting
- Strict TypeScript mode

### 19.3 Commit Messages

```
type(scope): subject

body (optional)

footer (optional)

Types: feat, fix, docs, style, refactor, test, chore
```

### 19.4 Pull Request Process

1. Create feature branch
2. Write code with tests
3. Run linters and tests locally
4. Create PR with description
5. Code review (1 approval required)
6. CI/CD pipeline passes
7. Merge to develop
8. Deploy to staging
9. QA verification
10. Merge to main
11. Deploy to production

---

## 20. Dependencies Analysis

### 20.1 Python Dependencies (QBMigrationServer)

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| Flask | 2.x | Web framework | BSD-3 |
| SQLAlchemy | 2.x | ORM | MIT |
| Flask-Login | 0.6.x | Session management | MIT |
| Flask-Limiter | 3.x | Rate limiting | MIT |
| boto3 | 1.x | AWS SDK | Apache-2.0 |
| stripe | 5.x | Payment processing | MIT |
| gunicorn | 21.x | WSGI server | MIT |
| psycopg2 | 2.9.x | PostgreSQL driver | LGPL |
| redis | 4.x | Redis client | MIT |
| cryptography | 41.x | Encryption | Apache-2.0/BSD |

### 20.2 JavaScript Dependencies (Dashboard)

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| next | 14.x | React framework | MIT |
| react | 18.x | UI library | MIT |
| @tanstack/react-query | 5.x | Data fetching | MIT |
| zod | 3.x | Schema validation | MIT |
| tailwindcss | 3.x | CSS framework | MIT |
| lucide-react | 0.x | Icons | ISC |

### 20.3 Security Vulnerabilities

Run regular audits:
```bash
# Python
pip-audit

# JavaScript
npm audit
```

---

## 21. Glossary

| Term | Definition |
|------|------------|
| **AES-256-GCM** | Advanced Encryption Standard with 256-bit key and Galois/Counter Mode for authenticated encryption |
| **Chain of Custody** | Documented trail of who handled data and when, ensuring forensic integrity |
| **Ephemeral Instance** | Temporary EC2 instance that auto-terminates after task completion |
| **Forensic Hash** | SHA-256 cryptographic hash used to verify data integrity |
| **HMAC** | Hash-based Message Authentication Code for verifying message authenticity |
| **Merkle Root** | Single hash representing all hashes in a tree structure |
| **OAuth 2.0** | Authorization framework used by QuickBooks Online API |
| **Pizza Tracker** | Visual progress indicator showing migration phases |
| **QBD** | QuickBooks Desktop |
| **QBO** | QuickBooks Online |
| **Realm ID** | Unique identifier for a QuickBooks Online company |
| **Reconciliation Shield** | Visual indicator showing trial balance match status |
| **SyncToken** | QBO version control token to prevent concurrent modifications |
| **Trial Balance** | Sum of all debits and credits, should equal zero |
| **Zero Data Footprint** | Architecture ensuring no customer data persists after processing |

---

## 22. Appendices

### Appendix A: Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_INVALID_CREDENTIALS` | 401 | Invalid email or password |
| `AUTH_TOKEN_EXPIRED` | 401 | JWT token has expired |
| `MIGRATION_NOT_FOUND` | 404 | Migration ID does not exist |
| `MIGRATION_INVALID_STATE` | 400 | Migration cannot transition to requested state |
| `CREDIT_INSUFFICIENT` | 403 | No available migration credits |
| `CREDIT_LIMIT_EXCEEDED` | 403 | Transaction count exceeds credit limit |
| `QBO_API_ERROR` | 502 | QuickBooks Online API error |
| `QBO_RATE_LIMIT` | 429 | QBO rate limit exceeded |
| `ENCRYPTION_FAILED` | 500 | Data encryption/decryption error |
| `S3_UPLOAD_FAILED` | 500 | Failed to upload to S3 |
| `EC2_CREATE_ERROR` | 500 | Failed to create EC2 instance |

### Appendix B: Migration Status Flow

```
pending → uploading → uploaded → provisioning → processing → completed
                                      ↓                          ↓
                                   failed ←──────────────────────┘
                                      ↓
                                  cancelled
```

### Appendix C: QBO Entity Mapping

| QB Desktop Entity | QBO Entity | Notes |
|-------------------|------------|-------|
| Customer | Customer | Direct mapping |
| Vendor | Vendor | Direct mapping |
| Item | Item | Type conversion required |
| Account | Account | Classification mapping |
| Invoice | Invoice | Line item transformation |
| Bill | Bill | Vendor ref required |
| Payment | Payment | Customer ref required |
| JournalEntry | JournalEntry | Line detail required |
| Class | Class | Hierarchy preserved |
| Department | Department | QBO-specific |

### Appendix D: AWS Resource Tags

All AWS resources are tagged with:

| Tag Key | Value | Purpose |
|---------|-------|---------|
| `Project` | `ForensicBridge` | Cost allocation |
| `Environment` | `production`/`staging` | Environment identification |
| `ManagedBy` | `CloudFormation` | Resource management |
| `Owner` | `forensicbridge` | Ownership |

### Appendix E: Compliance

**Data Residency:** All processing occurs in Canadian data centers (AWS ca-central-1)

**Privacy Regulations:**
- PIPEDA compliant
- SOC 2 Type II (planned)
- Data breach notification within 72 hours

**Financial Standards:**
- Audit certificates do NOT constitute CPA opinion
- Designed for CPA review, not replacement

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-25 | ForensicBridge | Initial documentation |

---

*This documentation is proprietary and confidential. © 2026 ForensicBridge Inc. All rights reserved.*

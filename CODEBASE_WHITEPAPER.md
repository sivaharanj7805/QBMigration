# ForensicBridge Codebase Whitepaper

> **Comprehensive Technical Inventory**
> Generated: 2026-01-16

This document provides a complete inventory of the ForensicBridge application codebase, describing every file, its purpose, and its role in the overall system.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Root Level Files](#root-level-files)
3. [QBDesktopReader (C#)](#qbdesktopreader-c)
4. [QBMigrationLauncher (C# WPF)](#qbmigrationlauncher-c-wpf)
5. [QBMigrationServer (Python Flask)](#qbmigrationserver-python-flask)
6. [QBMigrationService (Python)](#qbmigrationservice-python)
7. [ForensicBridge Dashboard (Next.js)](#forensicbridge-dashboard-nextjs)
8. [AWS Infrastructure](#aws-infrastructure)

---

## System Overview

ForensicBridge is an enterprise-grade QuickBooks Desktop to QuickBooks Online migration platform with forensic-level data integrity verification. The system consists of five integrated components:

| Component | Technology | Purpose |
|:----------|:-----------|:--------|
| QBDesktopReader | C# (.NET) | Reads data directly from QuickBooks Desktop via QBXML SDK |
| QBMigrationLauncher | C# WPF | Desktop GUI for accountants to initiate migrations |
| QBMigrationServer | Python Flask | Central API server, job orchestration, and database |
| QBMigrationService | Python | Core migration engine that pushes data to QBO API |
| ForensicBridge Dashboard | Next.js/React | Web-based monitoring and management interface |

---

## Root Level Files

| File | Purpose |
|:-----|:--------|
| `.env` | Environment variables for all services (DB credentials, AWS keys, API secrets) |
| `.gitignore` | Specifies intentionally untracked files to ignore |
| `requirements.txt` | Global Python dependencies for the project |
| `run_all_tests.py` | Master test runner that executes all test suites across components |
| `test_full_system.py` | End-to-end integration test simulating complete migration flow |
| `test_s3.py` | Unit tests for AWS S3 upload functionality |
| `test_upload.json` | Sample JSON payload for testing file upload APIs |
| `aws.bat` | Windows batch script to quickly launch AWS CLI commands |
| `cookies.txt` | Browser cookies (development only, for authenticated testing) |

### Documentation Files

| File | Purpose |
|:-----|:--------|
| `BACKEND_TEST_REPORT.md` | Results of backend API and database testing |
| `CODEBASE_AUDIT.md` | Security and code quality audit findings |
| `COMPREHENSIVE_TESTING_REPORT.md` | Full testing coverage report across all components |
| `FINAL_PRODUCT_SPECS.md` | Final product specifications for release |
| `LAUNCH_CHECKLIST.md` | Pre-launch verification checklist |
| `PRE_BUILD_CHECKLIST.md` | 5-phase deployment guide for AWS infrastructure |
| `PRODUCTION_READINESS.md` | Production deployment documentation |
| `SALES_PITCH_25M_VALUATION.md` | Business case and valuation document |

---

## QBDesktopReader (C#)

**Location:** `QBDesktopReader/`
**Technology:** C# .NET 8.0
**Purpose:** Extracts data from QuickBooks Desktop company files (.QBW) using the official QBXML SDK.

### Core Extraction Engine

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `Program.cs` | Main entry point. Parses CLI arguments, initializes logging, orchestrates extraction. | Launches the entire extraction pipeline |
| `QBDataExtractor.cs` | Core extraction logic. Iterates through all QB entity types (Customers, Vendors, Items, Invoices, Bills, etc.) and extracts data. | Most critical file - handles all data retrieval |
| `QBSessionManager.cs` | Manages connection to QuickBooks Desktop. Handles session lifecycle, connection pooling, and error recovery. | Enables communication with QB Desktop application |
| `QBIteratorHelper.cs` | Helper for paginated queries. Handles large datasets that exceed QB's single-query limits. | Ensures complete data extraction for large files |
| `Models.cs` | Defines all data models (Customer, Vendor, Invoice, Bill, Item, etc.) that mirror QB's schema. | Data contract between extraction and migration |

### Security & Compliance

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `DataSanitizer.cs` | PII detection and redaction. Removes SSN, credit cards, phone numbers from data. | GDPR/CCPA compliance, prevents sensitive data leaks |
| `EncryptionManager.cs` | AES-256 encryption for data at rest and in transit. | Encrypts extracted data before upload |
| `LogRedactor.cs` | Sanitizes log files to prevent PII from appearing in logs. | Audit-safe logging |
| `ForensicHashingService.cs` | Computes SHA-256 hashes over canonical field ordering for deterministic integrity verification. | Enables hash-chain verification across the pipeline |
| `HashVerifier.cs` | Verifies computed hashes match before and after migration. | Proves data integrity |

### Data Pipeline

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `NDJSONWriter.cs` | Writes extracted data as Newline-Delimited JSON for streaming. | Enables memory-efficient processing of large files |
| `StreamingPipeline.cs` | Orchestrates the async streaming of data from QB through transformation to upload. | Non-blocking I/O for performance |
| `FileUploader.cs` | Handles chunked, resumable uploads to the server. | Reliable transfer of large datasets |
| `S3DirectUploader.cs` | Direct-to-S3 upload capability, bypassing server for large files. | Reduces server load, enables multi-GB uploads |
| `RecursiveTransactionLinker.cs` | Links parent-child relationships (e.g., Invoice to InvoiceLineItems). | Preserves relational integrity |

### Configuration & Resilience

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `ExtractionConfig.cs` | Runtime configuration including entity filters, batch sizes, timeouts. | Customizable extraction behavior |
| `ExtractionCheckpoint.cs` | Checkpoint management for resumable extractions after failures. | Enables recovery from crashes |
| `FieldLimits.cs` | Defines QBO field length limits to truncate oversized data. | Prevents QBO API rejections |
| `ProgressReporter.cs` | Reports extraction progress to the server via webhooks. | Enables real-time UI updates |

### Build & Deployment

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `QBDesktopReader.csproj` | MSBuild project file. Defines dependencies and build configuration. | Build artifact generation |
| `ForensicBridge.iss` | Inno Setup script for creating Windows installer. | Produces `ForensicBridge-Setup.exe` |
| `build.ps1` | PowerShell build automation script. | CI/CD integration |
| `config.json` | Development configuration. | Local testing |
| `config_production.json` | Production configuration with AWS endpoints. | Deployed configuration |
| `config_schema.json` | JSON Schema for config validation. | Prevents misconfigurations |
| `README.md` | Component documentation. | Developer reference |
| `UPDATE_v4.4.md` | Changelog for version 4.4. | Version history |

---

## QBMigrationLauncher (C# WPF)

**Location:** `QBMigrationLauncher/`
**Technology:** C# WPF (.NET)
**Purpose:** Windows desktop GUI for accountants. Provides drag-and-drop interface and migration monitoring.

### UI Layer

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `App.xaml` | Application-level resources and startup configuration. | WPF application bootstrap |
| `App.xaml.cs` | Application startup logic. | Entry point |
| `MainWindow.xaml` | Primary UI layout with file drop zone, progress indicators, status display. | Main user interface |
| `MainWindow.xaml.cs` | Code-behind for main window. | UI event handling |
| `BulkMigrationWindow.xaml` | UI for queueing multiple company files for batch migration. | Enterprise bulk processing |
| `BulkMigrationWindow.xaml.cs` | Code-behind for bulk migration. | Bulk queue management |
| `QBMigrationLauncher.csproj` | Project file. | Build configuration |

### Services Layer

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `Services/ExtractorRunner.cs` | Spawns QBDesktopReader as a subprocess. | Launches extraction process |
| `Services/LogParser.cs` | Parses extractor output for progress updates. | Real-time UI feedback |
| `Services/QuickBooksDetector.cs` | Detects installed QuickBooks versions. | Compatibility checking |
| `Services/HealthCheckService.cs` | Background health monitoring of server connectivity. | Connection status indicators |
| `Services/CertificateGenerator.cs` | Generates PDF audit certificates for completed migrations. | Compliance documentation |
| `Services/VarianceReportService.cs` | Generates variance reports comparing source vs destination. | Auditor deliverable |
| `Services/ActiveArchivalService.cs` | Interfaces with AWS Glacier for long-term archival. | Data retention compliance |
| `Services/BulkMigrationManager.cs` | Manages queue of pending migrations for batch processing. | Enterprise throughput |

### ViewModels

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `ViewModels/MainViewModel.cs` | MVVM ViewModel for main window data binding. | UI state management |
| `ViewModels/BulkMigrationViewModel.cs` | ViewModel for bulk migration queue. | Queue state management |

---

## QBMigrationServer (Python Flask)

**Location:** `QBMigrationServer/`
**Technology:** Python 3.11, Flask, SQLAlchemy
**Purpose:** Central API server. Handles authentication, file uploads, job orchestration, and database management.

### Core Application

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `app.py` | Flask application factory. Initializes logging, CORS, rate limiting, error handlers. | Server entry point |
| `run.py` | Development server runner. | Local development |
| `config.py` | Configuration classes for dev/staging/production environments. | Environment-specific settings |
| `extensions.py` | Flask extension initialization (rate limiter). | Shared extensions |

### API Blueprints (`api/`)

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `auth.py` | Authentication endpoints (login, register, logout, password reset). | User access control |
| `upload.py` | File upload handling with multipart support. | Receives .QBW files |
| `s3_upload.py` | Direct-to-S3 presigned URL generation. | Scalable file storage |
| `migrations.py` | Migration CRUD, status, start/stop/retry endpoints plus **forensic endpoints** (live-status, trial-balance, audit-certificate). | Core migration API |
| `dashboard_api.py` | Dashboard overview, statistics, recent activity feeds. | UI data aggregation |
| `projects.py` | Project (company file) management. | File organization |
| `webhooks.py` | Incoming webhook handlers from EC2 instances reporting progress. | Real-time updates |
| `webhook_delivery_log.py` | Webhook delivery tracking and retry logic. | Reliability |
| `websocket.py` | WebSocket support for real-time push notifications. | Live UI updates |
| `health.py` | Health check endpoints for load balancers. | Infrastructure monitoring |
| `health_check.py` | Detailed health diagnostics. | Debugging |
| `sso_provider.py` | SSO/SAML integration for enterprise clients. | Enterprise auth |
| `EncryptionManager.py` | Server-side encryption utilities. | Data security |
| `file_upload.py` | Additional file upload utilities. | Upload support |

### Database Models (`models/`)

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `database.py` | SQLAlchemy initialization. | ORM setup |
| `user.py` | User model with Argon2 password hashing, account lockout, email verification. | Authentication |
| `migration.py` | Migration model with status tracking, cost estimation, cleanup tracking, **forensic data storage** (trial_balance_data, live_status_data). | Core data model |
| `project.py` | Project model for organizing company files. | Organization |

### Utilities (`utils/`)

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `aws_manager.py` | AWS SDK wrapper for EC2, S3, SQS operations. | Cloud infrastructure |
| `enterprise_aws.py` | Enterprise-scale AWS operations (bulk provisioning). | High-volume processing |
| `backup.py` | Database backup to S3 with encryption. | Disaster recovery |
| `cleanup_scheduler.py` | Scheduled cleanup of expired migrations and orphaned resources. | Resource hygiene |
| `forensic_archival.py` | Glacier archival for long-term compliance storage. | Data retention |
| `notifications.py` | Email/SMS notification service. | Alerting |
| `validators.py` | Input validation helpers. | Security |
| `auth.py` | Authentication utilities. | Token handling |

### Static & Templates

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `templates/` | Jinja2 HTML templates for email notifications and web pages. | Email content |
| `static/` | Static assets (CSS, images). | Branding |

### Database & Migrations

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `migrate_to_postgres.py` | SQLite to PostgreSQL migration script. | Production database |
| `migrations_setup.py` | Flask-Migrate initialization. | Schema versioning |
| `requirements.txt` | Python dependencies. | Package management |

---

## QBMigrationService (Python)

**Location:** `QBMigrationService/`
**Technology:** Python 3.11
**Purpose:** Core migration engine. Transforms QB Desktop data to QBO format and pushes via Intuit API.

### Core Engine

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `main.py` | Entry point. Orchestrates the full migration workflow. | Migration execution |
| `orchestrator.py` | High-level workflow coordination (extract → transform → load → verify). | Pipeline control |
| `data_transformer.py` | Transforms QB Desktop entities to QBO format with field mapping. | Data conversion |
| `qbo_client.py` | QuickBooks Online API client with batch operations, retry logic, rate limiting. | QBO integration |
| `oauth_manager.py` | OAuth 2.0 token management with automatic refresh. | API authentication |
| `verifier.py` | Post-migration verification. Compares source vs destination, generates variance reports. | Integrity proof |

### Compliance & Auditing

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `audit_logger.py` | Comprehensive audit trail logging. | Compliance |
| `caseware_exporter.py` | Exports data in CaseWare-compatible format for auditors. | Auditor integration |
| `health_check_pdf.py` | Generates Health Check PDF reports. | Client deliverable |
| `variance_report.py` | Detailed variance analysis between source and destination. | Discrepancy identification |

### Security

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `encryption.py` | Data encryption/decryption utilities. | Data protection |
| `security.py` | Security utilities (hashing, token validation). | Defense in depth |
| `kms_manager.py` | AWS KMS integration for key management. | Enterprise key management |

### Data Handling

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `iif_parser.py` | Parses QuickBooks IIF export files. | Legacy format support |
| `models.py` | Data models matching QBO schema. | Type definitions |
| `schemas.py` | Pydantic schemas for validation. | Data validation |
| `exceptions.py` | Custom exception classes. | Error handling |
| `config.py` | Service configuration. | Runtime settings |

### Enterprise Features

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `archive_portal.py` | Active Archival web portal for data retrieval. | Historical access |
| `data_retention.py` | Data retention policy enforcement. | Compliance |
| `whitelabel.py` | White-label customization for enterprise clients. | Branding |

### Testing

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `test_integration.py` | Integration tests for the migration service. | Quality assurance |
| `tests/test_qbo_client.py` | Unit tests for QBO API client. | API reliability |
| `tests/test_e2e_flow.py` | End-to-end migration flow tests. | Full workflow validation |
| `tests/test_concurrent_uploads.py` | Concurrent upload stress tests. | Performance |
| `tests/test_master_e2e.py` | Master E2E test suite. | Comprehensive testing |

---

## ForensicBridge Dashboard (Next.js)

**Location:** `forensicbridge-dashboard/`
**Technology:** Next.js 16, React 19, TypeScript, Tailwind CSS
**Purpose:** Web-based monitoring and management interface for accountants and administrators.

### Application Core (`src/app/`)

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `layout.tsx` | Root layout with HTML structure, metadata, font loading. | Page wrapper |
| `globals.css` | Global CSS with design system tokens, card styles, buttons. | Visual styling |
| `providers.tsx` | React Query provider for data fetching. | State management |
| `favicon.ico` | Application icon. | Branding |

### Dashboard Pages (`src/app/(dashboard)/`)

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `layout.tsx` | Dashboard layout with sidebar and header. | Navigation shell |
| `page.tsx` | Main dashboard with drag-drop upload, stats, recent migrations. | Home page |
| `migrations/page.tsx` | Migration list with search, filter, status. | Migration management |
| `migrations/[id]/page.tsx` | Migration detail with Pizza Tracker, Trial Balance, Certificate. | Individual migration view |
| `upload/page.tsx` | Dedicated file upload page. | File submission |
| `projects/page.tsx` | Company files list. | File organization |
| `projects/new/page.tsx` | New project creation form. | Project setup |
| `reports/page.tsx` | Report generation (Variance, Health Check, Audit Cert). | Auditor tools |
| `vault/page.tsx` | Data Museum / Active Archival interface. | Historical data |
| `settings/page.tsx` | User and application settings. | Configuration |

### Authentication Pages (`src/app/(auth)/`)

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `login/page.tsx` | User login form. | Authentication |
| `register/page.tsx` | User registration form. | Onboarding |

### Components (`src/components/`)

#### Dashboard Components

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `dashboard/PizzaTracker.tsx` | 5-phase visual progress bar for migration. | Status visualization |
| `dashboard/ReconciliationShield.tsx` | Trial balance comparison with hash verification. | Integrity proof |
| `dashboard/AuditCertCard.tsx` | CPA audit certificate download card. | Compliance deliverable |
| `dashboard/CasewareBundleCard.tsx` | CaseWare export bundle download. | Auditor deliverable |
| `dashboard/ForensicIntegrityPulse.tsx` | Terminal-style rolling log of integrity events. | Real-time monitoring |
| `dashboard/ForensicFeed.tsx` | Activity feed of recent events. | Event history |
| `dashboard/DiscrepancyDoctor.tsx` | Drill-down discrepancy analysis. | Error investigation |

#### Migration Components

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `migrations/MigrationsTable.tsx` | Reusable migrations data table. | List display |
| `migrations/DiscrepancyDoctor.tsx` | Account-level variance drill-down. | Detailed analysis |

#### Layout Components

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `layout/Sidebar.tsx` | Collapsible navigation sidebar. | Navigation |

#### Settings Components

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `settings/WhitelabelCard.tsx` | Enterprise branding customization. | White-label |

### Library (`src/lib/`)

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `api.ts` | API client for all backend communication. | Data fetching |
| `auth.ts` | Authentication utilities. | Session handling |
| `hooks/useLiveStatus.ts` | React Query hook for live migration status. | Real-time updates |
| `hooks/useTrialBalance.ts` | Hook for trial balance data. | Financial data |
| `hooks/useMigrations.ts` | Hook for migrations list. | List data |
| `hooks/useDashboard.ts` | Hook for dashboard overview. | Aggregate data |

### Configuration

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `package.json` | NPM dependencies and scripts. | Package management |
| `tsconfig.json` | TypeScript configuration. | Type checking |
| `next.config.ts` | Next.js configuration. | Framework settings |
| `postcss.config.mjs` | PostCSS configuration for Tailwind. | CSS processing |
| `eslint.config.mjs` | ESLint configuration. | Code quality |
| `vitest.config.ts` | Vitest test runner configuration. | Testing |

---

## AWS Infrastructure

**Location:** `aws/`
**Purpose:** Infrastructure-as-Code for AWS deployment.

| File | Purpose | System Impact |
|:-----|:--------|:--------------|
| `cloudformation.yaml` | AWS CloudFormation template defining VPC, EC2, RDS, S3, ALB, IAM. | One-click deployment |
| `README.md` | Infrastructure documentation. | Deployment guide |
| `lambda/` | Lambda function code for serverless operations. | Event-driven processing |

---

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ACCOUNTANT'S WORKSTATION                          │
│  ┌─────────────────────┐     ┌─────────────────────────────────────────┐   │
│  │  QBMigrationLauncher │────▶│  QBDesktopReader (C#)                   │   │
│  │  (WPF GUI)           │     │  - Extracts from .QBW                   │   │
│  └─────────────────────┘     │  - Computes SHA-256 hashes              │   │
│                               │  - Uploads to S3                        │   │
│                               └────────────────┬────────────────────────┘   │
└────────────────────────────────────────────────┼────────────────────────────┘
                                                 │ HTTPS
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS CLOUD                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  QBMigrationServer (Flask)                                           │   │
│  │  - API Gateway                                                       │   │
│  │  - Job Orchestration                                                 │   │
│  │  - PostgreSQL Database                                               │   │
│  └─────────────────────┬───────────────────────────────────────────────┘   │
│                        │                                                     │
│                        ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  QBMigrationService (Python)                                         │   │
│  │  - Runs on ephemeral EC2                                             │   │
│  │  - Transforms data                                                   │   │
│  │  - Pushes to QBO API                                                 │   │
│  │  - Reports progress via webhooks                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       QUICKBOOKS ONLINE (INTUIT)                             │
│  - Receives migrated data                                                    │
│  - OAuth 2.0 authenticated                                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                       FORENSICBRIDGE DASHBOARD (Web)                         │
│  - Real-time migration monitoring                                            │
│  - Trial balance verification                                                │
│  - Audit certificate generation                                              │
│  - CaseWare bundle export                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## File Count Summary

| Component | Files | Lines of Code (Est.) |
|:----------|------:|---------------------:|
| QBDesktopReader | 27 | ~15,000 |
| QBMigrationLauncher | 17 | ~3,000 |
| QBMigrationServer | 40+ | ~8,000 |
| QBMigrationService | 29 | ~12,000 |
| ForensicBridge Dashboard | 35+ | ~6,000 |
| AWS Infrastructure | 3 | ~500 |
| Root Tests & Docs | 17 | ~2,000 |
| **TOTAL** | **168+** | **~46,500** |

---

*This document is auto-generated from the ForensicBridge codebase as of 2026-01-16.*

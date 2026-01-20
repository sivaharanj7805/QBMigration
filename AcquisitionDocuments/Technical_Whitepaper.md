FORENSICBRIDGE
Technical Whitepaper
Cryptographically Verified Financial Data Migration
QuickBooks Desktop to QuickBooks Online & Caseware Working Papers

Version 4.3
January 2026
www.forensicbridge.ca
 
Executive Summary
ForensicBridge is an enterprise-grade data migration platform that transforms QuickBooks Desktop (.QBW) data into QuickBooks Online with cryptographic verification and forensic audit trails. The system also supports Caseware export mode for generating audit-ready CSV files compatible with Caseware Working Papers and OnPoint DAS.
Unlike traditional ETL (Extract, Transform, Load) tools that prioritize speed over integrity, ForensicBridge implements a Forensic Trust Chain that maintains a continuous, cryptographically verifiable chain of custody from the source QuickBooks Desktop file to the destination ledger.

Key Differentiators
Capability	Traditional Tools	ForensicBridge
Data Verification	None	SHA-256 per-record hashing
Trial Balance Check	Manual reconciliation	Automated variance analysis
Encryption	Transit only (TLS)	AES-256-GCM at rest and in transit
Audit Certificate	Not available	Court-admissible PDF generation
PII Protection	Basic or none	Automatic SSN/CC/phone redaction
Compliance Alignment	Limited	SOC 2, HIPAA, PCI-DSS ready

Dual Destination Support
ForensicBridge supports two distinct output modes, selectable at runtime:
Mode	Destination	Output Format
Primary: QBO Mode	QuickBooks Online	Direct API push via QBO REST API v65
Secondary: Caseware Mode	Caseware Working Papers / OnPoint DAS	Audit_TB.csv, Audit_GL.csv, Audit_Mapping.cvw
 
Technical Architecture
ForensicBridge employs a hybrid architecture combining a Windows desktop client for QuickBooks extraction with a cloud-based transformation and verification backend.

System Components
Component	Technology	Purpose
QBDesktopReader	C# .NET 6.0 + QBFC16 SDK	Direct COM integration with QuickBooks Desktop; extracts 55 entity types
QBMigrationServer	Python Flask + PostgreSQL	REST API, user management, file handling, job orchestration
QBMigrationService	Python + QBO API v65	Data transformation, QBO push, verification, Caseware export
Dashboard	Next.js (React) + TypeScript	Real-time WebSocket-driven monitoring and controls
Cloud Infrastructure	AWS (S3, CloudWatch, WAF, KMS)	Storage, logging, security, encryption key management

Codebase Metrics
Metric	Value
Total Source Files	107 files (.cs, .py, .tsx, .ts, .js)
QBDesktopReader	22 C# files
QBMigrationLauncher	15 C# files
QBMigrationServer	~35 Python files
QBMigrationService	~20 Python files
forensicbridge-dashboard	~15 TypeScript/React files

Data Flow Pipeline
The migration process follows a four-phase pipeline, each with distinct security and verification checkpoints:
Phase	Name	Description
1	Secure Extraction	QBFC16 SDK extracts 55 entity types; SHA-256 hash computed per record; PII sanitized; data encrypted with AES-256-GCM
2	Encrypted Transit	Chunked upload (10MB segments) to S3 via TLS 1.3; integrity verified on receipt
3	Multi-Core Transformation	Parallel entity conversion; linked transaction reconstruction; 31 entity types mapped to QBO schema
4	Forensic Certification	Hash re-verification; trial balance reconciliation; PDF audit certificate generation
 
Entity Type Coverage
ForensicBridge extracts 55 distinct entity types from QuickBooks Desktop. Of these, 31 are transformable to QuickBooks Online (QBO supports fewer entity types than Desktop).
Count	Context	Source
55 entity types	Extracted from QuickBooks Desktop	QBDataExtractor.cs
31 entity types	Transformable to QuickBooks Online	data_transformer.py

Lists (25 Entity Types)
Accounts, Customers, Vendors, Employees, Leads, OtherNames, Items, Classes, PaymentMethods, Terms, SalesTaxCodes, CustomerTypes, VendorTypes, JobTypes, Currencies, CustomerMessages, DateDrivenTerms, InventorySites, PayrollItemWages, PayrollItemNonWages, WorkersCompCodes, PriceLevels, SalesReps, ShipMethods, SalesTaxGroups
Transactions (30 Entity Types)
Invoices, SalesReceipts, Estimates, PurchaseOrders, SalesOrders, Bills, BillPayments (Check/CC), VendorCredits, ReceivePayments, ARRefundCreditCards, Checks, JournalEntries, SalesTaxPayments, CreditCardCharges, CreditCardCredits, Charges, CreditMemos, Deposits, InventoryAdjustments, ItemReceipts, BuildAssemblies, Transfers, InventoryTransfers, Preferences, DataExtensions, DeletedRecords, ReportVerification, CompanyActivity

Lead Sheet Code Mapping (Caseware Mode)
44 pre-mapped Lead Sheet codes support standard, agricultural, and manufacturing chart of accounts:
Category	Count	Code Range	Examples
Standard Assets	7	A1-A5, A3.1-A3.2	Bank, AR, OCA, Fixed Assets
Agricultural	8	A6.1-A6.8	Livestock, Crops, Farm Equipment, Breeding Stock
Manufacturing	8	A7.1-A7.8	Raw Materials, WIP, Finished Goods, Tooling
Other Industries	5	A8.1-A8.5	Construction in Progress, Oil & Gas
Liabilities	8	L1-L4.2	AP, Credit Card, Payroll, Mortgage
Equity	5	E1-E5	Equity, Retained Earnings, Partner Capital
Revenue	3	R1-R2	Sales, Service Income, Contract Revenue
 
Security Architecture
Encryption Standards
Algorithm	Usage	Specification
AES-256-GCM	Data encryption at rest and in transit	256-bit key, 96-bit IV, authenticated encryption
SHA-256	Forensic integrity hashing	Per-record cryptographic fingerprint
Argon2id	Password hashing	Memory-hard, resistant to GPU attacks
PBKDF2	Key derivation	100,000 iterations minimum
AWS KMS	Customer-managed key support	Envelope encryption with CMK

Data Persistence Model
ForensicBridge implements a tiered persistence model that balances operational requirements with zero-trust security principles:
Component	Database	Persistence	Content
QBMigrationServer	PostgreSQL	Persistent	User accounts, migration metadata, audit logs (no financial data)
QBMigrationService	SQLite (temp)	Session only	QBD-to-QBO ID mappings; deleted after run completion
Flight Data	None	Zero persistence	Raw financial transactions streamed and discarded immediately
Critical distinction: Actual financial data (invoices, bills, payments) is encrypted, transmitted, processed, and immediately discarded. Only metadata and audit trails are persisted.

PII Sanitization
Automatic detection and redaction occurs before data leaves the extraction environment:
PII Type	Detection Pattern	Action
Social Security Numbers	XXX-XX-XXXX format	Full redaction
Credit Card Numbers	13-19 digit sequences (Luhn validated)	Mask to last 4 digits only
Phone Numbers	Various North American formats	E.164 normalization
Email Addresses	RFC 5322 compliant patterns	Validation and sanitization

Data Residency
Canadian data residency (AWS ca-central-1, Montreal) is enforced by default for enterprise deployments:
Setting	Default	Configurable
AWS Region	ca-central-1 (Montreal)	Yes, via AWS_REGION env var
S3 Bucket Region	ca-central-1	Enforced for Enterprise tier
RDS Region	ca-central-1	Enforced for Enterprise tier
 
Forensic Verification System
Per-Record SHA-256 Hashing
Every transaction extracted from QuickBooks Desktop receives a per-record SHA-256 integrity hash computed using canonical field ordering. This creates an immutable cryptographic fingerprint that can be verified post-migration.
Hash Verification Process
1.	C# client computes hash during extraction (ForensicHashingService.cs)
2.	Hash stored alongside encrypted data in upload bundle
3.	Python service re-computes hash after decryption (encryption.py)
4.	Mismatch triggers hard abort with forensic alert

Hashed Transaction Types (14 Types)
Invoice, Bill, ReceivePayment, BillPaymentCheck, CreditMemo, JournalEntry, Check, Deposit, SalesReceipt, PurchaseOrder, SalesOrder, Estimate, VendorCredit, Transfer

Trial Balance Reconciliation Shield
Automated verification that Total Debits equals Total Credits after migration, with drill-down capability to identify specific account variances down to the penny.
•	Penny-Perfect Match: Compares QuickBooks Desktop trial balance against extracted data
•	Visual Trust Badge: Real-time "Balanced" or "Discrepancy" indicator
•	Variance Shield: Verifies bank reconciliation status preservation

Discrepancy Doctor
When variances are detected, the Discrepancy Doctor provides interactive drill-down analysis:
•	Interactive drill-down with expandable rows per account
•	Account-level variance display (Source vs. Destination balances)
•	Severity indicators (Critical/Warning/Info)
•	Possible cause suggestions with per-discrepancy analysis

Audit Certificate Generation
Court-admissible PDF certificate generated upon successful migration. Certificate includes entity modification counts, cryptographic hash signatures, timestamped digital signature, operator identity, and trial balance verification results.
 
Performance Specifications
Processing Time Benchmarks
Processing time varies based on file size, transaction complexity, network conditions, and QBO API rate limits:
File Size	Transaction Count	Estimated Time	Use Case
< 50 MB	< 10,000	3-5 minutes	Typical small business
50-200 MB	10,000-50,000	5-15 minutes	Small CPA firm client
200-500 MB	50,000-150,000	15-30 minutes	Medium business
500 MB - 1 GB	150,000-300,000	30-60 minutes	Large business
1-2.4 GB	300,000-500,000+	45-90 minutes	Enterprise client

Performance Factors
•	Network upload speed (chunked upload at approximately 10MB/s)
•	QBO API rate limits (plan-dependent: 2-8 concurrent workers)
•	Number of linked transactions (invoices linked to payments)
•	Entity complexity (line items per transaction)

Resilience Features
•	Checkpoint Resumability: Checkpoints saved every 1,000 records; survives crashes and network interruptions
•	Incremental Sync: Only extracts records modified since last sync for weekly/monthly refresh operations
•	Stream-based Processing: NDJSON streaming handles large files that crash competing tools
 
Enterprise Features
Bulk Migration Manager
Status: IMPLEMENTED
Queue-based system for processing multiple company files simultaneously, designed for CPA firms migrating 50+ client files:
•	Queue-based processing with EnqueueFile() and EnqueueFiles() methods
•	Background processing with StartProcessingAsync()
•	Progress events (JobStarted, JobCompleted, JobFailed)
•	Summary report generation with GenerateSummaryReport()

White-Label Portal
Status: IMPLEMENTED
Complete rebranding capability allows firms to present ForensicBridge as their proprietary technology:
•	Custom subdomain support (migrations.firmname.com)
•	Logo upload and color scheme customization via CSS variables
•	License key management (STARTER/PROFESSIONAL/ENTERPRISE tiers)
•	Reseller portal for multi-firm deployments

Active Archival (Data Museum)
Status: IMPLEMENTED
Long-term queryable archive transforms legacy QuickBooks files into compliance-ready storage:
•	Flask web portal with API key authentication
•	Full-text transaction search with date, amount, and type filters
•	Complete audit log of all archive access
•	AWS Glacier integration for cold storage economics

Customer-Managed Keys (CMK)
Status: IMPLEMENTED
Enterprise clients can bring their own AWS KMS encryption keys:
•	Zero-knowledge architecture: client holds only decryption capability
•	Envelope encryption: data keys encrypted by customer CMK
•	Automatic annual key rotation support
•	Fallback local mode for non-AWS deployments

SSO/SAML Integration
Status: IMPLEMENTED
Centralized identity management with major enterprise providers:
Provider	Protocol	Status
Microsoft Entra ID (Azure AD)	OAuth2 / SAML 2.0	Implemented
Google Workspace	OAuth2	Implemented
Okta	SAML 2.0 / OAuth2	Implemented
 
Deployment Options
ForensicBridge supports multiple deployment models to meet varying enterprise requirements:
Mode	Components	Database	Notes
SaaS	AWS CloudFormation	RDS PostgreSQL	Fully managed deployment
On-Premise	Single .exe installer	Embedded SQLite/PostgreSQL	Air-gapped option available
Hybrid	Desktop client + hosted backend	PostgreSQL	Typical enterprise setup

QuickBooks Desktop Version Support
QBFC16 SDK provides broad compatibility with QuickBooks Desktop versions:
Version Range	Status	Notes
QuickBooks Desktop 2016+	Native	Direct QBFC16 SDK support
QuickBooks Desktop 2015	Compatible	Via QBXML v13
QuickBooks Desktop 2010-2014	Legacy	Requires QBXML fallback
QuickBooks Pro/Premier/Enterprise	All editions	Full support
 
File Format Support
Format	Extension	Support Level	Notes
QuickBooks Company File	.QBW	Native	Direct QBFC16 SDK extraction
QuickBooks Backup	.QBB	Via Restore	Restore to .QBW first
QuickBooks Portable	.QBM	Via Restore	Restore to .QBW first
Intuit Interchange	.IIF	Full Parser	Alternative extraction method
Excel Export	.XLSX	Full	Accountant-friendly import
CSV Export	.CSV	Full	Universal compatibility
QBXML	v1-16	Full	All QB Desktop versions since 2000


Compliance Alignment
ForensicBridge is designed to support compliance with major regulatory frameworks:
Standard	Status	Relevant Features
SOC 2 Type II	Ready	Activity logging, access controls, audit trails
HIPAA	Ready	PHI encryption, PII redaction, audit trails
PCI-DSS	Ready	Payment data handling, credit card masking
GDPR / CCPA	Ready	PII sanitization, data deletion capabilities
ISO 27001	Ready	Information security management controls
CRA IC05-1R1	Ready	Canadian record-keeping requirements (6 years)
IRS Rev. Proc. 98-25	Ready	US record-keeping requirements (7 years)
 
Quality Assurance
Test Coverage
The following metrics represent test pass rates (not line coverage):
Component	Pass Rate	Test Results	Notes
QBMigrationService	92.4%	85/92 tests passed	7 tests require attention
QBMigrationServer Auth	100%	10/10 tests passed	Full coverage
QBMigrationServer Basic	100%	4/4 tests passed	Health/status endpoints
ForensicBridge Dashboard	100%	46/46 tests passed	All components tested

Total Tests: 152  |  Passing: 145 (95.4% overall pass rate)


Conclusion
ForensicBridge represents a fundamental shift from "data migration" to "forensic data transport." By implementing cryptographic verification at every step, automated trial balance reconciliation, and court-ready audit certificates, ForensicBridge enables CPA firms to offer premium migration services with documented proof of data integrity.
The platform addresses the critical market window created by Intuit's QuickBooks Desktop discontinuation, providing audit firms with a defensible, enterprise-ready solution for the largest forced migration event in accounting software history.


For technical support or enterprise licensing inquiries:
www.forensicbridge.ca
support@forensicbridge.ca


This whitepaper documents ForensicBridge version 4.3.
All specifications verified against source code. Generated January 2026.

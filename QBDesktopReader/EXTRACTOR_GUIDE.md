# QBExtractor v4.4 - Complete Guide

## Overview

QBExtractor is a robust, enterprise-grade tool for extracting data from QuickBooks Desktop for migration to cloud accounting systems. Version 4.4 introduces **multi-backend support** with automatic fallback, making it nearly impossible to fail due to missing dependencies.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      QBExtractor.exe                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────────────────────────────────┐ │
│  │   Program   │───▶│         IQBDataProvider                 │ │
│  │    (CLI)    │    │  (Abstraction Layer)                    │ │
│  └─────────────┘    └─────────────────────────────────────────┘ │
│                              │                                   │
│              ┌───────────────┼───────────────┐                  │
│              ▼               ▼               ▼                  │
│     ┌────────────────┐ ┌────────────────┐                       │
│     │ QBFCDataProvider│ │QODBCDataProvider│                      │
│     │   (Primary)    │ │   (Fallback)   │                       │
│     └────────────────┘ └────────────────┘                       │
│              │               │                                   │
│              ▼               ▼                                   │
│     ┌────────────────┐ ┌────────────────┐                       │
│     │ QBDataExtractor │ │  ODBC Driver   │                       │
│     │  (Existing)    │ │   (QODBC)      │                       │
│     └────────────────┘ └────────────────┘                       │
│              │               │                                   │
│              ▼               ▼                                   │
│     ┌────────────────┐ ┌────────────────┐                       │
│     │   QBFC16 SDK   │ │ QuickBooks DB  │                       │
│     │    (COM)       │ │   via ODBC     │                       │
│     └────────────────┘ └────────────────┘                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Why It Won't Fail

### 1. Multiple Extraction Backends

The extractor has **two independent ways** to access QuickBooks data:

| Backend | Method | Pros | Cons |
|---------|--------|------|------|
| **QBFC** | Official SDK via COM | Most reliable, full features | Requires SDK installation |
| **QODBC** | ODBC driver | No SDK needed, SQL interface | Requires QODBC driver |

**Auto-Fallback Logic:**
```
1. Check if QBFC16 SDK is installed
   └─ YES → Use QBFC (best reliability)
   └─ NO  → Check if QODBC is installed
            └─ YES → Use QODBC (fallback)
            └─ NO  → Show clear installation instructions
```

### 2. Automatic Backend Detection

At startup, the extractor:
1. Scans the Windows registry for QBFC16 COM registration
2. Scans ODBC driver list for QODBC
3. Selects the best available backend
4. Falls back gracefully if primary fails

```csharp
// Simplified detection logic
var backends = QBDataProviderFactory.DetectAvailableBackends();
if (backends.Any(b => b.Available))
{
    // We can extract data!
    var provider = QBDataProviderFactory.CreateBestAvailableProvider();
}
```

### 3. Retry Logic with Exponential Backoff

Every operation has built-in retry:

```
Attempt 1 → Fail → Wait 1s
Attempt 2 → Fail → Wait 2s
Attempt 3 → Fail → Wait 4s
Attempt 4 → Success!
```

This handles:
- Transient network errors
- QuickBooks temporarily busy
- COM object initialization delays
- Database locks

### 4. Entity-Level Failure Isolation

If one entity fails, extraction continues:

```
✅ Accounts    - 150 records
✅ Customers   - 2,500 records
⚠️ Invoices    - FAILED (will retry)
✅ Vendors     - 800 records
✅ Bills       - 1,200 records
...
```

The extraction doesn't stop - it isolates failures and continues with other entities.

### 5. Checkpointing & Resume

For long extractions, progress is saved:

```
extraction_checkpoint.json
{
  "sessionId": "abc123",
  "completedEntities": ["Accounts", "Customers", "Vendors"],
  "lastEntity": "Invoices",
  "recordsExtracted": 3450
}
```

If the extraction crashes, it resumes from the last checkpoint.

### 6. COM Thread Safety

QuickBooks uses COM (Component Object Model) which is **NOT thread-safe**. The extractor handles this:

```csharp
// All COM operations run on a dedicated STA thread
private Thread _staThread;
_staThread.SetApartmentState(ApartmentState.STA);

// Every operation is marshaled to this thread
ExecuteOnSTAThread(() => {
    _qbfcSessionManager.DoRequests(request);
});
```

This prevents:
- Access violations
- Corrupted data
- Random crashes

---

## Installation Guide

### Prerequisites

You need **ONE** of the following (the extractor will detect which is available):

#### Option A: QuickBooks Desktop SDK (RECOMMENDED)

**Best for:** Full data extraction, all entity types, maximum reliability

1. Go to https://developer.intuit.com
2. Create a free Intuit Developer account
3. Navigate to: Products → QuickBooks Desktop → Downloads
4. Download and install **QBSDK16** (QuickBooks SDK 16.0)
5. Run the installer as Administrator
6. Restart your computer

**Verify installation:**
```powershell
# Check if SDK is installed
Test-Path "C:\Program Files (x86)\Intuit\IDN\QBSDK16.0"
```

#### Option B: QODBC Driver

**Best for:** When SDK installation is not possible, read-only access

1. Go to https://qodbc.com/qodbc-downloads/
2. Download QODBC Driver (free for read-only)
3. Run the installer
4. Configure the driver to connect to QuickBooks

**Verify installation:**
```powershell
# Check ODBC drivers
Get-OdbcDriver | Where-Object { $_.Name -match "QODBC|QuickBooks" }
```

### Building the Extractor

```powershell
cd QBDesktopReader

# Debug build
.\build.ps1

# Release build
.\build.ps1 -Release

# Release with installer
.\build.ps1 -Release -CreateInstaller
```

**Build output:** `publish\QBExtractor.exe`

---

## Usage Guide

### Check Available Backends

```powershell
.\QBExtractor.exe --show-backends
```

**Output:**
```
=== Available QuickBooks Backends ===

  [AVAILABLE] QBFC
           Version: QBFC16

  [NOT FOUND] QODBC
           QODBC Driver is not installed

=== Recommendations ===

  Ready to extract using: QBFC
```

### Basic Extraction

```powershell
# Standard extraction (auto-selects backend)
.\QBExtractor.exe --session FB-20260127123456-ABCD1234

# NDJSON output (warehouse-ready)
.\QBExtractor.exe --session FB-xxx --ndjson --output-dir ./export

# Incremental sync (only changes since last run)
.\QBExtractor.exe --session FB-xxx --auto-incremental

# Extract only (no upload)
.\QBExtractor.exe --session FB-xxx --extract-only
```

### Force Specific Backend

```powershell
# Force QBFC (SDK)
.\QBExtractor.exe --session FB-xxx --backend qbfc

# Force QODBC
.\QBExtractor.exe --session FB-xxx --backend qodbc
```

### Development/Testing

```powershell
# Skip license validation (dev mode)
.\QBExtractor.exe --session FB-xxx --skip-validation

# Verbose output
.\QBExtractor.exe --session FB-xxx --verbose

# No pause at end (for automation)
.\QBExtractor.exe --session FB-xxx --no-pause
```

---

## Data Extracted

### Lists (Master Data)
| Entity | Description |
|--------|-------------|
| Accounts | Chart of Accounts |
| Customers | Customer/Job list |
| Vendors | Vendor list |
| Employees | Employee list |
| Items | Products & Services |
| Classes | Class tracking |
| Payment Methods | Payment types |
| Terms | Payment terms |
| Sales Tax Codes | Tax configurations |
| Customer Types | Customer categories |
| Vendor Types | Vendor categories |
| Currencies | Multi-currency support |

### Transactions
| Entity | Description |
|--------|-------------|
| Invoices | Customer invoices with line items |
| Bills | Vendor bills |
| Checks | Check payments |
| Journal Entries | Manual journal entries |
| Deposits | Bank deposits |
| Credit Memos | Customer credits |
| Sales Receipts | Cash sales |
| Estimates | Quotes/proposals |
| Purchase Orders | POs to vendors |
| Sales Orders | Customer orders |
| Vendor Credits | Vendor credit memos |
| Inventory Adjustments | Stock adjustments |

### Additional Data
- Company preferences
- Custom fields (Data Extensions)
- Deleted records (for incremental sync)
- Report verification data

---

## Output Formats

### Single JSON (Default)
```json
{
  "schemaVersion": "4.4",
  "extractedAt": "2026-01-27T10:30:00Z",
  "company": { "companyName": "Acme Corp" },
  "accounts": [...],
  "customers": [...],
  "invoices": [...]
}
```

### NDJSON (--ndjson flag)
Per-entity files for data warehousing:
```
output/
├── accounts.ndjson
├── customers.ndjson
├── invoices.ndjson
├── vendors.ndjson
├── run_manifest.json
└── errors.ndjson
```

Each `.ndjson` file has one JSON record per line:
```json
{"listId":"80000001","name":"Checking","accountType":"Bank","balance":15000.00}
{"listId":"80000002","name":"Savings","accountType":"Bank","balance":50000.00}
```

---

## Error Handling

### Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | None needed |
| 10 | Config error | Check config.json |
| 15 | License invalid | Verify license key |
| 20 | No backend | Install SDK or QODBC |
| 30 | QB connection failed | Check QuickBooks is open |
| 40 | Extraction failed | Check error log |
| 50 | Upload failed | Check network/server |
| 60 | Cancelled | User interrupted |
| 99 | Unknown error | Check logs |

### Common Issues & Solutions

#### "No backend available"
```
Solution: Install either:
1. QBFC16 SDK from https://developer.intuit.com
2. QODBC Driver from https://qodbc.com
```

#### "QuickBooks connection failed"
```
Solution:
1. Ensure QuickBooks Desktop is OPEN
2. Open a company file in QuickBooks
3. When prompted, ALLOW the connection in QuickBooks
4. Run as Administrator if needed
```

#### "COM exception"
```
Solution:
1. Close and reopen QuickBooks
2. Run extractor as Administrator
3. Ensure 32-bit compatibility (x86)
```

---

## Security Features

### Data Protection
- **AES-256-GCM** encryption for data in transit
- **Per-record hashing** for audit trail
- **PII redaction** in logs by default
- **Secure temp file handling** with 3-pass overwrite

### Authentication
- Session code validation
- Device fingerprinting
- License key verification

---

## Troubleshooting

### Debug Mode
```powershell
.\QBExtractor.exe --session FB-xxx --verbose 2>&1 | Tee-Object debug.log
```

### Check Backend Status
```powershell
.\QBExtractor.exe --show-backends
```

### Manual SDK Check
```powershell
# Check COM registration
$type = [Type]::GetTypeFromProgID("QBFC16.QBSessionManager")
if ($type) { "QBFC16 is registered" } else { "QBFC16 NOT found" }
```

### Manual QODBC Check
```powershell
# List ODBC drivers
Get-OdbcDriver | Format-Table Name, Platform
```

---

## File Reference

| File | Purpose |
|------|---------|
| `QBExtractor.exe` | Main executable |
| `config.json` | Configuration settings |
| `config_production.json` | Production server settings |
| `IQBDataProvider.cs` | Backend abstraction interface |
| `QBFCDataProvider.cs` | QBFC SDK backend |
| `QODBCDataProvider.cs` | QODBC fallback backend |
| `QBDataExtractor.cs` | Core extraction logic (205KB) |
| `QBSessionManager.cs` | COM session management |
| `RetryHelper.cs` | Retry with exponential backoff |

---

## Why This Won't Fail - Summary

| Risk | Mitigation |
|------|------------|
| SDK not installed | Auto-fallback to QODBC |
| QODBC not installed | Clear error with installation guide |
| Network timeout | Retry with exponential backoff |
| QuickBooks busy | Retry logic, STA thread safety |
| Entity extraction fails | Isolation - continues with others |
| Crash mid-extraction | Checkpoint/resume support |
| COM threading issues | Dedicated STA thread |
| Large datasets | Streaming, low-memory mode |
| Data corruption | Per-record hashing, validation |

**Bottom line:** The extractor has multiple layers of redundancy and fault tolerance. If one path fails, it tries another. If that fails, it provides clear guidance on how to fix it.

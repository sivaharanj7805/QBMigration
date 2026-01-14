# QBDesktopReader - QuickBooks Desktop Data Extractor

Enterprise-grade data extraction from QuickBooks Desktop for migration to QuickBooks Online.

## Prerequisites

### 1. QuickBooks Desktop
- QuickBooks Desktop must be **installed and running** on the same machine
- Supported editions: Pro, Premier, Enterprise (2015 or later recommended)
- The company file must be **open** when running the extractor

### 2. QuickBooks Desktop SDK (QBFC16)
Download and install from Intuit Developer Portal:
1. Go to: https://developer.intuit.com/app/developer/qbdesktop/docs/develop/sdks-and-samples-for-qb-desktop
2. Download "QuickBooks Desktop SDK" 
3. Run the installer (installs to `C:\Program Files (x86)\Intuit\IDN\`)

### 3. .NET Framework 4.8
- Windows 10/11 includes this by default
- For Windows Server, install from Microsoft

### 4. Visual Studio 2019+ (for development)
- Community Edition is free
- Include ".NET desktop development" workload

## Building the Project

```powershell
cd QBDesktopReader
dotnet build
```

**If build fails with QBFC16 error:**
The SDK may not be installed or the COM GUID has changed. Re-add the COM reference:
1. Open the project in Visual Studio
2. Right-click "References" → "Add Reference"
3. Select COM tab → Find "qbFC16 1.0 Type Library"
4. Click OK

## Running

```powershell
# Basic extraction (single JSON)
.\bin\x86\Debug\net48\QBExtractor.exe

# NDJSON output (warehouse-ready)
.\bin\x86\Debug\net48\QBExtractor.exe --ndjson --output-dir ./export

# Incremental sync (auto-detects last run)
.\bin\x86\Debug\net48\QBExtractor.exe --ndjson --auto-incremental

# With verbose logging
.\bin\x86\Debug\net48\QBExtractor.exe -v
```

## First Run Authorization

On first run, QuickBooks will prompt for authorization:
1. QuickBooks will show a dialog: "An application is requesting access..."
2. Select **"Yes, always; allow access even if QuickBooks is not running"**
3. Click Continue

## Configuration

Edit `config.json`:
```json
{
  "serverUrl": "https://your-api-endpoint.com",
  "incrementalSyncFromDate": null,
  "advanced": {
    "initialBatchSize": 100,
    "retryAttempts": 3
  }
}
```

## Output Modes

### Single JSON (Default)
```powershell
QBExtractor.exe --extract-only
```
Produces: `extraction_{session-id}.json`

### NDJSON (Recommended for ETL)
```powershell
QBExtractor.exe --ndjson --output-dir ./export
```
Produces:
```
export/
├── accounts.ndjson
├── customers.ndjson
├── invoices.ndjson
├── ...
├── errors.ndjson
├── metrics.json
└── run_manifest.json
```

## Troubleshooting

### "QuickBooks not found / not running"
- Ensure QuickBooks Desktop is open with the company file loaded
- The extractor must run on the SAME machine as QuickBooks

### "Access denied" or "COM exception"
- Run as Administrator
- Authorize the app in QuickBooks (Edit → Preferences → Integrated Applications)

### "800700c1 is not a valid Win32 application"
- QBFC16 is 32-bit only. The project must target x86:
```xml
<PlatformTarget>x86</PlatformTarget>
```

### Build error: "Could not find type library"
- QuickBooks SDK not installed
- Download and install from Intuit Developer Portal

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      QBExtractor.exe                        │
├─────────────────────────────────────────────────────────────┤
│  Connector Layer                                            │
│  └─ QBSessionManager (STA thread, COM safety)               │
├─────────────────────────────────────────────────────────────┤
│  Extractor Layer                                            │
│  └─ QBDataExtractor + QBIteratorHelper (paging, retry)      │
├─────────────────────────────────────────────────────────────┤
│  Pipeline Layer                                             │
│  └─ StreamingPipeline + NDJSONWriter (encrypt, upload)      │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
    QuickBooks Desktop (via QBFC16 COM)
```

## Entity Types Extracted

**Lists**: Accounts, Customers, Vendors, Employees, Items, Classes, Terms, Payment Methods

**Transactions**: Invoices, Bills, Checks, Journal Entries, Deposits, Credit Memos, Sales Receipts, Estimates, Purchase Orders, Sales Orders

**Incremental**: Deleted records tracked for sync

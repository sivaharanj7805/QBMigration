# QBExtractor Deployment

This directory hosts the ForensicBridge QBExtractor download files.

## Directory Structure

```
extractor/
├── ForensicBridge_Install.bat    # Windows batch installer (downloads QBExtractor.exe)
├── ForensicBridge_Bootstrap.ps1  # PowerShell GUI installer
├── QBExtractor.exe               # <-- PUT YOUR BUILT EXE HERE
├── cache/                        # Auto-cached downloads from GitHub
│   └── QBExtractor.exe           # Alternative location
└── README.md                     # This file
```

## Deploying QBExtractor.exe

### Option 1: Place in this directory (Recommended)

Upload your built `QBExtractor.exe` directly to:
```
QBMigrationServer/static/extractor/QBExtractor.exe
```

### Option 2: Use EXTRACTOR_PATH environment variable

Set in your `.env` file:
```
EXTRACTOR_PATH=/var/www/forensicbridge/extractor/QBExtractor.exe
```

### Option 3: Place in cache directory

Upload to:
```
QBMigrationServer/static/extractor/cache/QBExtractor.exe
```

## Server Search Order

The API checks these locations in order:
1. `EXTRACTOR_PATH` environment variable (if set)
2. `/var/www/forensicbridge/extractor/QBExtractor.exe`
3. `/opt/forensicbridge/extractor/QBExtractor.exe`
4. `static/QBExtractor.exe`
5. `static/extractor/QBExtractor.exe`
6. `static/extractor/cache/QBExtractor.exe`

## File Requirements

- Minimum file size: 50KB (smaller files are rejected as invalid)
- Expected size: ~15-25 MB for self-contained .NET executable

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/extractor/download-exe` | Download QBExtractor.exe |
| `GET /api/extractor/status` | Check all download sources |
| `GET /api/extractor/info` | Get availability info |
| `POST /api/extractor/cache/clear` | Clear cached downloads |

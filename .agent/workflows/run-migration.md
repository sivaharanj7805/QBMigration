---
description: How to run the complete QB Migration process (Desktop -> Server -> Cloud)
---

# QB Migration: Full Process Execution

Follow these steps to run the end-to-end migration.

## Prerequisites

1. **PostgreSQL**: Ensure a local or remote PostgreSQL instance is running.
2. **Redis**: Required for QBMigrationServer rate limiting and background tasks.
3. **QuickBooks Desktop**: Must be open with the company file you wish to migrate.

---

## 1. Start QBMigrationServer (Flask)

The server acts as the central hub, receiving data from the desktop and managing background workers.

```powershell
# Navigate to server directory
cd QBMigrationServer

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start the Flask server
python run.py
```

*The server will be available at `http://localhost:5000`.*

---

## 2. Start Background Workers (Celery)

The workers handle the heavy lifting: decryption, transformation, and uploading to QBO.

```powershell
# Open a NEW terminal
cd QBMigrationServer
.\venv\Scripts\Activate.ps1

# Start Celery worker (ensure Redis is running)
celery -A workers.migration_worker worker --loglevel=info
```

---

## 3. Run QBDesktopReader (C#)

The desktop extractor reads data from QuickBooks, encrypts it, and sends it to the server.

1. **Configure**: Open `QBDesktopReader\config.json` and set `"serverUrl": "http://localhost:5000"`.
2. **Build**: Build the project in Visual Studio (Target: `x86`, `.NET Framework 4.8`).
3. **Run**:

```powershell
# Navigate to the bin folder
cd QBDesktopReader\bin\x86\Debug

# Run the extractor
.\QBDesktopExtractor.exe
```

---

## 4. Monitor Progress

1. **Desktop Log**: Watch the console for extraction and upload status.
2. **Server Log**: Watch the Flask console for incoming requests.
3. **Worker Log**: Watch the Celery console for migration progress (0% to 100%).
4. **QBO**: Once complete, check your QuickBooks Online sandbox to verify the data.

---

## Troubleshooting

- **Connection Error**: Ensure `serverUrl` in `config.json` matches the Flask server address.
- **SDK Error**: Ensure QuickBooks Desktop is open and the "Integrated Application" permission is granted to the extractor.
- **Worker Error**: Check `QBMigrationServer\logs\app.log` for detailed error messages.

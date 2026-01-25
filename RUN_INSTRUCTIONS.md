# ForensicBridge Run Instructions

This guide provides step-by-step instructions to get the complete ForensicBridge system running locally. The system consists of three main components:

1.  **Python Backend** (Server & API)
2.  **Next.js Frontend** (Dashboard)
3.  **C# Desktop Agent** (Data Extractor)

You will need **three separate terminal windows** to run all components simultaneously.

---

## 1. Server Setup (Backend)

The backend runs on Flask and handles the API, database, and logic.

### Prerequisites
*   Python 3.10 or higher
*   PostgreSQL (optional, can use SQLite for dev)

### Steps

1.  **Navigate to the server directory**:
    ```powershell
    cd c:\Users\Sivaharan\QBMigration\QBMigrationServer
    ```

2.  **Configure Environment**:
    Make sure the `.env` file exists in the root or server directory.
    *   **Database**: Check `DATABASE_URL` in `.env`.
        *   Default (Postgres): `postgresql://qbmigration:TestPass123@localhost:5432/qbmigration_dev`
        *   Alternative (SQLite): If you don't have Postgres installed, change line 22 in `.env` to:
            ```text
            DATABASE_URL=sqlite:///dev.db
            ```

3.  **Install Dependencies**:
    ```powershell
    # Create virtual environment (recommended)
    python -m venv venv
    .\venv\Scripts\activate

    # Install packages
    pip install -r requirements.txt
    ```

4.  **Initialize Database**:
    This script creates the necessary tables.
    ```powershell
    python init_database.py
    ```

5.  **Start the Server**:
    ```powershell
    python run.py
    ```
    *   **Success**: You should see `Server starting at: http://localhost:5000`

---

## 2. Dashboard Setup (Frontend)

The dashboard provides the user interface.

### Prerequisites
*   Node.js (LTS version recommended) and npm

### Steps

1.  **Navigate to the dashboard directory**:
    ```powershell
    cd c:\Users\Sivaharan\QBMigration\forensicbridge-dashboard
    ```

2.  **Install Dependencies**:
    ```powershell
    npm install
    ```

3.  **Start Development Server**:
    ```powershell
    npm run dev
    ```

4.  **Access the App**:
    *   Open your browser to [http://localhost:3000](http://localhost:3000).

---

## 3. Desktop Agent (Data Extractor)

This component interacts with QuickBooks Desktop.

### Prerequisites
*   .NET 8.0 SDK (or compatible version for the project)
*   Windows OS

### Steps

1.  **Navigate to the reader directory**:
    ```powershell
    cd c:\Users\Sivaharan\QBMigration\QBDesktopReader
    ```

2.  **Build the Application**:
    Run the provided build script.
    ```powershell
    powershell -ExecutionPolicy Bypass -File .\build.ps1
    ```

3.  **Run the Executable**:
    The build script outputs to the `publish` folder.
    ```powershell
    .\publish\ForensicBridge.exe
    ```

---

## Summary of URLs & Ports

| Component | URL / Location | Notes |
| :--- | :--- | :--- |
| **Dashboard** | `http://localhost:3000` | Main User Interface |
| **Backend API** | `http://localhost:5000` | API Server |
| **API Health** | `http://localhost:5000/health` | Status Check |
| **Database** | Port `5432` (Postgres) | Or `dev.db` file (SQLite) |

---

## Troubleshooting

*   **Database Errors**: If `python run.py` fails with database connection errors, ensure `DATABASE_URL` is set correctly in `.env`. Use the SQLite connection string provided above for a hassle-free local setup.
*   **Port Conflicts**: Ensure ports 3000 and 5000 are not being used by other applications.
*   **Missing `.env`**: If files are missing environment variables, copy `.env` from the root directory to `QBMigrationServer/.env`.

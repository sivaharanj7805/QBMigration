# Pre-Build Execution Guide
**Objective:** Complete these 5 phases to prepare your environment for the implementation of `ForensicBridge-Setup.exe`.

---

## Phase 1: Deploy AWS Infrastructure (The Backend)
The installer needs a live server to talk to. We will build this using the provided CloudFormation template.

**Step-by-Step:**
1.  **Log in to AWS Console:** Go to [console.aws.amazon.com](https://console.aws.amazon.com).
2.  **Go to CloudFormation:** Search for "CloudFormation" in the top bar.
3.  **Create Stack:**
    *   Click **Create stack** -> **With new resources (standard)**.
    *   Select **Upload a template file**.
    *   Click **Choose file** and select `aws/cloudformation.yaml` from this project.
    *   Click **Next**.
4.  **Configure Stack:**
    *   **Stack name:** `ForensicBridge-Prod`
    *   **Environment:** `production`
    *   **DBPassword:** Enter a strong password (e.g., specific generated password). Save this!
5.  **Launch:** Click **Next** through options, check "I acknowledge AWS CloudFormation might create IAM resources," and click **Submit**.
6.  **Get Your URL:**
    *   Wait ~10 minutes for `CREATE_COMPLETE`.
    *   Click the **Outputs** tab.
    *   Copy the Value for `ALBDNS` (e.g., `forensic-bridge-123.us-east-1.elb.amazonaws.com`).
    *   **This is your API_URL.**

---

## Phase 2: Update Application Config (The Wiring)
Now tell the installer to point to that new URL.

**Step-by-Step:**
1.  Open text editor.
2.  Navigate to `QBDesktopReader/ForensicBridge.iss`.
3.  Scroll to **Line 96** (approx).
4.  Look for:
    ```pascal
    "serverUrl": "https://api.forensicbridge.io",
    ```
5.  **Replace** the URL with your **API_URL** from Phase 1.
    *   Example: `"serverUrl": "http://forensic-bridge-123.us-east-1.elb.amazonaws.com",` (Use https if you configured SSL, otherwise http for testing).
6.  **Save** the file.

---

## Phase 3: Connect to QuickBooks Online (The Access)
The server needs permission to talk to Intuit.

**Part A: Get Keys from Intuit**
1.  Go to [developer.intuit.com](https://developer.intuit.com) and sign in.
2.  Click **My Apps** -> **Create an app**.
3.  Select **QuickBooks Online and Payments**.
4.  Give it a name (e.g., "ForensicBridge Migration").
5.  Go to **Production** settings (left sidebar).
6.  Copy your **Client ID** and **Client Secret**.
7.  Add your Redirect URI: `http://<YOUR_API_URL>/api/auth/callback` (or similar, depending on your auth flow).

**Part B: Add Keys to Your Server**
1.  **SSH into your Server:**
    *   Go to AWS Console -> EC2.
    *   Find instance `forensicbridge-production-server`.
    *   Click **Connect** -> **EC2 Instance Connect**.
2.  **Edit Config:**
    ```bash
    sudo nano /opt/forensicbridge/.env
    ```
3.  **Update Values:**
    *   Find `QBO_CLIENT_ID` and paste your ID.
    *   Find `QBO_CLIENT_SECRET` and paste your Secret.
4.  **Restart Server:**
    ```bash
    sudo systemctl restart forensicbridge
    ```

---

## Phase 4: Create the Application Icon (The Polish)
The installer build will fail (or look broken) without an icon.

**Step-by-Step:**
1.  **Find an Icon:**
    *   Use a site like [icon-icons.com](https://icon-icons.com) to find a "Database" or "Bridge" icon.
    *   Download it as `.ico` format (32x32 or 64x64).
2.  **Place the File:**
    *   Rename the file to `icon.ico`.
    *   Move it into the folder: `QBDesktopReader/assets/`
    *   Ensure path is: `c:\Users\Sivaharan\QBMigration\QBDesktopReader\assets\icon.ico`

---

## Phase 5: Build the Installer (The Button)
Everything is ready. Now we trigger the cloud builder.

**Step-by-Step:**
1.  **Open Terminal** in the project folder.
2.  **Stage Changes:**
    ```bash
    git add .
    ```
3.  **Commit:**
    ```bash
    git commit -m "Configured production URLs and added icon"
    ```
4.  **Push:**
    ```bash
    git push origin main
    ```
5.  **Watch Build:**
    *   Go to your GitHub Repository page.
    *   Click **Actions** tab.
    *   Click **"Build ForensicBridge Installer"**.
    *   Watch the steps turn green.
6.  **Download:**
    *   When finished, scroll to **Artifacts**.
    *   Download `ForensicBridge-Setup`.

You now have a fully functional, production-ready installer.

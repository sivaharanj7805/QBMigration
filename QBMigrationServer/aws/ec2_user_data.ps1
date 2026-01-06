<powershell>
# ============================================================================
# QuickBooks Migration - EC2 Instance User Data Script
# ============================================================================
# This script runs automatically when EC2 instance boots
# It downloads encrypted QB file from S3, decrypts it, runs migration, and
# self-terminates the instance. ZERO DATA PERSISTS.
# ============================================================================

$ErrorActionPreference = "Stop"

# ============================================================================
# CONFIGURATION (populated by app.py when instance created)
# ============================================================================
$MigrationId = "{{MIGRATION_ID}}"
$S3Bucket = "{{S3_BUCKET}}"
$S3Key = "{{S3_KEY}}"
$ServerUrl = "{{SERVER_URL}}"
$WebhookSignature = "{{WEBHOOK_SIGNATURE}}"
$Region = "{{AWS_REGION}}"

# QBO Credentials (passed as environment variables)
$QBOClientId = "{{QBO_CLIENT_ID}}"
$QBOClientSecret = "{{QBO_CLIENT_SECRET}}"
$QBORefreshToken = "{{QBO_REFRESH_TOKEN}}"

# ============================================================================
# DIRECTORIES
# ============================================================================
$TempDir = "C:\QBMigrationTemp"
$LogFile = "$TempDir\migration.log"
$ToolsDir = "C:\QBMigrationTool"

# ============================================================================
# LOGGING FUNCTION
# ============================================================================
function Write-MigrationLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    Write-Host $logMessage
    
    try {
        Add-Content -Path $LogFile -Value $logMessage -ErrorAction SilentlyContinue
    } catch {
        # Ignore logging errors
    }
}

# ============================================================================
# WEBHOOK FUNCTION
# ============================================================================
function Send-Webhook {
    param(
        [string]$Endpoint,
        [hashtable]$Body
    )
    
    try {
        $headers = @{
            "Content-Type" = "application/json"
            "X-Migration-Id" = $MigrationId
            "X-Webhook-Signature" = $WebhookSignature
        }
        
        $jsonBody = $Body | ConvertTo-Json -Depth 10 -Compress
        
        $response = Invoke-RestMethod `
            -Uri "$ServerUrl$Endpoint" `
            -Method POST `
            -Headers $headers `
            -Body $jsonBody `
            -TimeoutSec 30 `
            -ErrorAction Stop
            
        Write-MigrationLog "Webhook sent: $Endpoint" "INFO"
        return $true
    }
    catch {
        Write-MigrationLog "Webhook failed: $Endpoint - $($_.Exception.Message)" "ERROR"
        return $false
    }
}

# ============================================================================
# CLEANUP FUNCTION
# ============================================================================
function Remove-AllFiles {
    Write-MigrationLog "Cleaning up all local files..." "INFO"
    
    try {
        # Remove temp directory
        if (Test-Path $TempDir) {
            Remove-Item -Path "$TempDir\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        
        # Clear QuickBooks recent files list
        $QBRegistryPath = "HKCU:\Software\Intuit\QuickBooks"
        if (Test-Path $QBRegistryPath) {
            Remove-Item -Path "$QBRegistryPath\*" -Recurse -Force -ErrorAction SilentlyContinue
        }
        
        # Clear temp files
        Remove-Item -Path "$env:TEMP\*" -Recurse -Force -ErrorAction SilentlyContinue
        
        Write-MigrationLog "Cleanup completed" "INFO"
    }
    catch {
        Write-MigrationLog "Cleanup error (non-fatal): $($_.Exception.Message)" "WARN"
    }
}

# ============================================================================
# SELF-TERMINATION FUNCTION
# ============================================================================
function Stop-SelfInstance {
    Write-MigrationLog "Initiating self-termination..." "INFO"
    
    try {
        # Get instance ID from metadata
        $instanceId = Invoke-RestMethod `
            -Uri "http://169.254.169.254/latest/meta-data/instance-id" `
            -UseBasicParsing `
            -TimeoutSec 5
        
        Write-MigrationLog "Instance ID: $instanceId" "INFO"
        
        # Wait for webhooks to complete
        Start-Sleep -Seconds 60
        
        # Terminate self
        aws ec2 terminate-instances --instance-ids $instanceId --region $Region
        
        Write-MigrationLog "Termination command sent" "INFO"
    }
    catch {
        Write-MigrationLog "Failed to terminate instance: $($_.Exception.Message)" "ERROR"
    }
}

# ============================================================================
# MAIN MIGRATION PROCESS
# ============================================================================
try {
    # Create temp directory
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
    
    Write-MigrationLog "============================================" "INFO"
    Write-MigrationLog "QB MIGRATION STARTING" "INFO"
    Write-MigrationLog "Migration ID: $MigrationId" "INFO"
    Write-MigrationLog "============================================" "INFO"
    
    # ========================================================================
    # STEP 1: Send start webhook
    # ========================================================================
    $instanceId = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/instance-id" -UseBasicParsing
    
    Send-Webhook -Endpoint "/api/webhooks/migration-started" -Body @{
        migration_id = $MigrationId
        instance_id = $instanceId
    }
    
    # ========================================================================
    # STEP 2: Download encrypted file from S3
    # ========================================================================
    Write-MigrationLog "Downloading file from S3..." "INFO"
    
    $EncryptedFile = "$TempDir\encrypted.enc"
    
    aws s3 cp "s3://$S3Bucket/$S3Key" $EncryptedFile --region $Region
    
    if (-not (Test-Path $EncryptedFile)) {
        throw "Failed to download file from S3"
    }
    
    $fileSize = (Get-Item $EncryptedFile).Length
    Write-MigrationLog "Downloaded file: $fileSize bytes" "INFO"
    
    Send-Webhook -Endpoint "/api/webhooks/migration-progress" -Body @{
        migration_id = $MigrationId
        progress_percent = 25
        current_step = "File downloaded from S3"
    }
    
    # ========================================================================
    # STEP 3: Decrypt QuickBooks file
    # ========================================================================
    Write-MigrationLog "Decrypting QuickBooks file..." "INFO"
    
    $DecryptedFile = "$TempDir\company.qbw"
    
    # Call your C# decryption tool
    & "$ToolsDir\QBDecrypt.exe" `
        --input $EncryptedFile `
        --output $DecryptedFile
    
    if (-not (Test-Path $DecryptedFile)) {
        throw "Decryption failed - output file not created"
    }
    
    Write-MigrationLog "File decrypted successfully" "INFO"
    
    # Delete encrypted file immediately (no longer needed)
    Remove-Item -Path $EncryptedFile -Force
    Write-MigrationLog "Encrypted file deleted" "INFO"
    
    Send-Webhook -Endpoint "/api/webhooks/migration-progress" -Body @{
        migration_id = $MigrationId
        progress_percent = 50
        current_step = "File decrypted"
    }
    
    # ========================================================================
    # STEP 4: Start QuickBooks Desktop (headless)
    # ========================================================================
    Write-MigrationLog "Starting QuickBooks Desktop..." "INFO"
    
    $QBPath = "C:\Program Files\Intuit\QuickBooks 2024\qbw32.exe"
    
    if (-not (Test-Path $QBPath)) {
        throw "QuickBooks Desktop not found at: $QBPath"
    }
    
    Start-Process -FilePath $QBPath `
        -ArgumentList $DecryptedFile `
        -WindowStyle Hidden
    
    # Wait for QB to start
    Start-Sleep -Seconds 30
    
    Send-Webhook -Endpoint "/api/webhooks/migration-progress" -Body @{
        migration_id = $MigrationId
        progress_percent = 60
        current_step = "QuickBooks Desktop started"
    }
    
    # ========================================================================
    # STEP 5: Run migration to QuickBooks Online
    # ========================================================================
    Write-MigrationLog "Starting migration to QuickBooks Online..." "INFO"
    
    # Set environment variables for migration tool
    $env:QBO_CLIENT_ID = $QBOClientId
    $env:QBO_CLIENT_SECRET = $QBOClientSecret
    $env:QBO_REFRESH_TOKEN = $QBORefreshToken
    $env:MIGRATION_ID = $MigrationId
    $env:QB_FILE_PATH = $DecryptedFile
    
    # Run your C# migration tool
    $migrationOutput = & "$ToolsDir\QBMigrationService.exe" `
        --migration-id $MigrationId `
        --qb-file $DecryptedFile `
        2>&1
    
    Write-MigrationLog "Migration tool completed" "INFO"
    
    # Parse results from tool output (customize based on your tool)
    # Expected format: "RESULTS: {customers:50,vendors:30,invoices:100}"
    $results = @{
        customers = 0
        vendors = 0
        invoices = 0
        total = 0
    }
    
    if ($migrationOutput -match "RESULTS:\s*(\{.*\})") {
        try {
            $resultsJson = $matches[1] | ConvertFrom-Json
            $results = @{
                customers = $resultsJson.customers
                vendors = $resultsJson.vendors
                invoices = $resultsJson.invoices
                total = $resultsJson.total
            }
        } catch {
            Write-MigrationLog "Failed to parse results: $($_.Exception.Message)" "WARN"
        }
    }
    
    Write-MigrationLog "Migration completed: $($results.total) records" "INFO"
    
    # ========================================================================
    # STEP 6: Send completion webhook
    # ========================================================================
    Send-Webhook -Endpoint "/api/webhooks/migration-completed" -Body @{
        migration_id = $MigrationId
        status = "completed"
        results = $results
    }
    
    Write-MigrationLog "============================================" "INFO"
    Write-MigrationLog "MIGRATION COMPLETED SUCCESSFULLY" "INFO"
    Write-MigrationLog "============================================" "INFO"
    
} catch {
    # ========================================================================
    # ERROR HANDLING
    # ========================================================================
    $errorMessage = $_.Exception.Message
    $errorStack = $_.Exception.StackTrace
    
    Write-MigrationLog "============================================" "ERROR"
    Write-MigrationLog "MIGRATION FAILED" "ERROR"
    Write-MigrationLog "Error: $errorMessage" "ERROR"
    Write-MigrationLog "Stack: $errorStack" "ERROR"
    Write-MigrationLog "============================================" "ERROR"
    
    # Send failure webhook
    Send-Webhook -Endpoint "/api/webhooks/migration-failed" -Body @{
        migration_id = $MigrationId
        error = $errorMessage
        error_detail = $errorStack
    }
    
} finally {
    # ========================================================================
    # CLEANUP & TERMINATION (ALWAYS RUNS)
    # ========================================================================
    Write-MigrationLog "Final cleanup starting..." "INFO"
    
    # Stop QuickBooks
    try {
        Get-Process -Name "qbw32" -ErrorAction SilentlyContinue | Stop-Process -Force
        Write-MigrationLog "QuickBooks terminated" "INFO"
    } catch {
        Write-MigrationLog "QuickBooks already stopped" "INFO"
    }
    
    # Remove all files
    Remove-AllFiles
    
    # Self-terminate
    Stop-SelfInstance
}

</powershell>
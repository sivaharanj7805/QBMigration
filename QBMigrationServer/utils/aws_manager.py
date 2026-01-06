import boto3
import base64
import json
import time
import logging
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import hashlib
import hmac

logger = logging.getLogger(__name__)


class AWSMigrationManager:
    """Manage ephemeral AWS instances for QB migrations with full observability"""
    
    def __init__(self, region='us-east-1'):
        """Initialize AWS clients"""
        self.region = region
        
        try:
            self.ec2 = boto3.client('ec2', region_name=region)
            self.s3 = boto3.client('s3', region_name=region)
            self.ssm = boto3.client('ssm', region_name=region)
            self.cloudwatch = boto3.client('cloudwatch', region_name=region)
            self.ce = boto3.client('ce', region_name=region)  # Cost Explorer
            self.secrets = boto3.client('secretsmanager', region_name=region)
            
            logger.info(f"AWS clients initialized for region {region}")
        except Exception as e:
            logger.exception(f"Failed to initialize AWS clients: {str(e)}")
            raise
    
    # ============================================================================
    # S3 OPERATIONS
    # ============================================================================
    
    def upload_to_s3(self, file_obj, migration_id, metadata=None):
        """Upload file to S3 with encryption"""
        try:
            from flask import current_app
            bucket_name = current_app.config.get('AWS_S3_BUCKET')
            
            if not bucket_name:
                logger.error("AWS_S3_BUCKET not configured")
                return None
            
            # Generate S3 key
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            object_key = f"migrations/{migration_id}/{timestamp}_encrypted.enc"
            
            # Prepare metadata
            upload_metadata = {
                'migration-id': migration_id,
                'uploaded-at': datetime.utcnow().isoformat(),
                'content-type': 'application/octet-stream'
            }
            
            if metadata:
                for key, value in metadata.items():
                    safe_key = key.lower().replace('_', '-')
                    upload_metadata[safe_key] = str(value)
            
            # Upload with server-side encryption
            extra_args = {
                'ServerSideEncryption': 'AES256',
                'Metadata': upload_metadata,
                'ContentType': 'application/octet-stream',
                'StorageClass': 'STANDARD_IA'
            }
            
            self.s3.upload_fileobj(
                file_obj,
                bucket_name,
                object_key,
                ExtraArgs=extra_args
            )
            
            s3_uri = f"s3://{bucket_name}/{object_key}"
            
            logger.info(f"Uploaded to S3: {s3_uri}")
            
            # Set lifecycle policy
            try:
                self._set_object_lifecycle(bucket_name, object_key, hours=24)
            except Exception as e:
                logger.warning(f"Failed to set lifecycle policy: {str(e)}")
            
            # Publish metric
            self._publish_metric('S3Upload', 1, 'Count')
            
            return {
                'uri': s3_uri,
                'bucket': bucket_name,
                'key': object_key
            }
            
        except Exception as e:
            logger.exception(f"Failed to upload to S3: {str(e)}")
            self._publish_metric('S3UploadFailure', 1, 'Count')
            return None
    
    def _set_object_lifecycle(self, bucket, key, hours=24):
        """Set lifecycle policy on specific object"""
        try:
            self.s3.put_object_tagging(
                Bucket=bucket,
                Key=key,
                Tagging={
                    'TagSet': [
                        {'Key': 'auto-delete', 'Value': 'true'},
                        {'Key': 'expires-in-hours', 'Value': str(hours)}
                    ]
                }
            )
            logger.debug(f"Set lifecycle tags on {key}")
        except Exception as e:
            logger.exception(f"Failed to set lifecycle tags: {str(e)}")
    
    def delete_s3_file(self, migration_id):
        """Delete S3 file and all related objects"""
        try:
            from flask import current_app
            bucket_name = current_app.config.get('AWS_S3_BUCKET')
            
            if not bucket_name:
                logger.error("AWS_S3_BUCKET not configured")
                return False
            
            prefix = f"migrations/{migration_id}/"
            
            response = self.s3.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                logger.info(f"No S3 objects found for {migration_id}")
                return True
            
            objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
            
            if objects_to_delete:
                self.s3.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': objects_to_delete}
                )
                
                logger.info(f"Deleted {len(objects_to_delete)} S3 objects for {migration_id}")
                self._publish_metric('S3Delete', len(objects_to_delete), 'Count')
            
            return True
            
        except Exception as e:
            logger.exception(f"Failed to delete S3 files for {migration_id}: {str(e)}")
            return False
    
    # ============================================================================
    # EC2 OPERATIONS
    # ============================================================================
    
    def create_ec2_instance(self, migration_id, s3_uri, qbo_credentials, webhook_secret):
        """Create ephemeral EC2 instance with secrets in Secrets Manager"""
        try:
            from flask import current_app
            
            # Get configuration
            ami_id = current_app.config.get('AWS_EC2_AMI_ID')
            instance_type = current_app.config.get('AWS_EC2_INSTANCE_TYPE')
            key_name = current_app.config.get('AWS_EC2_KEY_NAME')
            security_group = current_app.config.get('AWS_EC2_SECURITY_GROUP')
            subnet_id = current_app.config.get('AWS_EC2_SUBNET_ID')
            iam_profile = current_app.config.get('AWS_IAM_INSTANCE_PROFILE')
            server_url = current_app.config.get('SERVER_URL')
            
            if not all([ami_id, instance_type, key_name, iam_profile]):
                logger.error("Missing required EC2 configuration")
                return None
            
            # Store QBO credentials in Secrets Manager (MORE SECURE)
            secret_name = f"qb-migration/{migration_id}"
            try:
                self.secrets.create_secret(
                    Name=secret_name,
                    SecretString=json.dumps(qbo_credentials),
                    Tags=[
                        {'Key': 'MigrationId', 'Value': migration_id},
                        {'Key': 'CreatedAt', 'Value': datetime.utcnow().isoformat()}
                    ]
                )
                logger.info(f"Stored credentials in Secrets Manager: {secret_name}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceExistsException':
                    # Update existing secret
                    self.secrets.update_secret(
                        SecretId=secret_name,
                        SecretString=json.dumps(qbo_credentials)
                    )
                else:
                    raise
            
            # Generate user data script (credentials fetched from Secrets Manager)
            user_data = self._generate_user_data_script(
                migration_id=migration_id,
                s3_uri=s3_uri,
                secret_name=secret_name,
                server_url=server_url,
                webhook_secret=webhook_secret
            )
            
            # Launch configuration
            launch_config = {
                'ImageId': ami_id,
                'InstanceType': instance_type,
                'KeyName': key_name,
                'MinCount': 1,
                'MaxCount': 1,
                'UserData': user_data,
                'IamInstanceProfile': {'Name': iam_profile},
                'TagSpecifications': [
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {'Key': 'Name', 'Value': f'QB-Migration-{migration_id}'},
                            {'Key': 'MigrationId', 'Value': migration_id},
                            {'Key': 'Purpose', 'Value': 'ephemeral-migration'},
                            {'Key': 'AutoTerminate', 'Value': 'true'},
                            {'Key': 'CreatedAt', 'Value': datetime.utcnow().isoformat()}
                        ]
                    }
                ],
                'BlockDeviceMappings': [
                    {
                        'DeviceName': '/dev/sda1',
                        'Ebs': {
                            'VolumeSize': 50,
                            'VolumeType': 'gp3',
                            'DeleteOnTermination': True,
                            'Encrypted': True
                        }
                    }
                ],
                'InstanceInitiatedShutdownBehavior': 'terminate',
                'Monitoring': {'Enabled': True}  # Detailed monitoring
            }
            
            if security_group:
                launch_config['SecurityGroupIds'] = [security_group]
            
            if subnet_id:
                launch_config['SubnetId'] = subnet_id
            
            # Launch instance
            response = self.ec2.run_instances(**launch_config)
            
            instance_id = response['Instances'][0]['InstanceId']
            
            logger.info(f"Created EC2 instance: {instance_id} for migration {migration_id}")
            
            # Publish metric
            self._publish_metric('EC2InstanceCreated', 1, 'Count')
            
            return instance_id
            
        except Exception as e:
            logger.exception(f"Failed to create EC2 instance: {str(e)}")
            self._publish_metric('EC2InstanceCreationFailure', 1, 'Count')
            return None
    
    def _generate_user_data_script(self, migration_id, s3_uri, secret_name, server_url, webhook_secret):
        """Generate PowerShell script with Secrets Manager integration"""
        
        s3_parts = s3_uri.replace('s3://', '').split('/', 1)
        s3_bucket = s3_parts[0]
        s3_key = s3_parts[1] if len(s3_parts) > 1 else ''
        
        webhook_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            migration_id.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        script = f"""<powershell>
# QB Migration - EC2 User Data Script
# SECURE: Credentials fetched from AWS Secrets Manager

$ErrorActionPreference = "Stop"

# Configuration
$MigrationId = "{migration_id}"
$S3Bucket = "{s3_bucket}"
$S3Key = "{s3_key}"
$ServerUrl = "{server_url}"
$WebhookSignature = "{webhook_signature}"
$Region = "{self.region}"
$SecretName = "{secret_name}"

$TempDir = "C:\\QBMigrationTemp"
$LogFile = "$TempDir\\migration.log"
$ToolsDir = "C:\\QBMigrationTool"

New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

function Write-MigrationLog {{
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    Write-Host $logMessage
    Add-Content -Path $LogFile -Value $logMessage -ErrorAction SilentlyContinue
}}

function Send-Webhook {{
    param([string]$Endpoint, [hashtable]$Body)
    
    try {{
        $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
        $webhookId = [guid]::NewGuid().ToString()
        
        $headers = @{{
            "Content-Type" = "application/json"
            "X-Migration-Id" = $MigrationId
            "X-Webhook-Signature" = $WebhookSignature
            "X-Webhook-Timestamp" = $timestamp
            "X-Webhook-Id" = $webhookId
        }}
        
        $jsonBody = $Body | ConvertTo-Json -Depth 10 -Compress
        
        Invoke-RestMethod -Uri "$ServerUrl$Endpoint" `
            -Method POST `
            -Headers $headers `
            -Body $jsonBody `
            -TimeoutSec 30 | Out-Null
            
        Write-MigrationLog "Webhook sent: $Endpoint (ID: $webhookId)" "INFO"
    }}
    catch {{
        Write-MigrationLog "Webhook failed: $Endpoint - $_" "ERROR"
    }}
}}

function Remove-AllFiles {{
    Write-MigrationLog "Cleaning up all files..." "INFO"
    try {{
        if (Test-Path $TempDir) {{
            Remove-Item -Path "$TempDir\\*" -Recurse -Force -ErrorAction SilentlyContinue
        }}
        Remove-Item -Path "$env:TEMP\\*" -Recurse -Force -ErrorAction SilentlyContinue
    }}
    catch {{
        Write-MigrationLog "Cleanup error: $_" "WARN"
    }}
}}

function Stop-SelfInstance {{
    Write-MigrationLog "Triggering self-termination..." "INFO"
    try {{
        $instanceId = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/instance-id" -UseBasicParsing
        Start-Sleep -Seconds 60
        aws ec2 terminate-instances --instance-ids $instanceId --region $Region
    }}
    catch {{
        Write-MigrationLog "Termination failed: $_" "ERROR"
    }}
}}

try {{
    Write-MigrationLog "=== Migration Starting ===" "INFO"
    
    $instanceId = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/instance-id" -UseBasicParsing
    
    Send-Webhook -Endpoint "/api/webhooks/migration-started" -Body @{{
        migration_id = $MigrationId
        instance_id = $instanceId
    }}
    
    # Fetch credentials from Secrets Manager (SECURE)
    Write-MigrationLog "Fetching credentials from Secrets Manager..." "INFO"
    $secretJson = aws secretsmanager get-secret-value --secret-id $SecretName --region $Region --query SecretString --output text
    $credentials = $secretJson | ConvertFrom-Json
    
    $env:QBO_CLIENT_ID = $credentials.client_id
    $env:QBO_CLIENT_SECRET = $credentials.client_secret
    $env:QBO_REFRESH_TOKEN = $credentials.refresh_token
    
    Write-MigrationLog "Credentials retrieved successfully" "INFO"
    
    # Download from S3
    Write-MigrationLog "Downloading from S3..." "INFO"
    $EncryptedFile = "$TempDir\\encrypted.enc"
    aws s3 cp "s3://$S3Bucket/$S3Key" $EncryptedFile --region $Region
    
    if (-not (Test-Path $EncryptedFile)) {{
        throw "S3 download failed"
    }}
    
    Send-Webhook -Endpoint "/api/webhooks/migration-progress" -Body @{{
        migration_id = $MigrationId
        progress_percent = 25
        current_step = "File downloaded"
    }}
    
    # Decrypt
    Write-MigrationLog "Decrypting..." "INFO"
    $DecryptedFile = "$TempDir\\company.qbw"
    & "$ToolsDir\\QBDecrypt.exe" --input $EncryptedFile --output $DecryptedFile
    
    Remove-Item -Path $EncryptedFile -Force
    
    Send-Webhook -Endpoint "/api/webhooks/migration-progress" -Body @{{
        migration_id = $MigrationId
        progress_percent = 50
        current_step = "File decrypted"
    }}
    
    # Start QB
    Write-MigrationLog "Starting QuickBooks..." "INFO"
    $QBPath = "C:\\Program Files\\Intuit\\QuickBooks 2024\\qbw32.exe"
    Start-Process -FilePath $QBPath -ArgumentList $DecryptedFile -WindowStyle Hidden
    Start-Sleep -Seconds 30
    
    # Run migration
    Write-MigrationLog "Running migration..." "INFO"
    $env:MIGRATION_ID = $MigrationId
    $env:QB_FILE_PATH = $DecryptedFile
    
    $output = & "$ToolsDir\\QBMigrationService.exe" --migration-id $MigrationId 2>&1
    
    # Parse results
    $results = @{{
        customers = 0
        vendors = 0
        invoices = 0
        total = 0
    }}
    
    Send-Webhook -Endpoint "/api/webhooks/migration-completed" -Body @{{
        migration_id = $MigrationId
        status = "completed"
        results = $results
    }}
    
    Write-MigrationLog "=== Migration Completed ===" "INFO"
    
}}
catch {{
    Write-MigrationLog "FATAL ERROR: $_" "ERROR"
    
    Send-Webhook -Endpoint "/api/webhooks/migration-failed" -Body @{{
        migration_id = $MigrationId
        error = $_.Exception.Message
        error_code = "MIGRATION_ERROR"
    }}
    
    exit 1
}}
finally {{
    # Delete secret from Secrets Manager
    try {{
        aws secretsmanager delete-secret --secret-id $SecretName --force-delete-without-recovery --region $Region
        Write-MigrationLog "Deleted secret from Secrets Manager" "INFO"
    }}
    catch {{
        Write-MigrationLog "Failed to delete secret: $_" "WARN"
    }}
    
    Remove-AllFiles
    Stop-SelfInstance
}}

</powershell>
"""
        
        return base64.b64encode(script.encode('utf-8')).decode('utf-8')
    
    def terminate_instance(self, instance_id):
        """Terminate EC2 instance"""
        try:
            self.ec2.terminate_instances(InstanceIds=[instance_id])
            logger.info(f"Terminated instance: {instance_id}")
            self._publish_metric('EC2InstanceTerminated', 1, 'Count')
            return True
        except Exception as e:
            logger.exception(f"Failed to terminate instance {instance_id}: {str(e)}")
            return False
    
    def get_instance_status(self, instance_id):
        """Get EC2 instance status with health checks"""
        try:
            response = self.ec2.describe_instances(InstanceIds=[instance_id])
            
            if not response['Reservations']:
                return None
            
            instance = response['Reservations'][0]['Instances'][0]
            
            # Get detailed status
            status_response = self.ec2.describe_instance_status(InstanceIds=[instance_id])
            
            status_info = {
                'state': instance['State']['Name'],
                'launch_time': instance['LaunchTime'],
                'instance_type': instance['InstanceType'],
                'public_ip': instance.get('PublicIpAddress'),
                'private_ip': instance.get('PrivateIpAddress')
            }
            
            if status_response['InstanceStatuses']:
                status = status_response['InstanceStatuses'][0]
                status_info.update({
                    'instance_status': status['InstanceStatus']['Status'],
                    'system_status': status['SystemStatus']['Status'],
                    'healthy': status['InstanceStatus']['Status'] == 'ok' and status['SystemStatus']['Status'] == 'ok'
                })
            
            return status_info
            
        except Exception as e:
            logger.exception(f"Failed to get instance status for {instance_id}: {str(e)}")
            return None
    
    # ============================================================================
    # COST TRACKING
    # ============================================================================
    
    def get_migration_cost(self, migration_id, start_date, end_date):
        """Get actual cost from AWS Cost Explorer"""
        try:
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                Filter={
                    'Tags': {
                        'Key': 'MigrationId',
                        'Values': [migration_id]
                    }
                },
                GroupBy=[
                    {'Type': 'SERVICE', 'Key': 'SERVICE'}
                ]
            )
            
            costs = {}
            total = 0.0
            
            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    costs[service] = costs.get(service, 0.0) + cost
                    total += cost
            
            logger.info(f"Retrieved cost for {migration_id}: ${total:.4f}")
            
            return {
                'total': round(total, 4),
                'breakdown': {k: round(v, 4) for k, v in costs.items()}
            }
            
        except Exception as e:
            logger.exception(f"Failed to get migration cost: {str(e)}")
            return None
    
    # ============================================================================
    # CLEANUP
    # ============================================================================
    
    def cleanup_migration(self, migration_id, instance_id=None):
        """Complete cleanup of migration resources"""
        results = {
            'instance_terminated': False,
            's3_deleted': False,
            'snapshots_deleted': False,
            'secret_deleted': False
        }
        
        try:
            # Terminate instance
            if instance_id:
                results['instance_terminated'] = self.terminate_instance(instance_id)
            else:
                results['instance_terminated'] = True
            
            # Delete S3 files
            results['s3_deleted'] = self.delete_s3_file(migration_id)
            
            # Delete snapshots
            try:
                snapshots = self.ec2.describe_snapshots(
                    Filters=[
                        {'Name': 'tag:MigrationId', 'Values': [migration_id]}
                    ]
                )['Snapshots']
                
                for snapshot in snapshots:
                    self.ec2.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                    logger.info(f"Deleted snapshot: {snapshot['SnapshotId']}")
                
                results['snapshots_deleted'] = True
            except Exception as e:
                logger.warning(f"Failed to delete snapshots: {str(e)}")
                results['snapshots_deleted'] = False
            
            # Delete secret from Secrets Manager
            try:
                secret_name = f"qb-migration/{migration_id}"
                self.secrets.delete_secret(
                    SecretId=secret_name,
                    ForceDeleteWithoutRecovery=True
                )
                logger.info(f"Deleted secret: {secret_name}")
                results['secret_deleted'] = True
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    logger.warning(f"Failed to delete secret: {str(e)}")
                results['secret_deleted'] = True  # Already deleted or doesn't exist
            
            logger.info(f"Cleanup completed for {migration_id}: {results}")
            
            return results
            
        except Exception as e:
            logger.exception(f"Cleanup failed for {migration_id}: {str(e)}")
            return results
    
    # ============================================================================
    # METRICS
    # ============================================================================
    
    def _publish_metric(self, metric_name, value, unit='None'):
        """Publish metric to CloudWatch"""
        try:
            self.cloudwatch.put_metric_data(
                Namespace='QBMigration',
                MetricData=[
                    {
                        'MetricName': metric_name,
                        'Value': value,
                        'Unit': unit,
                        'Timestamp': datetime.utcnow()
                    }
                ]
            )
        except Exception as e:
            logger.error(f"Failed to publish metric {metric_name}: {str(e)}")
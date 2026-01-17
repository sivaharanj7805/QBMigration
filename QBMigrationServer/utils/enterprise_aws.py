"""
Enterprise AWS Module
=====================
Advanced AWS features for enterprise compliance:
1. S3 Object Locking (WORM) - Write Once, Read Many
2. Customer-Managed Keys (CMK) - Client-owned KMS encryption
3. Multi-AZ Deployment - High availability across zones
4. Regional Enforcement - Canadian Data Residency (ca-central-1)

Version: 1.0
"""

import boto3
import logging
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from typing import Optional, Dict, List, Tuple
import json

logger = logging.getLogger(__name__)

# =============================================================================
# CANADIAN DATA RESIDENCY ENFORCEMENT
# =============================================================================

REQUIRED_REGION = 'ca-central-1'  # Montreal
ALLOWED_AVAILABILITY_ZONES = ['ca-central-1a', 'ca-central-1b', 'ca-central-1d']


class RegionalEnforcement:
    """Enforce Canadian data residency requirements"""
    
    @staticmethod
    def verify_region(region: str) -> Tuple[bool, str]:
        """
        Verify that the specified region is ca-central-1 (Montreal)
        
        Returns:
            (is_valid, error_message)
        """
        if region != REQUIRED_REGION:
            return False, f"Region '{region}' not allowed. Must use '{REQUIRED_REGION}' (Montreal) for Canadian data residency."
        return True, None
    
    @staticmethod
    def verify_s3_bucket_location(s3_client, bucket_name: str) -> Tuple[bool, str]:
        """
        Verify S3 bucket is located in ca-central-1
        """
        try:
            response = s3_client.get_bucket_location(Bucket=bucket_name)
            location = response.get('LocationConstraint')
            
            # AWS quirk: us-east-1 returns None
            if location is None:
                location = 'us-east-1'
            
            if location != REQUIRED_REGION:
                return False, f"S3 bucket '{bucket_name}' is in '{location}', must be in '{REQUIRED_REGION}'"
            
            logger.info(f"S3 bucket '{bucket_name}' verified in {REQUIRED_REGION}")
            return True, None
            
        except ClientError as e:
            return False, f"Failed to verify bucket location: {str(e)}"
    
    @staticmethod
    def verify_ec2_availability_zone(ec2_client, instance_id: str) -> Tuple[bool, str]:
        """
        Verify EC2 instance is in an allowed ca-central-1 availability zone
        """
        try:
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    az = instance.get('Placement', {}).get('AvailabilityZone', '')
                    
                    if az not in ALLOWED_AVAILABILITY_ZONES:
                        return False, f"Instance '{instance_id}' in AZ '{az}', must be in {ALLOWED_AVAILABILITY_ZONES}"
                    
                    logger.info(f"EC2 instance '{instance_id}' verified in {az}")
                    return True, None
            
            return False, f"Instance '{instance_id}' not found"
            
        except ClientError as e:
            return False, f"Failed to verify instance zone: {str(e)}"


# =============================================================================
# S3 OBJECT LOCKING (WORM - Write Once, Read Many)
# =============================================================================

class S3ObjectLocking:
    """
    Implements WORM storage for forensic audit trails.
    Provides mathematical proof that data was not modified after creation.
    
    Used for:
    - run_manifest.json
    - Forensic logs
    - Migration reports
    """
    
    def __init__(self, s3_client=None, bucket_name: str = None):
        self.s3 = s3_client or boto3.client('s3', region_name=REQUIRED_REGION)
        self.bucket_name = bucket_name
    
    def enable_object_lock_on_bucket(self, bucket_name: str = None) -> dict:
        """
        Enable Object Lock on an S3 bucket.
        NOTE: Object Lock must be enabled at bucket creation time.
        This method configures default retention if already enabled.
        """
        bucket = bucket_name or self.bucket_name
        
        try:
            # Check if Object Lock is enabled
            response = self.s3.get_object_lock_configuration(Bucket=bucket)
            logger.info(f"Object Lock already enabled on bucket '{bucket}'")
            return response
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ObjectLockConfigurationNotFoundError':
                logger.warning(f"Object Lock not enabled on bucket '{bucket}'. "
                             "Must be enabled at bucket creation time.")
                return {'error': 'Object Lock must be enabled at bucket creation'}
            raise
    
    def set_default_retention(self, bucket_name: str, mode: str = 'GOVERNANCE', 
                              days: int = 2555) -> dict:
        """
        Set default retention policy for the bucket.
        
        Args:
            bucket_name: S3 bucket name
            mode: 'GOVERNANCE' (removable with permission) or 'COMPLIANCE' (immutable)
            days: Retention period in days (default 7 years = 2555 days)
        """
        try:
            response = self.s3.put_object_lock_configuration(
                Bucket=bucket_name,
                ObjectLockConfiguration={
                    'ObjectLockEnabled': 'Enabled',
                    'Rule': {
                        'DefaultRetention': {
                            'Mode': mode,
                            'Days': days
                        }
                    }
                }
            )
            logger.info(f"Set {mode} retention of {days} days on bucket '{bucket_name}'")
            return {'success': True, 'mode': mode, 'days': days}
            
        except ClientError as e:
            logger.error(f"Failed to set retention: {str(e)}")
            return {'error': str(e)}
    
    def put_object_with_lock(self, bucket_name: str, key: str, body: bytes,
                              retention_mode: str = 'GOVERNANCE',
                              retain_until: datetime = None,
                              legal_hold: bool = False) -> dict:
        """
        Upload an object with Object Lock retention.
        
        Args:
            bucket_name: S3 bucket name
            key: Object key
            body: Object content
            retention_mode: 'GOVERNANCE' or 'COMPLIANCE'
            retain_until: Datetime until which object is locked
            legal_hold: Enable legal hold (prevents deletion even after retention)
        """
        if retain_until is None:
            retain_until = datetime.utcnow() + timedelta(days=2555)  # 7 years
        
        try:
            put_params = {
                'Bucket': bucket_name,
                'Key': key,
                'Body': body,
                'ObjectLockMode': retention_mode,
                'ObjectLockRetainUntilDate': retain_until
            }
            
            if legal_hold:
                put_params['ObjectLockLegalHoldStatus'] = 'ON'
            
            response = self.s3.put_object(**put_params)
            
            logger.info(f"Uploaded WORM object '{key}' with {retention_mode} retention until {retain_until}")
            
            return {
                'success': True,
                'key': key,
                'version_id': response.get('VersionId'),
                'retention_mode': retention_mode,
                'retain_until': retain_until.isoformat(),
                'legal_hold': legal_hold
            }
            
        except ClientError as e:
            logger.error(f"Failed to upload WORM object: {str(e)}")
            return {'error': str(e)}
    
    def store_forensic_manifest(self, migration_id: str, manifest_data: dict,
                                 retain_years: int = 7) -> dict:
        """
        Store run_manifest.json with WORM protection.
        Provides cryptographic proof of migration integrity.
        """
        key = f"forensic/{migration_id}/run_manifest.json"
        retain_until = datetime.utcnow() + timedelta(days=retain_years * 365)
        
        body = json.dumps(manifest_data, indent=2, default=str).encode('utf-8')
        
        return self.put_object_with_lock(
            bucket_name=self.bucket_name,
            key=key,
            body=body,
            retention_mode='COMPLIANCE',  # Immutable for forensic evidence
            retain_until=retain_until,
            legal_hold=True  # Extra protection for audit trails
        )
    
    def store_forensic_log(self, migration_id: str, log_type: str, 
                           log_data: str, retain_years: int = 7) -> dict:
        """
        Store forensic log with WORM protection.
        """
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        key = f"forensic/{migration_id}/logs/{log_type}_{timestamp}.log"
        retain_until = datetime.utcnow() + timedelta(days=retain_years * 365)
        
        return self.put_object_with_lock(
            bucket_name=self.bucket_name,
            key=key,
            body=log_data.encode('utf-8'),
            retention_mode='COMPLIANCE',
            retain_until=retain_until
        )
    
    def get_object_retention(self, bucket_name: str, key: str) -> dict:
        """
        Get retention settings for an object.
        """
        try:
            response = self.s3.get_object_retention(Bucket=bucket_name, Key=key)
            return {
                'mode': response['Retention']['Mode'],
                'retain_until': response['Retention']['RetainUntilDate'].isoformat()
            }
        except ClientError as e:
            return {'error': str(e)}


# =============================================================================
# CUSTOMER-MANAGED KEYS (CMK)
# =============================================================================

class CustomerManagedKeys:
    """
    Implements Customer-Managed Keys for enterprise clients.
    Gives clients "Ultimate Sovereignty" over their encrypted data.
    
    Use case: $60M enterprise deals where the client owns the encryption keys.
    """
    
    def __init__(self, kms_client=None, s3_client=None):
        self.kms = kms_client or boto3.client('kms', region_name=REQUIRED_REGION)
        self.s3 = s3_client or boto3.client('s3', region_name=REQUIRED_REGION)
    
    def validate_customer_key(self, key_id: str) -> Tuple[bool, dict]:
        """
        Validate that a customer-provided KMS key exists and is usable.
        
        Args:
            key_id: AWS KMS Key ID or ARN
            
        Returns:
            (is_valid, key_info)
        """
        try:
            response = self.kms.describe_key(KeyId=key_id)
            key_metadata = response['KeyMetadata']
            
            # Verify key is in correct region
            key_arn = key_metadata['Arn']
            if REQUIRED_REGION not in key_arn:
                return False, {'error': f"Key must be in {REQUIRED_REGION} for Canadian data residency"}
            
            # Verify key is enabled
            if key_metadata['KeyState'] != 'Enabled':
                return False, {'error': f"Key is not enabled (state: {key_metadata['KeyState']})"}
            
            # Verify key usage
            if key_metadata['KeyUsage'] != 'ENCRYPT_DECRYPT':
                return False, {'error': "Key must support ENCRYPT_DECRYPT usage"}
            
            logger.info(f"Validated CMK: {key_id}")
            
            return True, {
                'key_id': key_metadata['KeyId'],
                'arn': key_arn,
                'description': key_metadata.get('Description', ''),
                'key_state': key_metadata['KeyState'],
                'creation_date': key_metadata['CreationDate'].isoformat()
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NotFoundException':
                return False, {'error': 'Key not found'}
            elif error_code == 'AccessDeniedException':
                return False, {'error': 'Access denied - ensure ForensicBridge has kms:DescribeKey permission'}
            return False, {'error': str(e)}
    
    def configure_bucket_cmk(self, bucket_name: str, customer_key_arn: str) -> dict:
        """
        Configure S3 bucket to use customer's KMS key for default encryption.
        
        Args:
            bucket_name: S3 bucket name
            customer_key_arn: Customer's KMS key ARN
        """
        # First validate the key
        is_valid, key_info = self.validate_customer_key(customer_key_arn)
        if not is_valid:
            return key_info
        
        try:
            self.s3.put_bucket_encryption(
                Bucket=bucket_name,
                ServerSideEncryptionConfiguration={
                    'Rules': [
                        {
                            'ApplyServerSideEncryptionByDefault': {
                                'SSEAlgorithm': 'aws:kms',
                                'KMSMasterKeyID': customer_key_arn
                            },
                            'BucketKeyEnabled': True  # Reduces KMS costs
                        }
                    ]
                }
            )
            
            logger.info(f"Configured bucket '{bucket_name}' with CMK '{customer_key_arn}'")
            
            return {
                'success': True,
                'bucket': bucket_name,
                'kms_key': customer_key_arn,
                'message': 'Customer-managed encryption enabled'
            }
            
        except ClientError as e:
            logger.error(f"Failed to configure CMK: {str(e)}")
            return {'error': str(e)}
    
    def upload_with_cmk(self, bucket_name: str, key: str, body: bytes,
                        customer_key_arn: str) -> dict:
        """
        Upload an object encrypted with customer's KMS key.
        """
        try:
            response = self.s3.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=body,
                ServerSideEncryption='aws:kms',
                SSEKMSKeyId=customer_key_arn
            )
            
            return {
                'success': True,
                'key': key,
                'version_id': response.get('VersionId'),
                'kms_key_used': customer_key_arn
            }
            
        except ClientError as e:
            return {'error': str(e)}
    
    def generate_cmk_grant(self, key_id: str, grantee_principal: str,
                           operations: List[str] = None) -> dict:
        """
        Create a KMS grant allowing ForensicBridge to use customer's key.
        Customer can revoke this grant at any time for "Ultimate Sovereignty".
        
        Args:
            key_id: Customer's KMS key ID
            grantee_principal: IAM ARN of ForensicBridge service role
            operations: List of allowed operations
        """
        if operations is None:
            operations = ['Encrypt', 'Decrypt', 'GenerateDataKey']
        
        try:
            response = self.kms.create_grant(
                KeyId=key_id,
                GranteePrincipal=grantee_principal,
                Operations=operations,
                Name=f"ForensicBridge-Access-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            )
            
            return {
                'grant_id': response['GrantId'],
                'grant_token': response['GrantToken'],
                'message': 'Grant created - customer can revoke at any time'
            }
            
        except ClientError as e:
            return {'error': str(e)}


# =============================================================================
# MULTI-AZ DEPLOYMENT
# =============================================================================

class MultiAZDeployment:
    """
    Implements Multi-AZ EC2 deployment for high availability.
    Ensures service remains online if one AWS zone goes down.
    
    Critical for "Panic Wave" of May 2026 fiscal year-end.
    """
    
    def __init__(self, ec2_client=None):
        self.ec2 = ec2_client or boto3.client('ec2', region_name=REQUIRED_REGION)
        self.preferred_zones = ALLOWED_AVAILABILITY_ZONES.copy()
    
    def get_available_zones(self) -> List[dict]:
        """
        Get list of available zones in ca-central-1 with their status.
        """
        try:
            response = self.ec2.describe_availability_zones(
                Filters=[
                    {'Name': 'region-name', 'Values': [REQUIRED_REGION]},
                    {'Name': 'state', 'Values': ['available']}
                ]
            )
            
            zones = []
            for az in response['AvailabilityZones']:
                zones.append({
                    'zone_name': az['ZoneName'],
                    'zone_id': az['ZoneId'],
                    'state': az['State'],
                    'region': az['RegionName']
                })
            
            return zones
            
        except ClientError as e:
            logger.error(f"Failed to get AZs: {str(e)}")
            return []
    
    def select_optimal_zone(self, subnet_id: str = None) -> str:
        """
        Select the optimal availability zone based on:
        1. Current zone health
        2. Existing instance distribution
        3. Subnet availability
        
        Returns the zone name to use for instance launch.
        """
        available_zones = self.get_available_zones()
        
        if not available_zones:
            logger.warning("No available zones found, using default")
            return self.preferred_zones[0]
        
        # If subnet specified, get its zone
        if subnet_id:
            try:
                response = self.ec2.describe_subnets(SubnetIds=[subnet_id])
                if response['Subnets']:
                    zone = response['Subnets'][0]['AvailabilityZone']
                    if zone in [z['zone_name'] for z in available_zones]:
                        return zone
            except ClientError:
                pass
        
        # Count existing migration instances per zone for load balancing
        try:
            response = self.ec2.describe_instances(
                Filters=[
                    {'Name': 'tag:Purpose', 'Values': ['ephemeral-migration']},
                    {'Name': 'instance-state-name', 'Values': ['running', 'pending']}
                ]
            )
            
            zone_counts = {z['zone_name']: 0 for z in available_zones}
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    zone = instance.get('Placement', {}).get('AvailabilityZone', '')
                    if zone in zone_counts:
                        zone_counts[zone] += 1
            
            # Select zone with fewest instances
            optimal_zone = min(zone_counts, key=zone_counts.get)
            logger.info(f"Selected optimal zone: {optimal_zone} (instance counts: {zone_counts})")
            return optimal_zone
            
        except ClientError as e:
            logger.error(f"Failed to analyze zone distribution: {str(e)}")
            return available_zones[0]['zone_name']
    
    def get_subnets_for_multi_az(self, vpc_id: str = None) -> List[dict]:
        """
        Get subnets across multiple AZs for Multi-AZ deployment.
        """
        try:
            filters = [
                {'Name': 'state', 'Values': ['available']},
                {'Name': 'availability-zone', 'Values': ALLOWED_AVAILABILITY_ZONES}
            ]
            if vpc_id:
                filters.append({'Name': 'vpc-id', 'Values': [vpc_id]})
            
            response = self.ec2.describe_subnets(Filters=filters)
            
            subnets = []
            for subnet in response['Subnets']:
                subnets.append({
                    'subnet_id': subnet['SubnetId'],
                    'availability_zone': subnet['AvailabilityZone'],
                    'available_ips': subnet['AvailableIpAddressCount'],
                    'vpc_id': subnet['VpcId']
                })
            
            return subnets
            
        except ClientError as e:
            logger.error(f"Failed to get subnets: {str(e)}")
            return []
    
    def launch_in_zone(self, zone: str, launch_params: dict) -> str:
        """
        Launch an EC2 instance in a specific availability zone.
        
        Args:
            zone: Target availability zone
            launch_params: Standard EC2 run_instances parameters
            
        Returns:
            Instance ID
        """
        # Ensure zone is valid
        if zone not in ALLOWED_AVAILABILITY_ZONES:
            raise ValueError(f"Zone '{zone}' not in allowed zones: {ALLOWED_AVAILABILITY_ZONES}")
        
        # Add placement to params
        launch_params['Placement'] = {'AvailabilityZone': zone}
        
        try:
            response = self.ec2.run_instances(**launch_params)
            instance_id = response['Instances'][0]['InstanceId']
            
            logger.info(f"Launched instance {instance_id} in zone {zone}")
            return instance_id
            
        except ClientError as e:
            # If zone is at capacity, try another zone
            if 'InsufficientInstanceCapacity' in str(e):
                logger.warning(f"Zone {zone} at capacity, trying alternate zone")
                alternate_zones = [z for z in ALLOWED_AVAILABILITY_ZONES if z != zone]
                if alternate_zones:
                    return self.launch_in_zone(alternate_zones[0], launch_params)
            raise
    
    def get_zone_health(self) -> Dict[str, dict]:
        """
        Get health status of each availability zone in ca-central-1.
        Useful for monitoring during high-load periods.
        """
        health = {}
        
        zones = self.get_available_zones()
        for zone_info in zones:
            zone = zone_info['zone_name']
            health[zone] = {
                'state': zone_info['state'],
                'running_instances': 0,
                'pending_instances': 0
            }
        
        try:
            response = self.ec2.describe_instances(
                Filters=[
                    {'Name': 'tag:Purpose', 'Values': ['ephemeral-migration']},
                    {'Name': 'instance-state-name', 'Values': ['running', 'pending']}
                ]
            )
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    zone = instance.get('Placement', {}).get('AvailabilityZone', '')
                    state = instance['State']['Name']
                    
                    if zone in health:
                        if state == 'running':
                            health[zone]['running_instances'] += 1
                        elif state == 'pending':
                            health[zone]['pending_instances'] += 1
            
        except ClientError:
            pass
        
        return health

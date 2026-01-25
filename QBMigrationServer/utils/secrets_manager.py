"""
AWS Secrets Manager Integration for ForensicBridge
Production-grade secrets management to replace .env file usage.

Usage:
    from utils.secrets_manager import get_secret, get_all_secrets
    
    # Get a single secret
    db_password = get_secret('database_password')
    
    # Get all secrets as dict
    secrets = get_all_secrets()
"""

import os
import json
import logging
from functools import lru_cache
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SecretsManagerError(Exception):
    """Raised when secrets cannot be retrieved."""
    pass


def _get_boto3_client():
    """Get boto3 client with lazy import to avoid import errors when not using AWS."""
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
        return boto3.client(
            'secretsmanager',
            region_name=os.getenv('AWS_REGION', 'ca-central-1')
        )
    except ImportError:
        raise SecretsManagerError("boto3 not installed. Run: pip install boto3")


@lru_cache(maxsize=1)
def get_all_secrets(secret_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve all secrets from AWS Secrets Manager.
    
    Uses caching to avoid repeated API calls. Cache is cleared on module reload.
    
    Args:
        secret_name: Name of the secret in Secrets Manager. 
                     Defaults to SECRETS_MANAGER_NAME env var or 'forensicbridge/production'.
    
    Returns:
        Dictionary of secret key-value pairs.
        
    Raises:
        SecretsManagerError: If secrets cannot be retrieved.
    """
    # In development mode, fall back to environment variables
    if os.getenv('FLASK_ENV', 'development') == 'development':
        logger.info("Development mode: Using environment variables instead of Secrets Manager")
        return _get_env_secrets()
    
    secret_name = secret_name or os.getenv(
        'SECRETS_MANAGER_NAME', 
        'forensicbridge/production'
    )
    
    try:
        from botocore.exceptions import ClientError, NoCredentialsError
        
        client = _get_boto3_client()
        response = client.get_secret_value(SecretId=secret_name)
        
        if 'SecretString' in response:
            secrets = json.loads(response['SecretString'])
            logger.info(f"Successfully loaded {len(secrets)} secrets from Secrets Manager")
            return secrets
        else:
            # Binary secret
            raise SecretsManagerError("Binary secrets not supported")
            
    except NoCredentialsError:
        logger.warning("No AWS credentials found. Falling back to environment variables.")
        return _get_env_secrets()
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            logger.warning(f"Secret '{secret_name}' not found. Falling back to environment variables.")
            return _get_env_secrets()
        elif error_code == 'AccessDeniedException':
            logger.error(f"Access denied to secret '{secret_name}'. Check IAM permissions.")
            raise SecretsManagerError(f"Access denied: {e}")
        else:
            logger.error(f"Error retrieving secret: {e}")
            raise SecretsManagerError(f"Failed to retrieve secret: {e}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving secrets: {e}")
        raise SecretsManagerError(f"Unexpected error: {e}")


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a single secret value by key.
    
    Args:
        key: The secret key to retrieve.
        default: Default value if key not found.
        
    Returns:
        The secret value or default.
    """
    try:
        secrets = get_all_secrets()
        return secrets.get(key, default)
    except SecretsManagerError:
        # Fall back to environment variable
        return os.getenv(key, default)


def _get_env_secrets() -> Dict[str, Any]:
    """
    Get secrets from environment variables as fallback.
    Maps common secret names to their env var equivalents.
    """
    return {
        # Flask
        'flask_secret_key': os.getenv('SECRET_KEY', ''),
        'flask_env': os.getenv('FLASK_ENV', 'development'),
        
        # Database
        'database_url': os.getenv('DATABASE_URL', ''),
        
        # AWS
        'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID', ''),
        'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY', ''),
        'aws_region': os.getenv('AWS_REGION', 'ca-central-1'),
        'aws_s3_bucket': os.getenv('AWS_S3_BUCKET', ''),
        
        # QuickBooks Online
        'qbo_client_id': os.getenv('QBO_CLIENT_ID', ''),
        'qbo_client_secret': os.getenv('QBO_CLIENT_SECRET', ''),
        'qbo_refresh_token': os.getenv('QBO_REFRESH_TOKEN', ''),
        'qbo_realm_id': os.getenv('QBO_REALM_ID', ''),
        
        # Webhooks
        'webhook_secret': os.getenv('WEBHOOK_SECRET', ''),
        
        # Encryption
        'backup_encryption_key': os.getenv('BACKUP_ENCRYPTION_KEY', ''),
        'encryption_password': os.getenv('ENCRYPTION_PASSWORD', ''),
    }


def clear_cache():
    """Clear the secrets cache. Useful for testing or when secrets are rotated."""
    get_all_secrets.cache_clear()
    logger.info("Secrets cache cleared")


def validate_required_secrets(required_keys: list) -> Dict[str, bool]:
    """
    Validate that all required secrets are present.
    
    Args:
        required_keys: List of secret keys that must be present.
        
    Returns:
        Dict mapping each key to True if present, False otherwise.
    """
    secrets = get_all_secrets()
    result = {}
    missing = []
    
    for key in required_keys:
        present = bool(secrets.get(key))
        result[key] = present
        if not present:
            missing.append(key)
    
    if missing:
        logger.warning(f"Missing required secrets: {missing}")
    
    return result


# Production secrets template for AWS Secrets Manager
SECRETS_TEMPLATE = """
{
    "flask_secret_key": "YOUR_256_BIT_SECRET_KEY",
    "database_url": "postgresql://user:password@host:5432/database",
    "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "aws_region": "ca-central-1",
    "aws_s3_bucket": "forensicbridge-prod-migrations",
    "qbo_client_id": "YOUR_QBO_CLIENT_ID",
    "qbo_client_secret": "YOUR_QBO_CLIENT_SECRET",
    "qbo_refresh_token": "YOUR_QBO_REFRESH_TOKEN",
    "qbo_realm_id": "YOUR_COMPANY_ID",
    "webhook_secret": "YOUR_WEBHOOK_SECRET",
    "backup_encryption_key": "YOUR_BACKUP_KEY",
    "encryption_password": "YOUR_ENCRYPTION_PASSWORD"
}
"""


if __name__ == '__main__':
    # Test the secrets manager
    logger.info("Testing Secrets Manager...")
    logger.info(f"Flask ENV: {os.getenv('FLASK_ENV', 'development')}")
    
    try:
        secrets = get_all_secrets()
        logger.info(f"Loaded {len(secrets)} secrets")
        
        # Validate required secrets for production
        required = ['flask_secret_key', 'database_url', 'aws_s3_bucket']
        validation = validate_required_secrets(required)
        
        for key, present in validation.items():
            status = "✅" if present else "❌"
            logger.info(f"  {status} {key}")
            
    except SecretsManagerError as e:
        logger.error(f"Error: {e}")

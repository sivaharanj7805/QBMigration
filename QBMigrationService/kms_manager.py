"""
AWS Key Management Service (KMS) Integration
=============================================
Hardware-backed encryption key management for enterprise security.
Replaces local .pem files with AWS KMS envelope encryption.
"""

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, Tuple

# AWS SDK
try:
    import boto3
    from botocore.exceptions import ClientError

    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False
    boto3 = None
    ClientError = Exception

logger = logging.getLogger(__name__)


class AWSKMSManager:
    """
    AWS Key Management Service integration for ForensicBridge.

    Features:
    - Envelope encryption (data key encrypted by master key)
    - Automatic key rotation
    - Hardware Security Module (HSM) backed keys
    - Audit logging via CloudTrail

    Security Model:
    1. Master Key (CMK) stays in AWS KMS (never leaves)
    2. Data Key generated per migration
    3. Data Key encrypted by CMK for storage
    4. Data encrypted with plaintext Data Key
    5. Plaintext Data Key discarded after use
    """

    def __init__(
        self,
        region: str = None,
        key_alias: str = "alias/forensicbridge-master",
        access_key_id: str = None,
        secret_access_key: str = None,
        tenant_id: str = None,
    ):
        """
        Initialize KMS manager.

        Args:
            region: AWS region (default: from environment)
            key_alias: KMS key alias (overridden if tenant_id is provided)
            access_key_id: Optional AWS access key (default: from environment)
            secret_access_key: Optional AWS secret key (default: from environment)
            tenant_id: Optional tenant ID for per-tenant key isolation (ADV-02)
        """
        if not AWS_AVAILABLE:
            raise ImportError(
                "boto3 is required for KMS integration. "
                "Install with: pip install boto3"
            )

        self.region = region or os.environ.get("AWS_REGION", "ca-central-1")

        # ADV-02: Validate tenant_id to prevent alias injection
        if tenant_id:
            if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", tenant_id):
                raise ValueError(
                    "Invalid tenant_id: must be 1-64 alphanumeric, "
                    "hyphen, or underscore characters"
                )
        self.tenant_id = tenant_id

        # ADV-02: Per-tenant key isolation
        # Each tenant gets their own KMS CMK for data isolation
        if (
            tenant_id
            and os.environ.get("ENABLE_TENANT_KEY_ISOLATION", "false").lower() == "true"
        ):
            self.key_alias = f"alias/forensicbridge-tenant-{tenant_id}"
        else:
            self.key_alias = key_alias

        # ADV-03: HSM-backed key configuration
        self.hsm_enabled = os.environ.get("KMS_HSM_ENABLED", "false").lower() == "true"

        # Initialize KMS client
        session_kwargs = {"region_name": self.region}

        if access_key_id and secret_access_key:
            session_kwargs["aws_access_key_id"] = access_key_id
            session_kwargs["aws_secret_access_key"] = secret_access_key

        self.kms_client = boto3.client("kms", **session_kwargs)
        self.key_id = None

        # Cache the key ID
        self._resolve_key_id()

    def _resolve_key_id(self):
        """Resolve key alias to key ID."""
        try:
            response = self.kms_client.describe_key(KeyId=self.key_alias)
            self.key_id = response["KeyMetadata"]["KeyId"]
            logger.info(f"KMS key resolved: {self.key_id[:8]}...")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NotFoundException":
                logger.warning(f"KMS key {self.key_alias} not found. Creating...")
                self._create_key()
            else:
                raise

    def _create_key(self):
        """Create a new KMS customer master key.

        ADV-02: Supports per-tenant keys with TenantId tag.
        ADV-03: Supports HSM-backed keys via CUSTOM_KEY_STORE_ID.
        """
        try:
            tags = [
                {"TagKey": "Application", "TagValue": "ForensicBridge"},
                {
                    "TagKey": "Environment",
                    "TagValue": os.environ.get("ENV", "production"),
                },
            ]

            # ADV-02: Tag tenant-specific keys for isolation tracking
            if self.tenant_id:
                tags.append({"TagKey": "TenantId", "TagValue": self.tenant_id})
                description = (
                    f"ForensicBridge Encryption Key (Tenant: {self.tenant_id})"
                )
            else:
                description = "ForensicBridge Migration Encryption Key"

            create_params = {
                "Description": description,
                "KeyUsage": "ENCRYPT_DECRYPT",
                "Origin": "AWS_KMS",
                "Tags": tags,
            }

            # ADV-03: HSM-backed keys via CloudHSM custom key store
            custom_key_store_id = os.environ.get("KMS_CUSTOM_KEY_STORE_ID")
            if self.hsm_enabled and custom_key_store_id:
                create_params["Origin"] = "AWS_CLOUDHSM"
                create_params["CustomKeyStoreId"] = custom_key_store_id
                logger.info("Creating HSM-backed KMS key via CloudHSM")

            response = self.kms_client.create_key(**create_params)

            self.key_id = response["KeyMetadata"]["KeyId"]

            # Create alias
            self.kms_client.create_alias(
                AliasName=self.key_alias, TargetKeyId=self.key_id
            )

            # Enable automatic key rotation (annual)
            self.kms_client.enable_key_rotation(KeyId=self.key_id)

            logger.info(f"Created new KMS key: {self.key_id}")

        except ClientError as e:
            logger.error(f"Failed to create KMS key: {e}")
            raise

    def generate_data_key(self, context: Dict[str, str] = None) -> Tuple[bytes, bytes]:
        """
        Generate a new data encryption key.

        The returned tuple contains:
        - Plaintext key (use for encryption, then discard)
        - Encrypted key (store alongside encrypted data)

        Args:
            context: Encryption context for additional security.
                     ADV-02: Tenant ID is automatically injected if configured.

        Returns:
            Tuple of (plaintext_key, encrypted_key)
        """
        try:
            params = {"KeyId": self.key_id, "KeySpec": "AES_256"}  # 256-bit AES key

            # ADV-02: Inject tenant_id into encryption context for key isolation
            # Always enforce instance tenant_id to prevent cross-tenant access
            encryption_context = context.copy() if context else {}
            if self.tenant_id:
                if (
                    "tenant_id" in encryption_context
                    and encryption_context["tenant_id"] != self.tenant_id
                ):
                    logger.warning(
                        "Caller-provided tenant_id in encryption context "
                        "overridden for security"
                    )
                encryption_context["tenant_id"] = self.tenant_id

            if encryption_context:
                params["EncryptionContext"] = encryption_context

            response = self.kms_client.generate_data_key(**params)

            plaintext_key = response["Plaintext"]
            encrypted_key = response["CiphertextBlob"]

            logger.debug("Generated new data key")

            return plaintext_key, encrypted_key

        except ClientError as e:
            logger.error(f"Failed to generate data key: {e}")
            raise

    def decrypt_data_key(
        self, encrypted_key: bytes, context: Dict[str, str] = None
    ) -> bytes:
        """
        Decrypt a data key.

        Args:
            encrypted_key: The encrypted data key blob
            context: Must match the context used during generation

        Returns:
            Plaintext data key
        """
        try:
            params = {"CiphertextBlob": encrypted_key, "KeyId": self.key_id}

            if context:
                params["EncryptionContext"] = context

            response = self.kms_client.decrypt(**params)

            return response["Plaintext"]

        except ClientError as e:
            logger.error(f"Failed to decrypt data key: {e}")
            raise

    def encrypt_oauth_tokens(self, tokens: Dict) -> Dict:
        """
        Encrypt OAuth tokens for secure storage.

        Args:
            tokens: OAuth token dictionary

        Returns:
            Encrypted token bundle
        """
        context = {
            "purpose": "oauth_tokens",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Generate data key for this token set
        plaintext_key, encrypted_key = self.generate_data_key(context)

        # Encrypt tokens with data key using AES-256-GCM
        import os as _os

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(plaintext_key)
        nonce = _os.urandom(12)

        token_bytes = json.dumps(tokens).encode()
        ciphertext = aesgcm.encrypt(nonce, token_bytes, None)

        # SECURITY FIX: Securely zero plaintext key from memory
        # Setting to None does not overwrite the bytes object in CPython
        if isinstance(plaintext_key, (bytearray, memoryview)):
            for i in range(len(plaintext_key)):
                plaintext_key[i] = 0
        plaintext_key = None

        return {
            "encrypted_key": base64.b64encode(encrypted_key).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "context": context,
        }

    def decrypt_oauth_tokens(self, encrypted_bundle: Dict) -> Dict:
        """
        Decrypt OAuth tokens.

        Args:
            encrypted_bundle: Bundle from encrypt_oauth_tokens

        Returns:
            Decrypted token dictionary
        """
        encrypted_key = base64.b64decode(encrypted_bundle["encrypted_key"])
        nonce = base64.b64decode(encrypted_bundle["nonce"])
        ciphertext = base64.b64decode(encrypted_bundle["ciphertext"])
        context = encrypted_bundle.get("context")

        # Decrypt data key
        plaintext_key = self.decrypt_data_key(encrypted_key, context)

        # Decrypt tokens
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(plaintext_key)
        token_bytes = aesgcm.decrypt(nonce, ciphertext, None)

        # SECURITY FIX: Securely zero plaintext key from memory
        if isinstance(plaintext_key, (bytearray, memoryview)):
            for i in range(len(plaintext_key)):
                plaintext_key[i] = 0
        plaintext_key = None

        return json.loads(token_bytes.decode())

    def encrypt_migration_data(self, data: bytes, migration_id: str) -> Dict:
        """
        Encrypt migration data using envelope encryption.

        Args:
            data: Raw data to encrypt
            migration_id: Unique migration identifier

        Returns:
            Encrypted data bundle
        """
        context = {"migration_id": migration_id, "purpose": "migration_data"}

        plaintext_key, encrypted_key = self.generate_data_key(context)

        import os as _os

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(plaintext_key)
        nonce = _os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, data, migration_id.encode())

        plaintext_key = None

        return {
            "encrypted_key": base64.b64encode(encrypted_key).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "migration_id": migration_id,
            "algorithm": "AES-256-GCM",
            "kms_key_id": self.key_id[:8] + "...",
        }

    def decrypt_migration_data(self, encrypted_bundle: Dict) -> bytes:
        """
        Decrypt migration data.

        Args:
            encrypted_bundle: Bundle from encrypt_migration_data

        Returns:
            Decrypted data bytes
        """
        migration_id = encrypted_bundle["migration_id"]
        context = {"migration_id": migration_id, "purpose": "migration_data"}

        encrypted_key = base64.b64decode(encrypted_bundle["encrypted_key"])
        nonce = base64.b64decode(encrypted_bundle["nonce"])
        ciphertext = base64.b64decode(encrypted_bundle["ciphertext"])

        plaintext_key = self.decrypt_data_key(encrypted_key, context)

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(plaintext_key)
        data = aesgcm.decrypt(nonce, ciphertext, migration_id.encode())

        plaintext_key = None

        return data


class KMSFallbackManager:
    """
    Fallback encryption manager when AWS KMS is not available.
    Uses local keys but with same interface.
    """

    def __init__(self):
        self.local_key = None
        self._load_or_generate_key()

    def _load_or_generate_key(self):
        """Load or generate a local master key."""
        # SECURITY FIX: Use secure absolute path instead of relative CWD
        key_path = os.environ.get("LOCAL_MASTER_KEY_PATH", "/var/lib/forensicbridge/.master_key")

        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                self.local_key = f.read()
        else:
            import os as _os

            self.local_key = _os.urandom(32)
            # HIGH-03 FIX: Write key with restrictive 0600 permissions
            fd = _os.open(key_path, _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC, 0o600)
            try:
                _os.write(fd, self.local_key)
            finally:
                _os.close(fd)
            logger.warning(
                "Generated local master key. " "For production, use AWS KMS instead."
            )

    def generate_data_key(self, context: Dict = None) -> Tuple[bytes, bytes]:
        """Generate data key using local key."""
        import os as _os

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        # Generate random data key
        data_key = _os.urandom(32)

        # Encrypt with local master key
        aesgcm = AESGCM(self.local_key)
        nonce = _os.urandom(12)

        context_bytes = json.dumps(context or {}).encode()
        encrypted = aesgcm.encrypt(nonce, data_key, context_bytes)

        # Pack nonce + ciphertext
        encrypted_key = nonce + encrypted

        return data_key, encrypted_key

    def decrypt_data_key(self, encrypted_key: bytes, context: Dict = None) -> bytes:
        """Decrypt data key using local key."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = encrypted_key[:12]
        ciphertext = encrypted_key[12:]

        context_bytes = json.dumps(context or {}).encode()

        aesgcm = AESGCM(self.local_key)
        return aesgcm.decrypt(nonce, ciphertext, context_bytes)


def get_encryption_manager(use_kms: bool = None) -> object:
    """
    Factory function to get appropriate encryption manager.

    Args:
        use_kms: Force KMS (True) or local (False).
                 If None, auto-detect based on AWS credentials.

    Returns:
        AWSKMSManager or KMSFallbackManager
    """
    if use_kms is False:
        return KMSFallbackManager()

    if use_kms is True or AWS_AVAILABLE:
        try:
            return AWSKMSManager()
        except Exception as e:
            if use_kms is True:
                raise
            logger.warning(f"KMS not available, using local encryption: {e}")
            return KMSFallbackManager()

    return KMSFallbackManager()


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Test with fallback (local) manager
    manager = get_encryption_manager(use_kms=False)

    # Generate data key
    plaintext, encrypted = manager.generate_data_key({"test": "context"})
    logger.info(f"Generated key length: {len(plaintext)} bytes")
    logger.info(f"Encrypted key length: {len(encrypted)} bytes")

    # Decrypt and verify
    decrypted = manager.decrypt_data_key(encrypted, {"test": "context"})
    assert decrypted == plaintext
    logger.info("Key encryption/decryption successful!")

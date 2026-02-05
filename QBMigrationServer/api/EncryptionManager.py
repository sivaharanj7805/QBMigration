"""
Server-Side Encryption Manager
- RSA-4096 key pair generation and management
- AES-256-GCM decryption
- Hybrid encryption/decryption
- Compatible with C# QBExtractor v3.1
"""

import base64
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# KEY ROTATION CONFIGURATION
# Maximum age of a key before rotation is recommended (90 days = PCI-DSS compliant)
KEY_ROTATION_DAYS = int(os.getenv("KEY_ROTATION_DAYS", "90"))
# Maximum number of archived key versions to keep
MAX_ARCHIVED_KEYS = int(os.getenv("MAX_ARCHIVED_KEYS", "5"))


class EncryptionManager:
    """
    Server-side encryption manager
    Handles RSA key pair and AES decryption with key rotation support.

    Key Rotation Features:
    - Versioned keys with creation timestamps
    - Automatic detection of keys needing rotation
    - Archive of old keys for decrypting legacy data
    - Configurable rotation period (default: 90 days per PCI-DSS)
    """

    def __init__(self, key_dir=None):
        """
        Initialize encryption manager

        Args:
            key_dir: Directory to store RSA keys (default: ./keys)
        """
        self.key_dir = key_dir or os.path.join(os.getcwd(), "keys")
        self.archive_dir = os.path.join(self.key_dir, "archive")
        os.makedirs(self.key_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)

        self.private_key_path = os.path.join(self.key_dir, "rsa_private.pem")
        self.public_key_path = os.path.join(self.key_dir, "rsa_public.pem")
        self.key_metadata_path = os.path.join(self.key_dir, "key_metadata.json")

        # Load or generate keys
        self.private_key, self.key_version = self._load_or_generate_keys()
        self.public_key = self.private_key.public_key()

        # Cache of archived keys for decrypting old data
        self._archived_keys: Dict[str, Any] = {}

    def _load_key_metadata(self) -> Dict:
        """Load key metadata from JSON file."""
        if os.path.exists(self.key_metadata_path):
            try:
                with open(self.key_metadata_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load key metadata: {e}")
        return {}

    def _save_key_metadata(self, metadata: Dict):
        """Save key metadata to JSON file."""
        try:
            with open(self.key_metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save key metadata: {e}")
            raise

    def _load_or_generate_keys(self) -> Tuple[Any, str]:
        """Load existing RSA keys or generate new ones with versioning."""
        metadata = self._load_key_metadata()

        if os.path.exists(self.private_key_path):
            # Load existing keys
            try:
                with open(self.private_key_path, "rb") as f:
                    private_key = serialization.load_pem_private_key(
                        f.read(), password=None, backend=default_backend()
                    )

                version = metadata.get("current_version", "v1")
                created_at = metadata.get("created_at", "unknown")
                logger.info(
                    f"Loaded existing RSA-4096 key pair (version: {version}, created: {created_at})"
                )

                # Check if key rotation is needed
                self._check_rotation_needed(metadata)

                return private_key, version
            except Exception as e:
                logger.warning(f"Failed to load keys: {e}. Generating new keys...")

        # Generate new keys with versioning
        return self._generate_new_keypair()

    def _generate_new_keypair(self, is_rotation: bool = False) -> Tuple[Any, str]:
        """Generate a new RSA-4096 key pair with versioning."""
        logger.info("Generating new RSA-4096 key pair (this may take a moment)...")

        # Determine new version
        metadata = self._load_key_metadata()
        current_version = metadata.get("current_version", "v0")
        version_num = int(current_version[1:]) if current_version.startswith("v") else 0
        new_version = f"v{version_num + 1}"

        # Generate key
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=4096, backend=default_backend()
        )
        public_key = private_key.public_key()

        # Save private key
        with open(self.private_key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Save public key
        with open(self.public_key_path, "wb") as f:
            f.write(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

        # Update metadata
        now = datetime.now(timezone.utc).isoformat() + "Z"
        new_metadata = {
            "current_version": new_version,
            "created_at": now,
            "rotation_due_at": None,  # Calculated on next check
            "key_size": 4096,
            "algorithm": "RSA-OAEP-SHA256",
        }

        if is_rotation:
            new_metadata["rotated_from"] = current_version
            new_metadata["rotation_date"] = now
            logger.info(f"Key rotated from {current_version} to {new_version}")
        else:
            logger.info(f"RSA-4096 key pair generated (version: {new_version})")

        self._save_key_metadata(new_metadata)
        return private_key, new_version

    def _check_rotation_needed(self, metadata: Dict):
        """Log warning if key rotation is needed based on age."""
        created_at = metadata.get("created_at")
        if not created_at:
            return

        try:
            created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_days = (
                datetime.now(timezone.utc).replace(tzinfo=created_date.tzinfo)
                - created_date
            ).days

            if age_days >= KEY_ROTATION_DAYS:
                logger.warning(
                    f"SECURITY: RSA key is {age_days} days old (limit: {KEY_ROTATION_DAYS} days). "
                    f"Key rotation is recommended. Call rotate_keys() to rotate."
                )
            elif age_days >= KEY_ROTATION_DAYS - 14:
                logger.info(
                    f"Key rotation due in {KEY_ROTATION_DAYS - age_days} days "
                    f"(key age: {age_days} days)"
                )
        except Exception as e:
            logger.warning(f"Could not check key age: {e}")

    def rotate_keys(self) -> Dict:
        """
        Rotate RSA keys - archive current key and generate new one.

        This operation:
        1. Archives the current private key with version suffix
        2. Generates a new RSA-4096 key pair
        3. Updates key metadata
        4. Prunes old archived keys beyond MAX_ARCHIVED_KEYS

        Returns:
            Dict with rotation details: old_version, new_version, archived_path
        """
        metadata = self._load_key_metadata()
        old_version = metadata.get("current_version", "v1")

        # Archive current keys
        archive_path = None
        if os.path.exists(self.private_key_path):
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            archive_name = f"rsa_private_{old_version}_{timestamp}.pem"
            archive_path = os.path.join(self.archive_dir, archive_name)

            shutil.copy2(self.private_key_path, archive_path)
            logger.info(f"Archived old private key to: {archive_name}")

            # Also archive public key for completeness
            if os.path.exists(self.public_key_path):
                pub_archive_name = f"rsa_public_{old_version}_{timestamp}.pem"
                shutil.copy2(
                    self.public_key_path,
                    os.path.join(self.archive_dir, pub_archive_name),
                )

        # Generate new keys
        self.private_key, self.key_version = self._generate_new_keypair(
            is_rotation=True
        )
        self.public_key = self.private_key.public_key()

        # Prune old archived keys
        self._prune_archived_keys()

        # Clear archived keys cache
        self._archived_keys = {}

        result = {
            "success": True,
            "old_version": old_version,
            "new_version": self.key_version,
            "archived_path": archive_path,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

        logger.info(f"Key rotation complete: {old_version} -> {self.key_version}")
        return result

    def _prune_archived_keys(self):
        """Remove archived keys beyond MAX_ARCHIVED_KEYS limit."""
        try:
            archived_files = sorted(
                [
                    f
                    for f in os.listdir(self.archive_dir)
                    if f.startswith("rsa_private_")
                ],
                reverse=True,  # Newest first
            )

            # Keep only MAX_ARCHIVED_KEYS versions
            files_to_remove = archived_files[MAX_ARCHIVED_KEYS:]
            for filename in files_to_remove:
                filepath = os.path.join(self.archive_dir, filename)
                os.remove(filepath)
                logger.info(f"Pruned old archived key: {filename}")

                # Also remove corresponding public key if exists
                pub_filename = filename.replace("private", "public")
                pub_filepath = os.path.join(self.archive_dir, pub_filename)
                if os.path.exists(pub_filepath):
                    os.remove(pub_filepath)

        except Exception as e:
            logger.warning(f"Failed to prune archived keys: {e}")

    def get_key_status(self) -> Dict:
        """
        Get current key status for monitoring/compliance.

        Returns:
            Dict with key status: version, age_days, rotation_needed, etc.
        """
        metadata = self._load_key_metadata()
        created_at = metadata.get("created_at", "unknown")

        age_days = None
        rotation_needed = False

        if created_at != "unknown":
            try:
                created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days = (
                    datetime.now(timezone.utc).replace(tzinfo=created_date.tzinfo)
                    - created_date
                ).days
                rotation_needed = age_days >= KEY_ROTATION_DAYS
            except Exception as e:
                logger.warning(f"Failed to parse key creation date: {e}")

        # Count archived keys
        archived_count = 0
        try:
            archived_count = len(
                [
                    f
                    for f in os.listdir(self.archive_dir)
                    if f.startswith("rsa_private_")
                ]
            )
        except Exception as e:
            logger.warning(f"Failed to count archived keys: {e}")

        return {
            "version": self.key_version,
            "created_at": created_at,
            "age_days": age_days,
            "rotation_threshold_days": KEY_ROTATION_DAYS,
            "rotation_needed": rotation_needed,
            "rotation_due_in_days": (
                max(0, KEY_ROTATION_DAYS - (age_days or 0)) if age_days else None
            ),
            "algorithm": "RSA-4096 OAEP-SHA256",
            "archived_key_count": archived_count,
            "max_archived_keys": MAX_ARCHIVED_KEYS,
        }

    def decrypt_with_archived_key(
        self, encrypted_aes_key_b64: str, key_version: str
    ) -> bytes:
        """
        Decrypt AES key using an archived RSA key (for old encrypted data).

        Args:
            encrypted_aes_key_b64: Base64-encoded encrypted AES key
            key_version: Version of the key used for encryption (e.g., 'v1')

        Returns:
            bytes: Decrypted AES key
        """
        # Check cache first
        if key_version in self._archived_keys:
            archived_key = self._archived_keys[key_version]
        else:
            # Find and load archived key
            archived_key = self._load_archived_key(key_version)
            if archived_key:
                self._archived_keys[key_version] = archived_key

        if not archived_key:
            raise ValueError(f"Archived key version '{key_version}' not found")

        # Decrypt with archived key
        encrypted_aes_key = base64.b64decode(encrypted_aes_key_b64)
        aes_key = archived_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return aes_key

    def _load_archived_key(self, version: str):
        """Load an archived private key by version."""
        try:
            # Find matching archived key file
            for filename in os.listdir(self.archive_dir):
                if filename.startswith(f"rsa_private_{version}_"):
                    filepath = os.path.join(self.archive_dir, filename)
                    with open(filepath, "rb") as f:
                        return serialization.load_pem_private_key(
                            f.read(), password=None, backend=default_backend()
                        )
            return None
        except Exception as e:
            logger.error(f"Failed to load archived key {version}: {e}")
            return None

    def get_public_key_xml(self):
        """
        Get public key in XML format (compatible with C# RSACryptoServiceProvider)

        Returns:
            str: Public key in XML format
        """
        public_numbers = self.public_key.public_numbers()

        # Convert to base64
        modulus = base64.b64encode(
            public_numbers.n.to_bytes(
                (public_numbers.n.bit_length() + 7) // 8, byteorder="big"
            )
        ).decode("utf-8")

        exponent = base64.b64encode(
            public_numbers.e.to_bytes(
                (public_numbers.e.bit_length() + 7) // 8, byteorder="big"
            )
        ).decode("utf-8")

        # C# XML format
        xml = f"""<RSAKeyValue>
  <Modulus>{modulus}</Modulus>
  <Exponent>{exponent}</Exponent>
</RSAKeyValue>"""

        return xml

    def get_public_key_pem(self):
        """
        Get public key in PEM format

        Returns:
            str: Public key in PEM format
        """
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def decrypt_aes_key(self, encrypted_aes_key_b64):
        """
        Decrypt AES key using RSA private key

        Args:
            encrypted_aes_key_b64: Base64-encoded encrypted AES key

        Returns:
            bytes: Decrypted AES key (32 bytes)
        """
        try:
            # Decode base64
            encrypted_aes_key = base64.b64decode(encrypted_aes_key_b64)

            # Decrypt with RSA private key (OAEP padding)
            aes_key = self.private_key.decrypt(
                encrypted_aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            if len(aes_key) != 32:
                raise ValueError(
                    f"Invalid AES key length: {len(aes_key)} bytes (expected 32)"
                )

            return aes_key

        except Exception as e:
            logger.error(f"RSA decryption failed: {str(e)}")
            raise ValueError(f"Failed to decrypt AES key: {str(e)}")

    def decrypt_data(self, encrypted_data_b64, aes_key, iv_b64, tag_b64):
        """
        Decrypt data using AES-256-GCM

        Args:
            encrypted_data_b64: Base64-encoded encrypted data
            aes_key: AES key (32 bytes) - can be bytes or base64 string
            iv_b64: Base64-encoded IV/nonce (12 bytes)
            tag_b64: Base64-encoded authentication tag (16 bytes)

        Returns:
            bytes: Decrypted data
        """
        try:
            # Decode base64
            ciphertext = base64.b64decode(encrypted_data_b64)
            iv = base64.b64decode(iv_b64)
            tag = base64.b64decode(tag_b64)

            # Handle AES key (could be bytes or base64 string)
            if isinstance(aes_key, str):
                aes_key = base64.b64decode(aes_key)

            # Validate sizes
            if len(iv) != 12:
                raise ValueError(f"Invalid IV length: {len(iv)} bytes (expected 12)")
            if len(tag) != 16:
                raise ValueError(f"Invalid tag length: {len(tag)} bytes (expected 16)")
            if len(aes_key) != 32:
                raise ValueError(
                    f"Invalid AES key length: {len(aes_key)} bytes (expected 32)"
                )

            # Decrypt with AES-GCM
            aesgcm = AESGCM(aes_key)

            # GCM expects ciphertext + tag concatenated
            ciphertext_with_tag = ciphertext + tag

            plaintext = aesgcm.decrypt(iv, ciphertext_with_tag, None)

            return plaintext

        except Exception as e:
            logger.error(f"AES-GCM decryption failed: {str(e)}")
            raise ValueError(f"Failed to decrypt data: {str(e)}")

    def decrypt_qb_data(self, encryption_payload):
        """
        Decrypt QB data from client payload (v3.1 format)

        Args:
            encryption_payload: Dict with keys:
                - encrypted_data: base64 string
                - key: base64 string (if not RSA-encrypted) OR None
                - encrypted_key: base64 string (if RSA-encrypted) OR None
                - is_key_encrypted: bool
                - iv: base64 string
                - tag: base64 string

        Returns:
            str: Decrypted JSON data (as string)
        """
        try:
            encrypted_data = encryption_payload.get("encrypted_data")
            aes_key_b64 = encryption_payload.get("key")
            encrypted_aes_key_b64 = encryption_payload.get("encrypted_key")
            is_key_encrypted = encryption_payload.get("is_key_encrypted", False)
            iv = encryption_payload.get("iv")
            tag = encryption_payload.get("tag")

            # Validate required fields
            if not encrypted_data:
                raise ValueError("Missing encrypted_data")
            if not iv:
                raise ValueError("Missing IV")
            if not tag:
                raise ValueError("Missing authentication tag")
            if not aes_key_b64 and not encrypted_aes_key_b64:
                raise ValueError("Missing AES key (encrypted or plaintext)")

            # Get AES key
            if is_key_encrypted and encrypted_aes_key_b64:
                # Decrypt RSA-encrypted AES key
                logger.info("Decrypting RSA-encrypted AES key...")
                aes_key = self.decrypt_aes_key(encrypted_aes_key_b64)
            elif aes_key_b64:
                # Use plaintext AES key (sent via TLS)
                logger.info("Using TLS-protected AES key...")
                aes_key = base64.b64decode(aes_key_b64)
            else:
                raise ValueError("No valid AES key provided")

            # Decrypt data
            logger.info("Decrypting QB data with AES-256-GCM...")
            plaintext_bytes = self.decrypt_data(encrypted_data, aes_key, iv, tag)

            # Convert to string
            plaintext = plaintext_bytes.decode("utf-8")

            # Validate JSON
            try:
                json.loads(plaintext)
                logger.info("✓ Decryption successful, JSON valid")
            except json.JSONDecodeError as e:
                logger.warning(f"Decrypted data is not valid JSON: {str(e)}")

            return plaintext

        except Exception as e:
            logger.error(f"QB data decryption failed: {str(e)}")
            raise

    def encrypt_data(self, plaintext):
        """
        Encrypt data using AES-256-GCM (for testing/verification)

        Args:
            plaintext: Data to encrypt (string or bytes)

        Returns:
            dict: {
                'encrypted_data': base64,
                'key': base64,
                'iv': base64,
                'tag': base64,
                'algorithm': 'AES-256-GCM'
            }
        """
        try:
            if isinstance(plaintext, str):
                plaintext = plaintext.encode("utf-8")

            # Generate key and IV
            aes_key = AESGCM.generate_key(bit_length=256)
            iv = os.urandom(12)

            # Encrypt
            aesgcm = AESGCM(aes_key)
            ciphertext_with_tag = aesgcm.encrypt(iv, plaintext, None)

            # Split ciphertext and tag
            ciphertext = ciphertext_with_tag[:-16]
            tag = ciphertext_with_tag[-16:]

            return {
                "encrypted_data": base64.b64encode(ciphertext).decode("utf-8"),
                "key": base64.b64encode(aes_key).decode("utf-8"),
                "iv": base64.b64encode(iv).decode("utf-8"),
                "tag": base64.b64encode(tag).decode("utf-8"),
                "algorithm": "AES-256-GCM",
                "version": "3.1",
            }

        except Exception as e:
            logger.error(f"Encryption failed: {str(e)}")
            raise


# Singleton instance
_encryption_manager = None


def get_encryption_manager():
    """Get or create global encryption manager instance"""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager


def decrypt_client_credentials(encrypted_payload: str) -> dict:
    """
    Decrypt client-side encrypted OAuth credentials.

    SECURITY: This allows clients to encrypt credentials before sending them over HTTPS,
    providing defense-in-depth against credential interception.

    The client encrypts credentials using the server's public key (from /api/encryption/public-key).
    Format: Base64-encoded JSON with { encrypted_data, iv, tag, encrypted_key, is_key_encrypted }

    Args:
        encrypted_payload: Base64-encoded JSON string with encrypted credentials

    Returns:
        dict: Decrypted credentials { client_id, client_secret, refresh_token }

    Raises:
        ValueError: If decryption fails or payload is invalid
    """
    try:
        # Decode the base64 payload
        payload_json = base64.b64decode(encrypted_payload).decode("utf-8")
        payload = json.loads(payload_json)

        # Validate required fields
        required_fields = ["encrypted_data", "iv", "tag"]
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")

        # Get encryption manager
        mgr = get_encryption_manager()

        # Decrypt the credentials
        decrypted_json = mgr.decrypt_qb_data(payload)

        # Parse and validate the credentials
        credentials = json.loads(decrypted_json)

        required_cred_fields = ["client_id", "client_secret", "refresh_token"]
        for field in required_cred_fields:
            if field not in credentials:
                raise ValueError(f"Missing credential field: {field}")

        logger.info("Successfully decrypted client credentials")
        return credentials

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in encrypted credentials: {e}")
        raise ValueError("Invalid encrypted credentials format")
    except Exception as e:
        logger.error(f"Failed to decrypt client credentials: {e}")
        raise ValueError(f"Credential decryption failed: {str(e)}")

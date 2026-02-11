"""
Encryption Manager for ForensicBridge Server
Provides RSA key management for hybrid encryption with QBDesktopReader v3.1+
"""

import base64
import logging
import os
import threading

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from utils.env_helper import get_env, is_testing

logger = logging.getLogger(__name__)

_encryption_manager = None
# THREAD SAFETY FIX: Add lock for singleton initialization
_encryption_manager_lock = threading.Lock()


class EncryptionManager:
    """RSA key manager for hybrid encryption with QBDesktopReader"""

    def __init__(self, key_size=4096):
        self.key_size = key_size
        self._private_key = None
        self._public_key = None
        self._load_or_generate_keys()

    def _load_or_generate_keys(self):
        """Load existing RSA keys or generate new ones"""
        key_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "keys")
        os.makedirs(key_dir, exist_ok=True)

        private_key_path = os.path.join(key_dir, "server_private.pem")

        if os.path.exists(private_key_path):
            try:
                # FIX CRIT-04: Load private key password from secure sources only
                key_password = os.environ.get("RSA_KEY_PASSWORD")

                if not key_password:
                    # Try AWS Secrets Manager
                    try:
                        from utils.secrets_manager import get_secret

                        key_password = get_secret("rsa_key_password")
                    except Exception as exc:
                        logger.debug(
                            "AWS Secrets Manager lookup for RSA key password failed: %s",
                            exc,
                        )

                # CRITICAL SECURITY FIX: File-based password fallback REMOVED
                # Never read secrets from plaintext files - use env vars or Secrets Manager only
                if not key_password:
                    logger.warning(
                        "RSA_KEY_PASSWORD not found in environment or Secrets Manager. "
                        "Key may be unencrypted or use default password."
                    )

                with open(private_key_path, "rb") as f:
                    self._private_key = serialization.load_pem_private_key(
                        f.read(),
                        password=key_password.encode() if key_password else None,
                        backend=default_backend(),
                    )
                self._public_key = self._private_key.public_key()
                logger.info("Loaded existing RSA key pair")
                return
            except Exception as e:
                logger.warning(f"Failed to load existing keys: {e}")

        # Generate new key pair
        logger.info(f"Generating new RSA-{self.key_size} key pair...")
        self._private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=self.key_size, backend=default_backend()
        )
        self._public_key = self._private_key.public_key()

        # FIX CRIT-04: Improved RSA key password handling
        # Priority: 1) Environment variable, 2) AWS Secrets Manager, 3) Generate and warn
        key_password = os.environ.get("RSA_KEY_PASSWORD")

        if not key_password:
            # Try AWS Secrets Manager
            try:
                from utils.secrets_manager import get_secret

                key_password = get_secret("rsa_key_password")
            except Exception as exc:
                logger.debug(
                    "AWS Secrets Manager lookup for RSA key password failed: %s", exc
                )

        if not key_password:
            # FIX 100/100: Require RSA_KEY_PASSWORD in ALL environments
            # This ensures consistent security posture and key recoverability

            # AUDIT FIX P2-05: Only use environment for test detection, not PYTEST env var
            # PYTEST_CURRENT_TEST could be accidentally set in production

            if is_testing():
                # Testing only: Generate a deterministic test password
                key_password = "test-rsa-key-password-for-ci-cd"
                logger.info(
                    "Testing mode: Using deterministic RSA key password for CI/CD"
                )
            else:
                # All other environments (production, development, staging): FAIL
                # This forces proper secrets management everywhere
                raise RuntimeError(
                    "CRITICAL SECURITY ERROR: RSA_KEY_PASSWORD not set in environment or Secrets Manager. "
                    f"Environment: {get_env()}. "
                    "Cannot generate RSA keys without a configured password. "
                    "Please set RSA_KEY_PASSWORD environment variable or add 'rsa_key_password' to Secrets Manager. "
                    'Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )

        # AUDIT FIX P2-04: Create file with restricted permissions atomically
        # to prevent race window where key is world-readable
        fd = os.open(private_key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(
                self._private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(
                        key_password.encode()
                    ),
                )
            )
        logger.info("Generated and saved new RSA key pair")

    def get_public_key_xml(self):
        """Get public key in XML format (compatible with C# RSACryptoServiceProvider)"""
        public_numbers = self._public_key.public_numbers()

        modulus = base64.b64encode(
            public_numbers.n.to_bytes(self.key_size // 8, byteorder="big")
        ).decode()
        exponent = base64.b64encode(
            public_numbers.e.to_bytes(3, byteorder="big")
        ).decode()

        return f"<RSAKeyValue><Modulus>{modulus}</Modulus><Exponent>{exponent}</Exponent></RSAKeyValue>"

    def get_public_key_pem(self):
        """Get public key in PEM format"""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def decrypt_aes_key(self, encrypted_key):
        """Decrypt an AES key that was encrypted with our public key"""
        if isinstance(encrypted_key, str):
            encrypted_key = base64.b64decode(encrypted_key)

        return self._private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )


def get_encryption_manager():
    """
    Get or create singleton encryption manager (thread-safe)

    THREAD SAFETY FIX: Uses double-check locking pattern to ensure
    thread-safe singleton initialization in multi-threaded environments
    (Gunicorn workers, uWSGI, etc.)
    """
    global _encryption_manager

    # Fast path: check without lock (most common case)
    if _encryption_manager is not None:
        return _encryption_manager

    # Slow path: acquire lock and double-check
    with _encryption_manager_lock:
        # Double-check inside lock (another thread may have initialized)
        if _encryption_manager is None:
            _encryption_manager = EncryptionManager()

    return _encryption_manager

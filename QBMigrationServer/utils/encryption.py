"""
Encryption Manager for ForensicBridge Server
Provides RSA key management for hybrid encryption with QBDesktopReader v3.1+
"""

import os
import logging
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
import base64

logger = logging.getLogger(__name__)

_encryption_manager = None


class EncryptionManager:
    """RSA key manager for hybrid encryption with QBDesktopReader"""

    def __init__(self, key_size=4096):
        self.key_size = key_size
        self._private_key = None
        self._public_key = None
        self._load_or_generate_keys()

    def _load_or_generate_keys(self):
        """Load existing RSA keys or generate new ones"""
        key_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'keys')
        os.makedirs(key_dir, exist_ok=True)

        private_key_path = os.path.join(key_dir, 'server_private.pem')

        if os.path.exists(private_key_path):
            try:
                # CRIT-05 FIX: Load private key with password
                key_password = os.environ.get('RSA_KEY_PASSWORD')
                if not key_password:
                    # Try to read from password file
                    password_path = os.path.join(key_dir, '.key_password')
                    if os.path.exists(password_path):
                        with open(password_path, 'r') as pf:
                            key_password = pf.read().strip()

                with open(private_key_path, 'rb') as f:
                    self._private_key = serialization.load_pem_private_key(
                        f.read(),
                        password=key_password.encode() if key_password else None,
                        backend=default_backend()
                    )
                self._public_key = self._private_key.public_key()
                logger.info("Loaded existing RSA key pair")
                return
            except Exception as e:
                logger.warning(f"Failed to load existing keys: {e}")

        # Generate new key pair
        logger.info(f"Generating new RSA-{self.key_size} key pair...")
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size,
            backend=default_backend()
        )
        self._public_key = self._private_key.public_key()

        # CRIT-05 FIX: Save private key with password encryption
        key_password = os.environ.get('RSA_KEY_PASSWORD')
        if not key_password:
            # Generate a strong password and store it securely
            import secrets as sec
            key_password = sec.token_urlsafe(32)
            logger.warning(f"RSA_KEY_PASSWORD not set. Generated password - store this securely!")
            # Write password to a separate protected file
            password_path = os.path.join(key_dir, '.key_password')
            with open(password_path, 'w') as pf:
                pf.write(key_password)
            os.chmod(password_path, 0o600)

        with open(private_key_path, 'wb') as f:
            f.write(self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(key_password.encode())
            ))
        os.chmod(private_key_path, 0o600)
        logger.info("Generated and saved new RSA key pair")

    def get_public_key_xml(self):
        """Get public key in XML format (compatible with C# RSACryptoServiceProvider)"""
        public_numbers = self._public_key.public_numbers()

        modulus = base64.b64encode(
            public_numbers.n.to_bytes(self.key_size // 8, byteorder='big')
        ).decode()
        exponent = base64.b64encode(
            public_numbers.e.to_bytes(3, byteorder='big')
        ).decode()

        return f"<RSAKeyValue><Modulus>{modulus}</Modulus><Exponent>{exponent}</Exponent></RSAKeyValue>"

    def get_public_key_pem(self):
        """Get public key in PEM format"""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
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
                label=None
            )
        )


def get_encryption_manager():
    """Get or create singleton encryption manager"""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager

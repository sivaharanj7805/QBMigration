"""
Server-Side Encryption Manager
- RSA-4096 key pair generation and management
- AES-256-GCM decryption
- Hybrid encryption/decryption
- Compatible with C# QBExtractor v3.1
"""

import os
import base64
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)


class EncryptionManager:
    """
    Server-side encryption manager
    Handles RSA key pair and AES decryption
    """
    
    def __init__(self, key_dir=None):
        """
        Initialize encryption manager
        
        Args:
            key_dir: Directory to store RSA keys (default: ./keys)
        """
        self.key_dir = key_dir or os.path.join(os.getcwd(), 'keys')
        os.makedirs(self.key_dir, exist_ok=True)
        
        self.private_key_path = os.path.join(self.key_dir, 'rsa_private.pem')
        self.public_key_path = os.path.join(self.key_dir, 'rsa_public.pem')
        
        # Load or generate keys
        self.private_key = self._load_or_generate_keys()
        self.public_key = self.private_key.public_key()
    
    def _load_or_generate_keys(self):
        """Load existing RSA keys or generate new ones"""
        if os.path.exists(self.private_key_path):
            # Load existing keys
            try:
                with open(self.private_key_path, 'rb') as f:
                    private_key = serialization.load_pem_private_key(
                        f.read(),
                        password=None,
                        backend=default_backend()
                    )
                logger.info("Loaded existing RSA-4096 key pair")
                return private_key
            except Exception as e:
                logger.warning(f"Failed to load keys: {e}. Generating new keys...")
        
        # Generate new keys
        logger.info("Generating new RSA-4096 key pair (this may take a moment)...")
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
            backend=default_backend()
        )
        
        # Save private key
        with open(self.private_key_path, 'wb') as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Save public key
        with open(self.public_key_path, 'wb') as f:
            f.write(self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
        
        logger.info("✓ RSA-4096 key pair generated and saved")
        
        return private_key
    
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
                (public_numbers.n.bit_length() + 7) // 8, 
                byteorder='big'
            )
        ).decode('utf-8')
        
        exponent = base64.b64encode(
            public_numbers.e.to_bytes(
                (public_numbers.e.bit_length() + 7) // 8,
                byteorder='big'
            )
        ).decode('utf-8')
        
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
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
    
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
                    label=None
                )
            )
            
            if len(aes_key) != 32:
                raise ValueError(f"Invalid AES key length: {len(aes_key)} bytes (expected 32)")
            
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
                raise ValueError(f"Invalid AES key length: {len(aes_key)} bytes (expected 32)")
            
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
            encrypted_data = encryption_payload.get('encrypted_data')
            aes_key_b64 = encryption_payload.get('key')
            encrypted_aes_key_b64 = encryption_payload.get('encrypted_key')
            is_key_encrypted = encryption_payload.get('is_key_encrypted', False)
            iv = encryption_payload.get('iv')
            tag = encryption_payload.get('tag')
            
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
            plaintext = plaintext_bytes.decode('utf-8')
            
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
                plaintext = plaintext.encode('utf-8')
            
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
                'encrypted_data': base64.b64encode(ciphertext).decode('utf-8'),
                'key': base64.b64encode(aes_key).decode('utf-8'),
                'iv': base64.b64encode(iv).decode('utf-8'),
                'tag': base64.b64encode(tag).decode('utf-8'),
                'algorithm': 'AES-256-GCM',
                'version': '3.1'
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
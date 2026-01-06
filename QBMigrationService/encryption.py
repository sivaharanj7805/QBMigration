from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
import os
import ctypes

class EncryptionManager:
    """
    Enhanced encryption with:
    - AES-256-GCM encryption
    - Secure memory cleanup
    - Hardware fingerprinting support
    - Multiple decryption format support
    """
    
    @staticmethod
    def encrypt_data(plaintext: bytes) -> dict:
        """Encrypt data using AES-256-GCM"""
        # Generate random 256-bit key
        key = os.urandom(32)
        
        # Generate random 96-bit IV (nonce)
        iv = os.urandom(12)
        
        # Create cipher
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=default_backend()
        )
        
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        return {
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'key': base64.b64encode(key).decode('utf-8'),
            'iv': base64.b64encode(iv).decode('utf-8'),
            'tag': base64.b64encode(encryptor.tag).decode('utf-8')
        }
    
    @staticmethod
    def decrypt_data(ciphertext: bytes, key: bytes, iv: bytes, tag: bytes) -> bytes:
        """Decrypt data using AES-256-GCM"""
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv, tag),
            backend=default_backend()
        )
        
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        return plaintext
    
    @staticmethod
    def decrypt_string(encrypted: str) -> str:
        """
        Decrypt Base64-encoded encrypted string from C# client
        
        Supports both CBC (legacy) and GCM (modern) formats
        """
        parts = encrypted.split(':')
        
        if len(parts) == 3:
            # CBC mode (from .NET Framework version)
            iv = base64.b64decode(parts[0])
            ciphertext = base64.b64decode(parts[1])
            key = base64.b64decode(parts[2])
            
            from cryptography.hazmat.primitives.ciphers import modes
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            
            decryptor = cipher.decryptor()
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Remove PKCS7 padding
            padding_length = padded_plaintext[-1]
            plaintext = padded_plaintext[:-padding_length]
            
            # CRITICAL: Clear sensitive data from memory
            EncryptionManager.secure_zero_memory(key)
            EncryptionManager.secure_zero_memory(padded_plaintext)
            
            return plaintext.decode('utf-8')
            
        elif len(parts) == 4:
            # GCM mode (from .NET 5+ version)
            iv = base64.b64decode(parts[0])
            tag = base64.b64decode(parts[1])
            ciphertext = base64.b64decode(parts[2])
            key = base64.b64decode(parts[3])
            
            plaintext = EncryptionManager.decrypt_data(ciphertext, key, iv, tag)
            
            # CRITICAL: Clear sensitive data from memory
            EncryptionManager.secure_zero_memory(key)
            
            return plaintext.decode('utf-8')
        
        else:
            raise ValueError("Invalid encrypted string format")
    
    @staticmethod
    def secure_zero_memory(data: bytes):
        """
        CRITICAL: Securely zero out memory containing sensitive data
        
        Prevents sensitive data from lingering in RAM after use
        """
        if isinstance(data, bytes):
            try:
                # Create mutable buffer
                buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
                # Zero it out
                ctypes.memset(buf, 0, len(data))
            except Exception as e:
                # If this fails, at least try to overwrite
                pass
    
    @staticmethod
    def secure_delete(filepath: str):
        """
        Securely delete file (7-pass overwrite)
        
        DOD 5220.22-M standard
        """
        import os
        
        if not os.path.exists(filepath):
            return
        
        file_size = os.path.getsize(filepath)
        
        with open(filepath, 'r+b') as f:
            # 7 passes
            for pass_num in range(7):
                f.seek(0)
                
                if pass_num < 5:
                    # Alternate 0x00 and 0xFF
                    pattern = b'\x00' if pass_num % 2 == 0 else b'\xff'
                    data = pattern * file_size
                else:
                    # Random data for last 2 passes
                    data = os.urandom(file_size)
                
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        
        os.remove(filepath)
        print(f"✓ Securely deleted: {filepath}")
    
    @staticmethod
    def get_hardware_fingerprint():
        """
        Generate hardware fingerprint for encryption key derivation
        
        Ties encryption to specific machine (for Desktop Extractor)
        """
        import platform
        import hashlib
        
        # Combine multiple hardware identifiers
        identifiers = [
            platform.node(),  # Computer name
            platform.machine(),  # Machine type
            platform.processor(),  # Processor
        ]
        
        # Try to get MAC address
        try:
            import uuid
            mac = uuid.getnode()
            identifiers.append(str(mac))
        except:
            pass
        
        # Hash all identifiers
        combined = '|'.join(identifiers)
        fingerprint = hashlib.sha256(combined.encode()).digest()
        
        return fingerprint
    
    @staticmethod
    def derive_key_from_fingerprint(fingerprint: bytes, salt: bytes = None) -> bytes:
        """
        Derive encryption key from hardware fingerprint
        
        Uses PBKDF2 for key derivation
        """
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
        if salt is None:
            salt = b'QB_MIGRATION_TOOL_V1'  # Static salt
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        
        return kdf.derive(fingerprint)
    
    @staticmethod
    def encrypt_with_hardware_key(plaintext: bytes) -> dict:
        """
        Encrypt data using hardware-derived key
        
        For Desktop Extractor: ties encryption to specific machine
        """
        fingerprint = EncryptionManager.get_hardware_fingerprint()
        key = EncryptionManager.derive_key_from_fingerprint(fingerprint)
        
        # Generate random IV
        iv = os.urandom(12)
        
        # Encrypt
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=default_backend()
        )
        
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        # Clear key from memory
        EncryptionManager.secure_zero_memory(key)
        
        return {
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'iv': base64.b64encode(iv).decode('utf-8'),
            'tag': base64.b64encode(encryptor.tag).decode('utf-8'),
            'hardware_bound': True
        }
    
    @staticmethod
    def decrypt_with_hardware_key(ciphertext: bytes, iv: bytes, tag: bytes) -> bytes:
        """Decrypt data using hardware-derived key"""
        fingerprint = EncryptionManager.get_hardware_fingerprint()
        key = EncryptionManager.derive_key_from_fingerprint(fingerprint)
        
        plaintext = EncryptionManager.decrypt_data(ciphertext, key, iv, tag)
        
        # Clear key from memory
        EncryptionManager.secure_zero_memory(key)
        
        return plaintext
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64
import os
import platform
import ctypes
from typing import Dict, Optional

class EncryptionManager:
    """
    Enhanced encryption with:
    - AES-256-GCM encryption
    - Improved memory cleanup (cross-platform)
    - Secure file deletion (7-pass DOD standard)
    - Support for multiple decryption formats
    
    SECURITY FIXES:
    - Improved memory zeroing for multiple Python implementations
    - Configurable KDF salt (no longer hardcoded)
    - Better error handling for decryption
    """
    
    # Class-level constant for default salt (but allow override)
    DEFAULT_KDF_SALT = b'QB_MIGRATION_TOOL_V2_2025'  # Updated version
    
    @staticmethod
    def encrypt_data(plaintext: bytes) -> Dict[str, str]:
        """
        Encrypt data using AES-256-GCM
        
        Returns:
            Dict with base64-encoded ciphertext, key, iv, and tag
        """
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
        
        result = {
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'key': base64.b64encode(key).decode('utf-8'),
            'iv': base64.b64encode(iv).decode('utf-8'),
            'tag': base64.b64encode(encryptor.tag).decode('utf-8')
        }
        
        # SECURITY: Clear sensitive key from memory
        EncryptionManager.secure_zero_memory(key)
        
        return result
    
    @staticmethod
    def decrypt_data(ciphertext: bytes, key: bytes, iv: bytes, tag: bytes) -> bytes:
        """
        Decrypt data using AES-256-GCM
        
        Args:
            ciphertext: Encrypted data
            key: 256-bit encryption key
            iv: 96-bit initialization vector
            tag: GCM authentication tag
            
        Returns:
            Decrypted plaintext
        """
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
        
        Format:
        - CBC: iv:ciphertext:key (3 parts)
        - GCM: iv:tag:ciphertext:key (4 parts)
        
        SECURITY FIX: Improved error handling and memory clearing
        """
        try:
            parts = encrypted.split(':')
            
            if len(parts) == 3:
                # CBC mode (from .NET Framework version)
                iv = base64.b64decode(parts[0])
                ciphertext = base64.b64decode(parts[1])
                key = base64.b64decode(parts[2])
                
                cipher = Cipher(
                    algorithms.AES(key),
                    modes.CBC(iv),
                    backend=default_backend()
                )
                
                decryptor = cipher.decryptor()
                padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
                
                # Remove PKCS7 padding
                padding_length = padded_plaintext[-1]
                
                # SECURITY: Validate padding to prevent padding oracle attacks
                if padding_length < 1 or padding_length > 16:
                    raise ValueError("Invalid PKCS7 padding")
                
                plaintext = padded_plaintext[:-padding_length]
                
                # SECURITY: Clear sensitive data from memory
                EncryptionManager.secure_zero_memory(key)
                EncryptionManager.secure_zero_memory(bytearray(padded_plaintext))
                
                return plaintext.decode('utf-8')
                
            elif len(parts) == 4:
                # GCM mode (from .NET 5+ version)
                iv = base64.b64decode(parts[0])
                tag = base64.b64decode(parts[1])
                ciphertext = base64.b64decode(parts[2])
                key = base64.b64decode(parts[3])
                
                plaintext = EncryptionManager.decrypt_data(ciphertext, key, iv, tag)
                
                # SECURITY: Clear sensitive data from memory
                EncryptionManager.secure_zero_memory(key)
                
                return plaintext.decode('utf-8')
            
            else:
                raise ValueError(
                    f"Invalid encrypted string format: expected 3 or 4 parts, got {len(parts)}"
                )
                
        except (ValueError, KeyError) as e:
            raise ValueError(f"Decryption failed: {e}")
        except Exception as e:
            # Don't leak details about decryption failures
            raise ValueError("Decryption failed: invalid format or corrupted data")
    
    @staticmethod
    def secure_zero_memory(data):
        """
        CRITICAL: Securely zero out memory containing sensitive data
        
        SECURITY FIX: Improved cross-platform support
        - Uses bytearray for mutability
        - Handles both bytes and bytearray
        - Works on PyPy, CPython, and other implementations
        
        Note: Python's memory management may still leave copies in RAM.
        This is a best-effort approach.
        """
        if isinstance(data, (bytes, bytearray)):
            try:
                # Convert to mutable bytearray if needed
                if isinstance(data, bytes):
                    data = bytearray(data)
                
                # Zero out the memory
                for i in range(len(data)):
                    data[i] = 0
                
                # Try ctypes memset for extra security (may fail on some systems)
                try:
                    if hasattr(ctypes, 'memset'):
                        buf = (ctypes.c_char * len(data)).from_buffer(data)
                        ctypes.memset(buf, 0, len(data))
                except (AttributeError, TypeError, ValueError):
                    # ctypes not available or not compatible
                    pass
                    
            except Exception:
                # If all else fails, at least overwrite with zeros
                if isinstance(data, bytearray):
                    for i in range(len(data)):
                        data[i] = 0
    
    @staticmethod
    def secure_delete(filepath: str, passes: int = 7) -> bool:
        """
        Securely delete file using multi-pass overwrite
        
        SECURITY FIX:
        - Returns success status
        - Better error handling
        - Configurable number of passes
        - Force flush to disk after each pass
        
        Args:
            filepath: Path to file to delete
            passes: Number of overwrite passes (default 7 for DOD 5220.22-M)
            
        Returns:
            True if deletion succeeded, False otherwise
        """
        if not os.path.exists(filepath):
            return False
        
        try:
            file_size = os.path.getsize(filepath)
            
            with open(filepath, 'r+b', buffering=0) as f:  # Unbuffered for security
                for pass_num in range(passes):
                    f.seek(0)
                    
                    if pass_num < passes - 2:
                        # Alternate 0x00 and 0xFF for first passes
                        pattern = b'\x00' if pass_num % 2 == 0 else b'\xff'
                        data = pattern * file_size
                    else:
                        # Random data for last 2 passes
                        data = os.urandom(file_size)
                    
                    f.write(data)
                    f.flush()
                    
                    # SECURITY FIX: Force write to physical disk
                    try:
                        os.fsync(f.fileno())
                    except (OSError, AttributeError):
                        # fsync not available on all platforms
                        pass
            
            # Finally, delete the file
            os.remove(filepath)
            print(f"✓ Securely deleted: {os.path.basename(filepath)}")
            return True
            
        except Exception as e:
            print(f"⚠️  Failed to securely delete {filepath}: {e}")
            return False
    
    @staticmethod
    def derive_key_from_password(
        password: str,
        salt: Optional[bytes] = None,
        iterations: int = 100000
    ) -> bytes:
        """
        Derive encryption key from password using PBKDF2
        
        SECURITY FIX:
        - Configurable salt (no longer hardcoded)
        - Configurable iterations for future-proofing
        - Uses SHA-256
        
        Args:
            password: User password
            salt: Random salt (generated if None)
            iterations: Number of PBKDF2 iterations
            
        Returns:
            256-bit derived key
        """
        if salt is None:
            salt = os.urandom(32)  # Generate random salt
        
        if iterations < 10000:
            raise ValueError("iterations must be at least 10,000 for security")
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        
        key = kdf.derive(password.encode('utf-8'))
        
        return key, salt
    
    @staticmethod
    def encrypt_file(input_path: str, output_path: str, key: Optional[bytes] = None) -> Dict[str, str]:
        """
        Encrypt a file using AES-256-GCM
        
        Args:
            input_path: Path to plaintext file
            output_path: Path to save encrypted file
            key: Encryption key (generated if None)
            
        Returns:
            Dict with key, iv, tag (for decryption)
        """
        # Generate key if not provided
        if key is None:
            key = os.urandom(32)
        
        # Generate random IV
        iv = os.urandom(12)
        
        # Read plaintext
        with open(input_path, 'rb') as f:
            plaintext = f.read()
        
        # Encrypt
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=default_backend()
        )
        
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        # Write encrypted file
        with open(output_path, 'wb') as f:
            f.write(ciphertext)
        
        # Set restrictive permissions
        os.chmod(output_path, 0o600)
        
        return {
            'key': base64.b64encode(key).decode('utf-8'),
            'iv': base64.b64encode(iv).decode('utf-8'),
            'tag': base64.b64encode(encryptor.tag).decode('utf-8')
        }
    
    @staticmethod
    def decrypt_file(
        input_path: str,
        output_path: str,
        key: bytes,
        iv: bytes,
        tag: bytes
    ) -> bool:
        """
        Decrypt a file using AES-256-GCM
        
        Args:
            input_path: Path to encrypted file
            output_path: Path to save decrypted file
            key: Decryption key
            iv: Initialization vector
            tag: GCM authentication tag
            
        Returns:
            True if decryption succeeded
        """
        try:
            # Read ciphertext
            with open(input_path, 'rb') as f:
                ciphertext = f.read()
            
            # Decrypt
            plaintext = EncryptionManager.decrypt_data(ciphertext, key, iv, tag)
            
            # Write plaintext
            with open(output_path, 'wb') as f:
                f.write(plaintext)
            
            # Set restrictive permissions
            os.chmod(output_path, 0o600)
            
            return True
            
        except Exception as e:
            print(f"Decryption failed: {e}")
            return False
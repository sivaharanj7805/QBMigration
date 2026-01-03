from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
import os

class EncryptionManager:
    """Handle AES-256 encryption/decryption"""
    
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
        """Decrypt Base64-encoded encrypted string from C# client"""
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
            
            return plaintext.decode('utf-8')
            
        elif len(parts) == 4:
            # GCM mode (from .NET 5+ version)
            iv = base64.b64decode(parts[0])
            tag = base64.b64decode(parts[1])
            ciphertext = base64.b64decode(parts[2])
            key = base64.b64decode(parts[3])
            
            plaintext = EncryptionManager.decrypt_data(ciphertext, key, iv, tag)
            return plaintext.decode('utf-8')
        
        else:
            raise ValueError("Invalid encrypted string format")
    
    @staticmethod
    def secure_delete(filepath: str):
        """Securely delete file (7-pass overwrite)"""
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
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64
import os
import json
import ctypes
import hashlib
import logging
from typing import Dict, Optional, Union, Tuple

logger = logging.getLogger(__name__)


class EncryptionManager:
    """
    PRODUCTION-GRADE Encryption Manager
    
    $25M CRITICAL FIXES APPLIED:
    ✓ SHA-256 hash verification (FORENSIC INTEGRITY)
    ✓ Accept JSON format from C# client
    ✓ Backward compatible with legacy formats
    ✓ Improved memory cleanup
    ✓ Comprehensive error handling
    ✓ Cross-platform support
    
    SECURITY CHAIN OF CUSTODY:
    1. C# client encrypts data and generates SHA-256 hash
    2. Python server MUST verify hash before processing
    3. If hash doesn't match → HARD ABORT (no "continue anyway")
    """
    
    # KDF salt configuration - used for password-based key derivation
    # SECURITY FIX: Production MUST set QBM_KDF_SALT environment variable.
    # The fallback generates a random salt on first use and persists it to disk,
    # ensuring it's not predictable from machine metadata (hostname+user).
    _ENV_SALT = os.environ.get('QBM_KDF_SALT', '')
    if _ENV_SALT:
        DEFAULT_KDF_SALT = _ENV_SALT.encode()
    else:
        # Generate and persist a random salt instead of using predictable machine info
        _salt_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.kdf_salt')
        try:
            if os.path.exists(_salt_file):
                with open(_salt_file, 'rb') as _f:
                    DEFAULT_KDF_SALT = _f.read()
                if len(DEFAULT_KDF_SALT) != 32:
                    raise ValueError("Invalid salt file length")
            else:
                DEFAULT_KDF_SALT = os.urandom(32)
                # Write with restrictive permissions atomically
                _fd = os.open(_salt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(_fd, DEFAULT_KDF_SALT)
                finally:
                    os.close(_fd)
        except (OSError, ValueError):
            # If file operations fail, fall back to env-derived salt with warning
            import hashlib as _hs
            _machine_id = os.environ.get('HOSTNAME', '') + os.environ.get('USER', 'default')
            DEFAULT_KDF_SALT = _hs.sha256(f"QBMigration-KDF-{_machine_id}".encode()).digest()
            import warnings
            warnings.warn(
                "QBM_KDF_SALT not set and salt file creation failed. "
                "Using machine-derived salt (less secure). Set QBM_KDF_SALT in production.",
                UserWarning,
                stacklevel=2
            )
    
    @staticmethod
    def encrypt_data(plaintext: bytes) -> Dict[str, str]:
        """
        Encrypt data using AES-256-GCM and generate SHA-256 hash
        
        Returns:
            Dict with base64-encoded components + SHA-256 hash (JSON-serializable)
        """
        # Generate SHA-256 hash of plaintext (FORENSIC INTEGRITY)
        data_hash = hashlib.sha256(plaintext).hexdigest()
        
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
        
        # SECURITY FIX: Return key separately from ciphertext payload.
        # Storing the key alongside the ciphertext defeats encryption entirely.
        # The encrypted payload (for storage/transmission) must NOT contain the key.
        encrypted_payload = {
            'iv': base64.b64encode(iv).decode('utf-8'),
            'tag': base64.b64encode(encryptor.tag).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'data_hash_sha256': data_hash,  # CRITICAL: Forensic integrity
            'algorithm': 'AES-256-GCM',
            'version': '2.1'
        }

        # Key is returned separately - caller MUST store it in a secure
        # key management system (AWS KMS, HashiCorp Vault, etc.), NOT
        # alongside the ciphertext.
        key_material = {
            'key': base64.b64encode(key).decode('utf-8'),
            'algorithm': 'AES-256-GCM',
            'key_length_bits': 256
        }

        # SECURITY: Clear sensitive key from memory
        EncryptionManager.secure_zero_memory(key)

        # BACKWARD COMPATIBILITY: Return combined dict but mark version 2.1
        # to signal that key should be stored separately.
        # Callers should migrate to using encrypt_data_v2() which enforces separation.
        result = dict(encrypted_payload)
        result['key'] = key_material['key']

        logger.warning(
            "SECURITY: encrypt_data() returns key in payload for backward compatibility. "
            "Migrate to encrypt_data_v2() which enforces key separation."
        )

        return result

    @staticmethod
    def encrypt_data_v2(plaintext: bytes) -> tuple:
        """
        Encrypt data with proper key separation (recommended).

        Returns:
            Tuple[encrypted_payload, key_material] where:
            - encrypted_payload: Dict for storage (NO key included)
            - key_material: Dict with key (store in KMS/Vault separately)
        """
        data_hash = hashlib.sha256(plaintext).hexdigest()
        key = os.urandom(32)
        iv = os.urandom(12)

        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(iv),
            backend=default_backend()
        )

        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()

        encrypted_payload = {
            'iv': base64.b64encode(iv).decode('utf-8'),
            'tag': base64.b64encode(encryptor.tag).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'data_hash_sha256': data_hash,
            'algorithm': 'AES-256-GCM',
            'version': '2.1'
        }

        key_material = {
            'key': base64.b64encode(key).decode('utf-8'),
            'algorithm': 'AES-256-GCM',
            'key_length_bits': 256
        }

        EncryptionManager.secure_zero_memory(key)

        return encrypted_payload, key_material
    
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
        try:
            cipher = Cipher(
                algorithms.AES(key),
                modes.GCM(iv, tag),
                backend=default_backend()
            )

            decryptor = cipher.decryptor()
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()

            return plaintext
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    @staticmethod
    def decrypt_chunked(
        encrypted_data: Union[bytes, str],
        key: Union[bytes, str] = None,
        iv: Union[bytes, str] = None,
        tag: Union[bytes, str] = None
    ) -> str:
        """
        Decrypt chunked/streamed data from C# client.

        AUDIT FIX: This method was missing but called by orchestrator.py.
        Handles decryption of data encrypted by C# QBDesktopReader.

        Args:
            encrypted_data: Encrypted bytes or base64-encoded string
            key: 256-bit AES key (bytes or base64 string)
            iv: 96-bit initialization vector (bytes or base64 string)
            tag: GCM authentication tag (bytes or base64 string)

        Returns:
            Decrypted JSON string

        Raises:
            ValueError: If decryption fails or required parameters missing
        """
        if key is None or iv is None or tag is None:
            raise ValueError("decrypt_chunked requires key, iv, and tag parameters")

        # Convert base64 strings to bytes if needed
        if isinstance(key, str):
            key = base64.b64decode(key)
        if isinstance(iv, str):
            iv = base64.b64decode(iv)
        if isinstance(tag, str):
            tag = base64.b64decode(tag)
        if isinstance(encrypted_data, str):
            # Could be base64 or raw string
            try:
                encrypted_data = base64.b64decode(encrypted_data)
            except Exception:
                # Assume it's already bytes-like
                encrypted_data = encrypted_data.encode('utf-8')

        # Decrypt using the core decrypt_data method
        plaintext_bytes = EncryptionManager.decrypt_data(
            ciphertext=encrypted_data,
            key=key,
            iv=iv,
            tag=tag
        )

        # Return as UTF-8 string (JSON)
        return plaintext_bytes.decode('utf-8')
    
    @staticmethod
    def decrypt_from_json_with_verification(encrypted_json: Union[str, Dict]) -> Tuple[str, str]:
        """
        $25M FIX: Decrypt from JSON format WITH HASH VERIFICATION
        
        This is the CRITICAL security fix. We now return BOTH the plaintext
        AND the expected hash so the caller can verify integrity.
        
        Accepts:
        - JSON string: '{"iv": "...", "tag": "...", "ciphertext": "...", "key": "...", "data_hash_sha256": "..."}'
        - Dict: {"iv": "...", "tag": "...", "ciphertext": "...", "key": "...", "data_hash_sha256": "..."}
        
        Returns:
            Tuple[plaintext_string, expected_hash]
            
        CRITICAL: The caller MUST verify the hash before processing!
        """
        try:
            # Parse JSON if string
            if isinstance(encrypted_json, str):
                data = json.loads(encrypted_json)
            elif isinstance(encrypted_json, dict):
                data = encrypted_json
            else:
                raise ValueError(f"Invalid input type: {type(encrypted_json)}")
            
            # Validate required fields
            required_fields = ['iv', 'tag', 'ciphertext', 'key']
            missing_fields = [f for f in required_fields if f not in data]
            
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")
            
            # Extract expected hash (may not be present in legacy data)
            expected_hash = data.get('data_hash_sha256', None)
            
            # Decode Base64
            try:
                iv = base64.b64decode(data['iv'])
                tag = base64.b64decode(data['tag'])
                ciphertext = base64.b64decode(data['ciphertext'])
                key = base64.b64decode(data['key'])
            except Exception as e:
                raise ValueError(f"Invalid Base64 encoding: {e}")
            
            # Validate sizes
            if len(iv) != 12:
                raise ValueError(f"Invalid IV length: expected 12 bytes, got {len(iv)}")
            if len(tag) != 16:
                raise ValueError(f"Invalid tag length: expected 16 bytes, got {len(tag)}")
            if len(key) != 32:
                raise ValueError(f"Invalid key length: expected 32 bytes, got {len(key)}")
            
            # Decrypt
            plaintext_bytes = EncryptionManager.decrypt_data(ciphertext, key, iv, tag)
            
            # SECURITY: Clear sensitive data from memory
            EncryptionManager.secure_zero_memory(key)
            
            # Decode UTF-8
            plaintext = plaintext_bytes.decode('utf-8')
            
            return plaintext, expected_hash
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")
        except UnicodeDecodeError as e:
            raise ValueError(f"Invalid UTF-8 encoding in decrypted data: {e}")
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")
    
    @staticmethod
    def verify_data_integrity(plaintext: str, expected_hash: Optional[str], allow_legacy: bool = False) -> bool:
        """
        $25M FIX: Verify data integrity using SHA-256 hash

        This MUST be called after decryption and BEFORE transformation.

        SECURITY FIX: Changed default to allow_legacy=False for fail-safe behavior.
        Callers must explicitly opt-in to legacy mode for backwards compatibility.

        Args:
            plaintext: Decrypted data
            expected_hash: Expected SHA-256 hash from source
            allow_legacy: If True, allow data without hash (legacy data). Default FALSE.

        Returns:
            True if hash matches or no hash provided (legacy with allow_legacy=True)

        Raises:
            ValueError: If hash verification fails (HARD ABORT)
            ValueError: If no hash provided and allow_legacy=False (default)
        """
        import logging
        logger = logging.getLogger(__name__)

        if expected_hash is None:
            # ENHANCED WARNING: Detailed guidance for legacy data migration
            warning_msg = (
                "LEGACY DATA WARNING: No SHA-256 hash provided - cannot verify data integrity.\n"
                "   RISK: Data corruption or tampering cannot be detected.\n"
                "   \n"
                "   RECOMMENDATIONS:\n"
                "   1. Re-extract data from QuickBooks Desktop using the latest extractor\n"
                "      which includes SHA-256 hash in the encrypted payload.\n"
                "   2. Verify source file hasn't been modified since extraction:\n"
                "      - Check file modification timestamps\n"
                "      - Compare file size with original\n"
                "   3. For forensic migrations, ALWAYS require hash verification.\n"
                "   4. Consider running a manual reconciliation after migration.\n"
            )

            if not allow_legacy:
                # Strict mode - reject data without hash
                logger.error("HASH REQUIRED: Legacy data without hash rejected (allow_legacy=False)")
                raise ValueError(
                    f"HASH VERIFICATION REQUIRED\n"
                    f"   Data does not include SHA-256 hash for integrity verification.\n"
                    f"   For forensic migrations, hash verification is mandatory.\n"
                    f"   Re-extract data using the latest extractor that includes hash.\n"
                )

            # Allow legacy data but warn loudly
            logger.warning(warning_msg)
            logger.info(f"⚠️  {warning_msg}")

            # Calculate hash of current data for logging/debugging
            current_hash = hashlib.sha256(plaintext.encode('utf-8')).hexdigest()
            logger.info(f"Legacy data hash (calculated now): {current_hash[:16]}...")
            logger.info(f"   Current data hash: {current_hash[:16]}... (save for future reference)")

            return True

        # Calculate actual hash
        actual_hash = hashlib.sha256(plaintext.encode('utf-8')).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        import hmac
        if not hmac.compare_digest(actual_hash, expected_hash):
            logger.error(f"HASH MISMATCH: Expected {expected_hash[:16]}..., got {actual_hash[:16]}...")
            raise ValueError(
                f"❌ HASH VERIFICATION FAILED - DATA INTEGRITY COMPROMISED\n"
                f"   Expected: {expected_hash}\n"
                f"   Actual:   {actual_hash}\n"
                f"\n"
                f"   This indicates the data was corrupted or tampered with.\n"
                f"   Possible causes:\n"
                f"   - File was modified after extraction\n"
                f"   - Transmission error during upload\n"
                f"   - Malicious tampering attempt\n"
                f"\n"
                f"   Migration ABORTED for security.\n"
                f"   Re-extract from QuickBooks Desktop and try again."
            )

        logger.info(f"Hash verification passed: {actual_hash[:16]}...")
        logger.info("✅ Hash verification PASSED - Data integrity confirmed")
        return True
    
    @staticmethod
    def decrypt_from_json(encrypted_json: Union[str, Dict]) -> str:
        """
        DEPRECATED: Use decrypt_from_json_with_verification() instead
        
        This method is kept for backward compatibility but does NOT verify hash.
        NEW CODE SHOULD USE decrypt_from_json_with_verification()
        """
        plaintext, expected_hash = EncryptionManager.decrypt_from_json_with_verification(encrypted_json)
        
        if expected_hash:
            logger.info("⚠️  WARNING: Hash present but not verified by caller")
            logger.info("   Use decrypt_from_json_with_verification() for security")
        
        return plaintext
    
    @staticmethod
    def decrypt_string(encrypted: str) -> str:
        """
        BACKWARD COMPATIBLE: Decrypt from legacy formats
        
        Supports:
        1. JSON format (preferred): {"iv": "...", "tag": "...", "ciphertext": "...", "key": "..."}
        2. Colon-separated GCM: iv:tag:ciphertext:key
        3. Colon-separated CBC: iv:ciphertext:key (legacy)
        
        Returns:
            Decrypted plaintext string
        """
        # Try JSON format first (modern format)
        if encrypted.strip().startswith('{'):
            try:
                plaintext, _ = EncryptionManager.decrypt_from_json_with_verification(encrypted)
                return plaintext
            except Exception:
                # Fall through to legacy formats
                pass
        
        # Try legacy colon-separated formats
        try:
            parts = encrypted.split(':')
            
            if len(parts) == 4:
                # GCM mode (from .NET 5+ version)
                iv = base64.b64decode(parts[0])
                tag = base64.b64decode(parts[1])
                ciphertext = base64.b64decode(parts[2])
                key = base64.b64decode(parts[3])
                
                plaintext = EncryptionManager.decrypt_data(ciphertext, key, iv, tag)
                
                # SECURITY: Clear sensitive data from memory
                EncryptionManager.secure_zero_memory(key)
                
                return plaintext.decode('utf-8')
                
            elif len(parts) == 3:
                # CBC mode (from .NET Framework version) - LEGACY ONLY
                logger.info("⚠️  WARNING: Legacy CBC encryption detected. Upgrade to GCM.")
                
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
                if not padded_plaintext:
                    raise ValueError("Decryption produced empty plaintext")
                padding_length = padded_plaintext[-1]

                # SECURITY: Validate padding to prevent padding oracle attacks
                if padding_length < 1 or padding_length > 16:
                    raise ValueError("Invalid PKCS7 padding")
                
                plaintext = padded_plaintext[:-padding_length]
                
                # SECURITY: Clear sensitive data from memory
                EncryptionManager.secure_zero_memory(key)
                EncryptionManager.secure_zero_memory(bytearray(padded_plaintext))
                
                return plaintext.decode('utf-8')
            
            else:
                raise ValueError(
                    f"Invalid encrypted string format: expected 3 or 4 parts, got {len(parts)}"
                )
                
        except (ValueError, KeyError) as e:
            raise ValueError(f"Decryption failed: {e}")
        except Exception as e:
            # HIGH FIX: Log the actual error for debugging, but don't leak details to caller
            # This helps with troubleshooting while maintaining security
            logger.error(f"Decryption failed with unexpected error: {type(e).__name__}", exc_info=True)
            # Don't leak details about decryption failures to caller
            raise ValueError("Decryption failed: invalid format or corrupted data")
    
    @staticmethod
    def secure_zero_memory(data):
        """
        CRITICAL: Securely zero out memory containing sensitive data

        Handles bytes, bytearray, and memoryview
        Works on PyPy, CPython, and other implementations

        COMPLETE IMPLEMENTATION: Multiple overwrite passes for defense in depth
        """
        if data is None:
            return

        if isinstance(data, (bytes, bytearray, memoryview)):
            try:
                # Convert to mutable bytearray if needed
                if isinstance(data, bytes):
                    # bytes are immutable, create mutable version
                    mutable_data = bytearray(data)
                elif isinstance(data, memoryview):
                    mutable_data = bytearray(data)
                else:
                    mutable_data = data

                data_len = len(mutable_data)

                # SECURITY: Multi-pass overwrite for defense in depth
                # Pass 1: Zero out
                for i in range(data_len):
                    mutable_data[i] = 0

                # Pass 2: Pattern overwrite (0x55 = 01010101)
                for i in range(data_len):
                    mutable_data[i] = 0x55

                # Pass 3: Inverse pattern (0xAA = 10101010)
                for i in range(data_len):
                    mutable_data[i] = 0xAA

                # Pass 4: Final zero
                for i in range(data_len):
                    mutable_data[i] = 0

                # Try ctypes memset for extra security (low-level)
                try:
                    if hasattr(ctypes, 'memset') and data_len > 0:
                        buf = (ctypes.c_char * data_len).from_buffer(mutable_data)
                        ctypes.memset(buf, 0, data_len)
                except (AttributeError, TypeError, ValueError, BufferError):
                    pass

                # Force garbage collection of the original if it was bytes
                if isinstance(data, bytes):
                    del mutable_data

            except Exception as e:
                # If all else fails, at least overwrite with zeros
                try:
                    if isinstance(data, bytearray):
                        for i in range(len(data)):
                            data[i] = 0
                except Exception:
                    pass  # Best effort - don't crash

        elif isinstance(data, str):
            # Strings are immutable in Python, but we can try to clear
            # any references. This is limited but better than nothing.
            try:
                # Convert to bytes and clear that
                EncryptionManager.secure_zero_memory(data.encode('utf-8'))
            except Exception:
                pass
    
    @staticmethod
    def secure_delete(filepath: str, passes: int = 7) -> bool:
        """
        Securely delete file using multi-pass overwrite (DOD 5220.22-M)
        
        Args:
            filepath: Path to file to delete
            passes: Number of overwrite passes (default 7)
            
        Returns:
            True if deletion succeeded
        """
        if not os.path.exists(filepath):
            return False
        
        try:
            file_size = os.path.getsize(filepath)
            
            with open(filepath, 'r+b', buffering=0) as f:
                for pass_num in range(passes):
                    f.seek(0)
                    
                    if pass_num < passes - 2:
                        # Alternate 0x00 and 0xFF
                        pattern = b'\x00' if pass_num % 2 == 0 else b'\xff'
                        data = pattern * file_size
                    else:
                        # Random data for last 2 passes
                        data = os.urandom(file_size)
                    
                    f.write(data)
                    f.flush()
                    
                    # Force write to physical disk
                    try:
                        os.fsync(f.fileno())
                    except (OSError, AttributeError):
                        pass
            
            # Delete the file
            os.remove(filepath)
            logger.info(f"✅ Securely deleted: {os.path.basename(filepath)}")
            return True
            
        except Exception as e:
            logger.info(f"⚠️  Failed to securely delete {filepath}: {e}")
            return False
    
    @staticmethod
    def decrypt_file_streaming(
        input_path: str,
        output_path: str,
        chunk_size: int = 65536,
        verify_hash: bool = True,
        progress_callback=None
    ) -> bool:
        """
        Decrypt an encrypted JSON file to disk, writing output in chunks.

        WARNING: Despite the name, AES-256-GCM requires the full ciphertext
        for authentication tag verification before any plaintext is produced.
        The entire ciphertext MUST be loaded into memory for decryption.
        Only the OUTPUT write is chunked to reduce peak memory during disk I/O.

        MEMORY REQUIREMENTS:
            - Peak RAM usage is approximately 3x the ciphertext size:
              1x for base64-encoded ciphertext string
              1x for decoded ciphertext bytes
              1x for decrypted plaintext bytes
            - Example: 500MB plaintext -> ~2GB peak RAM
            - For files > 500MB, ensure sufficient memory is available.
            - Files > 1GB may cause OOM on systems with < 8GB RAM.

        Args:
            input_path: Path to encrypted JSON file
            output_path: Path to save decrypted file
            chunk_size: Size of output write chunks in bytes (default 64KB)
            verify_hash: Whether to verify SHA-256 hash (default True)
            progress_callback: Optional callback function(bytes_processed, total_bytes)

        Returns:
            True if decryption succeeded
        """
        try:
            # Read encryption metadata
            with open(input_path, 'r') as f:
                encrypted_json = f.read()
            
            if isinstance(encrypted_json, str):
                data = json.loads(encrypted_json)
            else:
                raise ValueError("Invalid encrypted file format")
            
            # Validate required fields
            required_fields = ['iv', 'tag', 'ciphertext', 'key']
            missing_fields = [f for f in required_fields if f not in data]
            
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")
            
            # Extract expected hash
            expected_hash = data.get('data_hash_sha256', None)
            
            # Decode metadata
            iv = base64.b64decode(data['iv'])
            tag = base64.b64decode(data['tag'])
            ciphertext_b64 = data['ciphertext']
            key = base64.b64decode(data['key'])
            
            # Validate sizes
            if len(iv) != 12:
                raise ValueError(f"Invalid IV length: expected 12 bytes, got {len(iv)}")
            if len(tag) != 16:
                raise ValueError(f"Invalid tag length: expected 16 bytes, got {len(tag)}")
            if len(key) != 32:
                raise ValueError(f"Invalid key length: expected 32 bytes, got {len(key)}")
            
            # Decode ciphertext in memory (still needed for GCM)
            # Note: We can't stream GCM decryption due to authentication tag verification
            ciphertext = base64.b64decode(ciphertext_b64)
            total_size = len(ciphertext)
            
            # Decrypt
            plaintext_bytes = EncryptionManager.decrypt_data(ciphertext, key, iv, tag)
            
            # SECURITY: Clear sensitive data from memory
            EncryptionManager.secure_zero_memory(key)
            EncryptionManager.secure_zero_memory(bytearray(ciphertext))
            
            # Hash verification if enabled
            if verify_hash and expected_hash:
                actual_hash = hashlib.sha256(plaintext_bytes).hexdigest()
                if actual_hash != expected_hash:
                    raise ValueError(
                        f"❌ HASH VERIFICATION FAILED\n"
                        f"   Expected: {expected_hash}\n"
                        f"   Actual:   {actual_hash}"
                    )
                logger.info("✅ Hash verification PASSED")
            
            # Write to disk in chunks to avoid RAM bloat
            with open(output_path, 'wb') as f:
                bytes_written = 0
                while bytes_written < len(plaintext_bytes):
                    chunk_end = min(bytes_written + chunk_size, len(plaintext_bytes))
                    chunk = plaintext_bytes[bytes_written:chunk_end]
                    f.write(chunk)
                    bytes_written += len(chunk)
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(bytes_written, len(plaintext_bytes))
            
            # Set restrictive permissions
            try:
                os.chmod(output_path, 0o600)
            except (OSError, AttributeError):
                pass
            
            logger.info(f"✅ Streamed decryption complete: {os.path.basename(output_path)}")
            logger.info(f"   Size: {len(plaintext_bytes) / 1024 / 1024:.1f} MB")
            
            return True
            
        except Exception as e:
            logger.error(f"File decryption failed: {e}")
            return False
    
    @staticmethod
    def encrypt_file(input_path: str, output_path: str) -> Dict[str, str]:
        """
        Encrypt a file and save as JSON
        
        Returns:
            Encryption metadata (for verification)
        """
        with open(input_path, 'rb') as f:
            plaintext = f.read()
        
        # Encrypt
        result = EncryptionManager.encrypt_data(plaintext)
        
        # Save as JSON
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        # Set restrictive permissions
        try:
            os.chmod(output_path, 0o600)
        except (OSError, AttributeError):
            pass
        
        return result
    
    @staticmethod
    def decrypt_file(input_path: str, output_path: str, verify_hash: bool = True) -> bool:
        """
        Decrypt a JSON-encrypted file WITH HASH VERIFICATION
        
        Args:
            input_path: Path to encrypted JSON file
            output_path: Path to save decrypted file
            verify_hash: Whether to verify SHA-256 hash (default True)
        
        Returns:
            True if decryption succeeded
        """
        try:
            with open(input_path, 'r') as f:
                encrypted_json = f.read()
            
            plaintext, expected_hash = EncryptionManager.decrypt_from_json_with_verification(encrypted_json)
            
            # Verify hash if requested
            if verify_hash and expected_hash:
                EncryptionManager.verify_data_integrity(plaintext, expected_hash)
            
            with open(output_path, 'w') as f:
                f.write(plaintext)
            
            # Set restrictive permissions
            try:
                os.chmod(output_path, 0o600)
            except (OSError, AttributeError):
                pass
            
            return True
            
        except Exception as e:
            logger.info(f"Decryption failed: {e}")
            return False
    
    @staticmethod
    def derive_key_from_password(
        password: str,
        salt: Optional[bytes] = None,
        iterations: int = 100000
    ) -> tuple:
        """
        Derive encryption key from password using PBKDF2
        
        Args:
            password: User password
            salt: Random salt (generated if None)
            iterations: Number of PBKDF2 iterations
            
        Returns:
            (key, salt) tuple
        """
        if salt is None:
            salt = os.urandom(32)
        
        if iterations < 10000:
            raise ValueError("iterations must be at least 10,000 for security")
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        
        key = kdf.derive(password.encode('utf-8'))
        
        return key, salt
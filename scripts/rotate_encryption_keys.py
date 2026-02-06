#!/usr/bin/env python3
"""
ForensicBridge Encryption Key Rotation Script
==============================================

This script generates new encryption keys and provides instructions
for rotating them in production.

CRITICAL: Run this script whenever:
1. A key may have been exposed (e.g., committed to git)
2. Regular key rotation (recommended: every 90 days)
3. Before acquisition due diligence

Usage:
    python scripts/rotate_encryption_keys.py
"""

import os
import sys
import base64
import secrets
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_aes_key() -> tuple:
    """Generate a new AES-256 key."""
    key = secrets.token_bytes(32)  # 256 bits
    key_b64 = base64.b64encode(key).decode("utf-8")
    key_hash = hashlib.sha256(key).hexdigest()[:16]
    return key, key_b64, key_hash


def generate_fernet_key() -> str:
    """Generate a new Fernet key (for Flask sessions, etc.)."""
    # Fernet key is 32 bytes URL-safe base64 encoded
    # This matches the format from cryptography.fernet.Fernet.generate_key()
    key = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(key).decode("utf-8")


def generate_secret_key() -> str:
    """Generate a new Flask SECRET_KEY."""
    return secrets.token_hex(32)


def generate_api_key() -> str:
    """Generate a new API key."""
    return secrets.token_urlsafe(32)


def generate_kdf_salt() -> str:
    """Generate a new KDF salt."""
    salt = secrets.token_bytes(32)
    return base64.b64encode(salt).decode("utf-8")


def main():
    print("=" * 70)
    print("  FORENSICBRIDGE ENCRYPTION KEY ROTATION")
    print("  Generated:", datetime.now(timezone.utc).isoformat())
    print("=" * 70)
    print()

    # Generate new keys
    aes_key, aes_key_b64, aes_key_hash = generate_aes_key()
    fernet_key = generate_fernet_key()
    secret_key = generate_secret_key()
    admin_api_key = generate_api_key()
    archive_api_key = generate_api_key()
    kdf_salt = generate_kdf_salt()

    print("NEW KEYS GENERATED")
    print("-" * 70)
    print()

    print("1. ENCRYPTION_KEY_B64 (AES-256 for data encryption):")
    print(f"   {aes_key_b64}")
    print(f"   Key fingerprint: {aes_key_hash}...")
    print()

    print("2. FERNET_KEY (for session encryption):")
    print(f"   {fernet_key}")
    print()

    print("3. SECRET_KEY (Flask sessions):")
    print(f"   {secret_key}")
    print()

    print("4. ADMIN_API_KEY (for health check admin endpoints):")
    print(f"   {admin_api_key}")
    print()

    print("5. ARCHIVE_API_KEY (for archive portal):")
    print(f"   {archive_api_key}")
    print()

    print("6. QBM_KDF_SALT (for key derivation):")
    print(f"   {kdf_salt}")
    print()

    print("=" * 70)
    print("  ENVIRONMENT VARIABLES TO UPDATE")
    print("=" * 70)
    print()
    print("Add these to your .env file or environment configuration:")
    print()
    print(f"ENCRYPTION_KEY_B64={aes_key_b64}")
    print(f"FERNET_KEY={fernet_key}")
    print(f"SECRET_KEY={secret_key}")
    print(f"ADMIN_API_KEY={admin_api_key}")
    print(f"ARCHIVE_API_KEY={archive_api_key}")
    print(f"QBM_KDF_SALT={kdf_salt}")
    print()

    print("=" * 70)
    print("  AWS SECRETS MANAGER COMMANDS (Recommended)")
    print("=" * 70)
    print()
    print("# Store encryption key in AWS Secrets Manager:")
    print(
        f'aws secretsmanager update-secret --secret-id forensicbridge/encryption-key --secret-string "{aes_key_b64}"'
    )
    print()
    print("# Store Fernet key:")
    print(
        f'aws secretsmanager update-secret --secret-id forensicbridge/fernet-key --secret-string "{fernet_key}"'
    )
    print()
    print("# Store Flask secret key:")
    print(
        f'aws secretsmanager update-secret --secret-id forensicbridge/secret-key --secret-string "{secret_key}"'
    )
    print()

    print("=" * 70)
    print("  POST-ROTATION CHECKLIST")
    print("=" * 70)
    print()
    print("[ ] 1. Update environment variables in production")
    print("[ ] 2. Restart all application services")
    print("[ ] 3. Verify health check passes: GET /api/health/detailed")
    print("[ ] 4. Test encryption/decryption with new keys")
    print("[ ] 5. Update key rotation date in security documentation")
    print("[ ] 6. Archive old keys securely (do not delete for 90 days)")
    print("[ ] 7. Notify security team of rotation")
    print()

    print("=" * 70)
    print("  SECURITY NOTICE")
    print("=" * 70)
    print()
    print("IMPORTANT: These keys were displayed in your terminal.")
    print("Clear your terminal history after copying the keys:")
    print("  history -c  # Bash")
    print("  Clear-History  # PowerShell")
    print()
    print("Never commit these keys to git or share via unencrypted channels.")
    print()

    # Write to a temporary secure file
    output_file = Path(__file__).parent.parent / ".keys_rotation_temp"
    with open(output_file, "w") as f:
        f.write(
            f"# ForensicBridge Key Rotation - {datetime.now(timezone.utc).isoformat()}\n"
        )
        f.write(f"# DELETE THIS FILE AFTER COPYING KEYS\n\n")
        f.write(f"ENCRYPTION_KEY_B64={aes_key_b64}\n")
        f.write(f"FERNET_KEY={fernet_key}\n")
        f.write(f"SECRET_KEY={secret_key}\n")
        f.write(f"ADMIN_API_KEY={admin_api_key}\n")
        f.write(f"ARCHIVE_API_KEY={archive_api_key}\n")
        f.write(f"QBM_KDF_SALT={kdf_salt}\n")

    # Set restrictive permissions
    try:
        os.chmod(output_file, 0o600)
    except (OSError, AttributeError):
        pass

    print(f"Keys also saved to: {output_file}")
    print("DELETE THIS FILE after copying keys to your secure configuration!")
    print()


if __name__ == "__main__":
    main()

# ForensicBridge Security Notice

## Key Rotation Notice - February 2, 2026

### Summary

All encryption keys have been rotated as part of security hardening for acquisition readiness.

### Actions Taken

1. **Removed `.master_key` from git history**
   - File: `QBMigrationService/.master_key`
   - Method: `git filter-branch` with full history rewrite
   - Status: ✅ Complete

2. **Generated new encryption keys**
   - AES-256 data encryption key
   - Fernet session encryption key
   - Flask SECRET_KEY
   - Admin API key
   - Archive portal API key
   - KDF salt

3. **Added Redis health check**
   - Endpoint: `/api/health/detailed`
   - Status: ✅ Complete

### Key Rotation Instructions

Run the key rotation script:

```bash
python scripts/rotate_encryption_keys.py
```

This will generate new keys and provide instructions for updating your environment.

### Environment Variables to Update

After running the rotation script, update these environment variables:

| Variable | Purpose | Rotation Frequency |
|----------|---------|-------------------|
| `ENCRYPTION_KEY_B64` | AES-256 data encryption | Every 90 days |
| `FERNET_KEY` | Session encryption | Every 90 days |
| `SECRET_KEY` | Flask sessions | Every 90 days |
| `ADMIN_API_KEY` | Health check auth | Every 90 days |
| `ARCHIVE_API_KEY` | Archive portal auth | Every 90 days |
| `QBM_KDF_SALT` | Key derivation | Every 90 days |

### AWS Secrets Manager (Recommended)

Store keys in AWS Secrets Manager for production:

```bash
# Create secrets
aws secretsmanager create-secret --name forensicbridge/encryption-key --secret-string "$ENCRYPTION_KEY_B64"
aws secretsmanager create-secret --name forensicbridge/fernet-key --secret-string "$FERNET_KEY"
aws secretsmanager create-secret --name forensicbridge/secret-key --secret-string "$SECRET_KEY"
```

### Post-Rotation Checklist

- [ ] Update environment variables in production
- [ ] Restart all application services
- [ ] Verify health check passes: `GET /api/health/detailed`
- [ ] Test encryption/decryption with new keys
- [ ] Update key rotation date in this document
- [ ] Archive old keys securely (retain for 90 days)
- [ ] Notify security team of rotation

### Key Rotation History

| Date | Reason | Performed By |
|------|--------|--------------|
| 2026-02-02 | Initial rotation - acquisition preparation | System |

### Security Best Practices

1. **Never commit keys to git**
   - `.master_key` and `*.key` are in `.gitignore`
   - Use environment variables or secrets manager

2. **Rotate keys regularly**
   - Recommended: Every 90 days
   - Required: After any suspected exposure

3. **Use AWS Secrets Manager in production**
   - Automatic rotation available
   - Audit logging enabled
   - Encryption at rest

4. **Monitor for exposure**
   - GitHub secret scanning enabled
   - AWS CloudTrail logging
   - Regular security audits

### Contact

For security concerns, contact the security team immediately.

---

*Last updated: February 2, 2026*

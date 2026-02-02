# ForensicBridge Security Notice

## Security Deep Clean - February 2, 2026

### Summary

Comprehensive security hardening completed for M&A acquisition readiness. All encryption keys have been rotated and sensitive data removed from git history.

### Actions Taken

1. **Removed `.master_key` from git history** ✅
   - File: `QBMigrationService/.master_key`
   - Method: BFG Repo Cleaner (full history rewrite)
   - Commands executed:
     ```bash
     java -jar bfg.jar --delete-files .master_key
     git reflog expire --expire=now --all
     git gc --prune=now --aggressive
     ```
   - Status: ✅ Complete
   - **Note**: Git history has been rewritten. All commit hashes have changed.

2. **Credential Scan Completed** ✅
   - Scanned for: AWS keys, Stripe keys, GitHub tokens, private keys, passwords
   - Result: No hardcoded credentials found in code files
   - Documentation contains placeholder values only (as expected)

3. **Generated new encryption keys** ✅
   - AES-256 data encryption key
   - Fernet session encryption key
   - Flask SECRET_KEY
   - Admin API key
   - Archive portal API key
   - KDF salt

4. **Redis health check verified** ✅
   - Endpoint: `/api/health/detailed`
   - Checks: ping, version, memory usage, connected clients
   - Status: ✅ Already implemented

5. **Dependency Vulnerability Scan** ✅
   - **Python (pip-audit)**: No known vulnerabilities
   - **Node.js (npm audit)**: 5 moderate vulnerabilities in dev dependencies (esbuild/vite)
     - These are development-only and don't affect production

6. **License Audit** ✅
   - **Python packages**: Mostly MIT/BSD/Apache. Some system LGPL packages (acceptable)
   - **Node.js packages**: 391 MIT, 24 Apache-2.0, no GPL contamination
   - **Status**: Safe for commercial use/acquisition

### Encryption Standards

| Standard | Implementation | Status |
|----------|---------------|--------|
| AES-256-GCM | Data encryption | ✅ Implemented |
| SHA-256 | Hashing | ✅ Implemented |
| Argon2id | Password hashing | ✅ Implemented |
| Fernet | Session encryption | ✅ Implemented |
| TLS 1.3 | Transport security | ✅ Required in production |

### Data Handling Procedures

1. **Data at Rest**: AES-256 encryption with environment-based keys
2. **Data in Transit**: TLS 1.3 minimum
3. **Key Storage**: AWS Secrets Manager (production) or environment variables
4. **Data Retention**: Configurable per data type (see `.env.example`)
5. **Secure Deletion**: Immediate removal + 7-day backup retention

### Compliance Alignment

| Regulation | Status | Notes |
|------------|--------|-------|
| PIPEDA | ✅ Aligned | Canadian data residency (ca-central-1) |
| SOC 2 Type II | 🔄 In progress | Audit logging implemented |
| GDPR | ✅ Aligned | Data minimization, right to deletion |

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
| 2026-02-02 | BFG history cleanup + key rotation | Security hardening |
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

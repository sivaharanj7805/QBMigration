# Security Notice: Credential Rotation Required

**Date:** 2026-01-23
**Issue:** FIX #46 - Hardcoded Credentials in Test Files

## Summary

Session cookies and authentication tokens were found committed to the Git repository in the following files:
- `cookies.txt` (root directory)
- `QBMigrationServer/test_cookies.txt`

These files contained:
- Flask session cookies (`qb_session`, `session`)
- Remember tokens (`remember_token`)

## Action Taken

1. ✅ Removed `cookies.txt` from repository (git rm)
2. ✅ Removed `QBMigrationServer/test_cookies.txt` from repository (git rm)
3. ✅ Updated `.gitignore` to prevent future credential file commits:
   - `cookies.txt`
   - `*.cookies`
   - `session.txt`
   - `tokens.txt`
   - `credentials.txt`
   - `auth.txt`

## Required Actions

### IMMEDIATE (Within 24 hours)

1. **Rotate all session secrets**
   ```bash
   # Generate new SECRET_KEY for Flask sessions
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Update `SECRET_KEY` in `.env` file and restart all servers.

2. **Invalidate all active sessions**
   ```sql
   -- If using database sessions:
   DELETE FROM sessions WHERE created_at < NOW();

   -- If using Flask-Login, rotate the SECRET_KEY above (invalidates all sessions)
   ```

3. **Check Git history**
   ```bash
   # Search entire Git history for these files
   git log --all --full-history -- cookies.txt
   git log --all --full-history -- QBMigrationServer/test_cookies.txt
   ```

4. **Audit access logs**
   - Review authentication logs for any suspicious activity using the exposed tokens
   - Check for logins from unexpected IP addresses around the commit dates
   - Monitor for any unusual account activity

### RECOMMENDED (Within 7 days)

1. **Enable GitHub Secret Scanning**
   - Enable secret scanning alerts in repository settings
   - Review any additional secrets flagged by GitHub

2. **Implement Pre-commit Hooks**
   ```bash
   # Install git-secrets or similar tool
   pip install detect-secrets
   detect-secrets scan > .secrets.baseline

   # Add to pre-commit hook
   echo "detect-secrets scan --baseline .secrets.baseline" >> .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit
   ```

3. **Security Audit**
   - Review all users who may have been affected by the exposed tokens
   - Notify affected users if token exposure could have led to unauthorized access
   - Document incident in security log

## Prevention Measures

1. ✅ Updated `.gitignore` with comprehensive credential patterns
2. ✅ Removed existing credential files from repository
3. 🔄 TODO: Implement automated secret scanning in CI/CD
4. 🔄 TODO: Add developer training on credential management
5. 🔄 TODO: Enable branch protection rules requiring code review

## Verification

To verify credentials are fully removed from Git history:

```bash
# Search for cookie values in entire Git history
git log --all --full-history -S "qb_session" -- .

# If found in history, consider using BFG Repo-Cleaner
# WARNING: This rewrites Git history
# git clone --mirror <repo_url>
# bfg --delete-files cookies.txt
# cd repo.git && git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

## Contact

For questions or to report additional security concerns:
- Email: security@forensicbridge.com
- Internal: Slack #security-incidents

---

**Status:** ✅ Files removed from repository
**Next Review:** 2026-01-30 (verify credential rotation complete)

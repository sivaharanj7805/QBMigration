# ForensicBridge Error Code Reference

**Version:** 1.0.0
**Last Updated:** 2026-01-23
**Issue:** #36 - Error Code Mapping Documentation

---

## Overview

This document provides a comprehensive reference for all error codes returned by the ForensicBridge API. Each error response includes:

- **error_code**: Machine-readable error identifier
- **error**: Human-readable error message (sanitized for security)
- **success**: Always `false` for errors

**Example Error Response:**
```json
{
  "success": false,
  "error": "Invalid input value",
  "error_code": "VALIDATION_ERROR"
}
```

---

## HTTP Status Code Mapping

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `BAD_REQUEST` | Malformed request syntax |
| 400 | `VALIDATION_ERROR` | Input validation failed |
| 401 | `AUTHENTICATION_ERROR` | Missing or invalid credentials |
| 401 | `UNAUTHORIZED` | Authentication required |
| 403 | `AUTHORIZATION_ERROR` | Insufficient permissions |
| 403 | `FORBIDDEN` | Access denied |
| 404 | `NOT_FOUND` | Resource not found |
| 409 | `CONFLICT` | Resource conflict (duplicate) |
| 409 | `ALREADY_PROCESSED` | Idempotent operation already completed |
| 413 | `PAYLOAD_TOO_LARGE` | Request body exceeds size limit |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Internal server error |
| 500 | `UNKNOWN_ERROR` | Unexpected error occurred |
| 503 | `SERVICE_UNAVAILABLE` | Service temporarily unavailable |

---

## Authentication & Authorization Errors

### AUTHENTICATION_ERROR (401)
**Cause:** Invalid JWT token, expired token, or missing Authorization header
**User Action:** Re-authenticate with valid credentials
**Example:**
```json
{
  "success": false,
  "error": "Authentication failed. Please check your credentials and try again.",
  "error_code": "AUTHENTICATION_ERROR"
}
```

### UNAUTHORIZED (401)
**Cause:** No authentication provided for protected endpoint
**User Action:** Include Authorization header with valid JWT token
**Example:**
```json
{
  "success": false,
  "error": "Authentication required",
  "error_code": "UNAUTHORIZED"
}
```

### AUTHORIZATION_ERROR (403)
**Cause:** Authenticated user lacks permissions for requested resource
**User Action:** Contact administrator for access
**Example:**
```json
{
  "success": false,
  "error": "You do not have permission to access this resource",
  "error_code": "AUTHORIZATION_ERROR"
}
```

### FORBIDDEN (403)
**Cause:** Access explicitly denied (e.g., tier restrictions, blocked account)
**User Action:** Upgrade tier or contact support
**Example:**
```json
{
  "success": false,
  "error": "Access denied",
  "error_code": "FORBIDDEN"
}
```

---

## Validation Errors

### VALIDATION_ERROR (400)
**Cause:** Request body or parameters failed validation
**User Action:** Check required fields, data types, and format constraints
**Common Reasons:**
- Missing required field
- Invalid data type (string instead of integer)
- Value out of allowed range
- Invalid email/phone format
- File format not supported

**Example:**
```json
{
  "success": false,
  "error": "Invalid input value",
  "error_code": "VALIDATION_ERROR"
}
```

### BAD_REQUEST (400)
**Cause:** Malformed request (invalid JSON, incorrect Content-Type)
**User Action:** Fix request syntax and headers
**Example:**
```json
{
  "success": false,
  "error": "Invalid request",
  "error_code": "BAD_REQUEST"
}
```

---

## Migration-Specific Errors

### MIGRATION_NOT_FOUND (404)
**Cause:** Migration ID does not exist or user lacks access
**User Action:** Verify migration_id is correct
**Example:**
```json
{
  "success": false,
  "error": "Migration not found",
  "error_code": "NOT_FOUND"
}
```

### MIGRATION_ALREADY_STARTED (409)
**Cause:** Attempting to start migration that is already in progress
**User Action:** Wait for current migration to complete
**Example:**
```json
{
  "success": false,
  "error": "Migration already in progress",
  "error_code": "CONFLICT"
}
```

### MIGRATION_FAILED (500)
**Cause:** Migration encountered unrecoverable error
**User Action:** Review error logs and retry or contact support
**Example:**
```json
{
  "success": false,
  "error": "Migration operation failed. Please contact support if the issue persists.",
  "error_code": "INTERNAL_ERROR"
}
```

### INSUFFICIENT_CREDITS (403)
**Cause:** User has no remaining migration credits
**User Action:** Purchase additional migration credits
**Example:**
```json
{
  "success": false,
  "error": "Insufficient migration credits. Please purchase additional credits.",
  "error_code": "AUTHORIZATION_ERROR"
}
```

### TRIAL_BALANCE_MISMATCH (500)
**Cause:** Trial balance verification failed (discrepancy > $0.01)
**User Action:** Review source data for accuracy
**Example:**
```json
{
  "success": false,
  "error": "Trial balance reconciliation failed",
  "error_code": "INTERNAL_ERROR"
}
```

---

## File Upload Errors

### PAYLOAD_TOO_LARGE (413)
**Cause:** File size exceeds maximum allowed (default: 5GB)
**User Action:** Use multipart upload for large files
**Example:**
```json
{
  "success": false,
  "error": "Request body exceeds maximum allowed size (5120MB)",
  "error_code": "PAYLOAD_TOO_LARGE"
}
```

### UNSUPPORTED_FILE_FORMAT (400)
**Cause:** File format not supported (must be .QBW, .QBB, .QBM)
**User Action:** Export from QuickBooks Desktop in supported format
**Example:**
```json
{
  "success": false,
  "error": "Failed to upload file. Please check the file format and try again.",
  "error_code": "VALIDATION_ERROR"
}
```

### ENCRYPTION_ERROR (500)
**Cause:** Failed to encrypt uploaded data
**User Action:** Retry upload or contact support
**Example:**
```json
{
  "success": false,
  "error": "An error occurred processing your request. Please try again later.",
  "error_code": "INTERNAL_ERROR"
}
```

---

## Rate Limiting Errors

### RATE_LIMIT_EXCEEDED (429)
**Cause:** Too many requests from same IP/user
**User Action:** Wait before retrying (see Retry-After header)
**Rate Limits:**
- Authentication: 5 attempts per 15 minutes
- File Upload: 10 uploads per hour
- API General: 100 requests per minute

**Example:**
```json
{
  "success": false,
  "error": "Rate limit exceeded. Please try again later.",
  "error_code": "RATE_LIMIT_EXCEEDED"
}
```

**Response Headers:**
- `Retry-After`: Seconds until rate limit resets
- `X-RateLimit-Limit`: Total requests allowed per window
- `X-RateLimit-Remaining`: Requests remaining in current window
- `X-RateLimit-Reset`: Unix timestamp when limit resets

---

## Webhook Errors

### INVALID_SIGNATURE (401)
**Cause:** Webhook signature verification failed
**User Action:** Verify WEBHOOK_SECRET is correctly configured
**Example:**
```json
{
  "success": false,
  "error": "Webhook verification failed: Invalid signature",
  "error_code": "AUTHENTICATION_ERROR"
}
```

### WEBHOOK_EXPIRED (401)
**Cause:** Webhook timestamp too old (> 5 minutes)
**User Action:** Ensure system clocks are synchronized
**Example:**
```json
{
  "success": false,
  "error": "Webhook verification failed: Webhook expired (older than 300 seconds)",
  "error_code": "AUTHENTICATION_ERROR"
}
```

### ALREADY_PROCESSED (409)
**Cause:** Webhook with same X-Webhook-Id already processed (idempotency)
**User Action:** No action needed (idempotent operation)
**Example:**
```json
{
  "success": true,
  "message": "Already processed",
  "idempotent": true
}
```

---

## Database & Infrastructure Errors

### DATABASE_ERROR (500)
**Cause:** Database operation failed
**User Action:** Retry operation or contact support
**Example:**
```json
{
  "success": false,
  "error": "Database operation failed. Please try again later.",
  "error_code": "INTERNAL_ERROR"
}
```

### SERVICE_UNAVAILABLE (503)
**Cause:** Service temporarily unavailable (maintenance, overload)
**User Action:** Retry with exponential backoff
**Example:**
```json
{
  "success": false,
  "error": "Service temporarily unavailable",
  "error_code": "SERVICE_UNAVAILABLE"
}
```

### AWS_SERVICE_ERROR (500)
**Cause:** AWS operation failed (S3, EC2, etc.)
**User Action:** Retry or contact support
**Example:**
```json
{
  "success": false,
  "error": "Cloud service operation failed. Please try again later.",
  "error_code": "INTERNAL_ERROR"
}
```

---

## Payment & Billing Errors

### PAYMENT_FAILED (400)
**Cause:** Payment processing failed
**User Action:** Verify payment information and retry
**Example:**
```json
{
  "success": false,
  "error": "Payment processing failed. Please verify your payment information.",
  "error_code": "VALIDATION_ERROR"
}
```

### SUBSCRIPTION_EXPIRED (403)
**Cause:** User subscription has expired
**User Action:** Renew subscription
**Example:**
```json
{
  "success": false,
  "error": "Subscription expired. Please renew to continue.",
  "error_code": "AUTHORIZATION_ERROR"
}
```

---

## Security Error Messages

**IMPORTANT:** For security reasons, detailed error messages are **never** exposed in production. All errors are sanitized to prevent information disclosure.

### What is NOT exposed:
- File system paths (`/home/user/...`, `/var/...`)
- Database schema (table names, column names)
- Stack traces and line numbers
- AWS credentials or API keys
- Internal module names

### What IS exposed:
- Generic error categories (e.g., "Invalid input value")
- User-actionable guidance (e.g., "Please check your credentials")
- HTTP status codes and error_code identifiers

**Development vs Production:**

| Environment | Error Detail Level | Stack Traces | Internal Paths |
|-------------|-------------------|--------------|----------------|
| Development | Full details | Yes | Yes |
| Production | Sanitized only | No | No |

---

## Retry Strategy

For transient errors (5xx status codes), implement exponential backoff:

```python
import time
import requests

def retry_with_backoff(url, max_retries=4):
    base_delay = 2  # seconds
    for attempt in range(max_retries):
        try:
            response = requests.post(url)
            if response.status_code < 500:
                return response
        except requests.exceptions.RequestException:
            pass

        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)  # 2s, 4s, 8s, 16s
            time.sleep(delay)

    raise Exception("Max retries exceeded")
```

---

## Support Contact

If you encounter persistent errors:

1. **Check Status Page**: https://status.forensicbridge.com
2. **Review Logs**: Check server logs for detailed error information
3. **Contact Support**: support@forensicbridge.com
4. **Include:**
   - Error code and HTTP status
   - Request ID (X-Request-ID header)
   - Timestamp of error
   - Steps to reproduce

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-23 | 1.0.0 | Initial error code documentation (Issue #36) |

---

**Related Documentation:**
- [API Authentication Guide](./API_AUTHENTICATION.md)
- [Webhook Integration Guide](./WEBHOOKS.md)
- [Rate Limiting Policy](./RATE_LIMITS.md)

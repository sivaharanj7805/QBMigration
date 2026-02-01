# ForensicBridge API Versioning and Deprecation Policy

**Version:** 1.0
**Effective Date:** February 1, 2026
**Last Updated:** February 1, 2026

---

## 1. API Versioning Strategy

### 1.1 Version Format

ForensicBridge uses URI path versioning:

```
https://api.forensicbridge.io/api/v{major}/resource
```

**Examples:**
- `https://api.forensicbridge.io/api/v1/migrations`
- `https://api.forensicbridge.io/api/v2/migrations`

### 1.2 Version Lifecycle

| Stage | Duration | Support Level |
|-------|----------|---------------|
| **Current** | Ongoing | Full support, new features |
| **Supported** | 24 months | Bug fixes, security patches |
| **Deprecated** | 12 months | Security patches only |
| **Sunset** | - | No support, returns 410 Gone |

### 1.3 Current API Versions

| Version | Status | Release Date | End of Life |
|---------|--------|--------------|-------------|
| **v1** | Current | Feb 1, 2026 | TBD |

---

## 2. Semantic Versioning

### 2.1 Version Components

```
v{MAJOR}.{MINOR}.{PATCH}
  │       │       └── Bug fixes, no API changes
  │       └────────── New features, backwards compatible
  └──────────────── Breaking changes
```

### 2.2 What Constitutes a Breaking Change

**Breaking changes (require major version bump):**
- Removing an endpoint
- Removing a request/response field
- Changing a field's data type
- Changing authentication requirements
- Changing error response format
- Changing rate limit behavior

**Non-breaking changes (minor version bump):**
- Adding new endpoints
- Adding new optional request fields
- Adding new response fields
- Adding new error codes
- Increasing rate limits
- Performance improvements

---

## 3. Deprecation Process

### 3.1 Deprecation Timeline

```
Day 0          Day 90         Day 180        Day 365
│              │              │              │
▼              ▼              ▼              ▼
┌──────────────┬──────────────┬──────────────┐
│ Announced    │ Deprecated   │ Sunset       │
│ (Warning)    │ (Last Call)  │ (410 Gone)   │
└──────────────┴──────────────┴──────────────┘
```

### 3.2 Deprecation Stages

#### Stage 1: Announced (Day 0)
- Deprecation notice added to documentation
- `Deprecation: true` header added to responses
- Email notification to all API consumers
- Changelog updated

#### Stage 2: Deprecated (Day 90)
- `Sunset: {date}` header added to responses
- Warning messages in response body
- Migration guide published
- Reminder emails sent monthly

#### Stage 3: Sunset (Day 365)
- Endpoint returns `410 Gone`
- Response includes migration instructions
- Logs show which clients are affected
- Support available for migration help

### 3.3 Deprecation Headers

```http
HTTP/1.1 200 OK
Deprecation: true
Sunset: Sat, 01 Feb 2027 00:00:00 GMT
Link: <https://api.forensicbridge.io/api/v2/migrations>; rel="successor-version"
X-Deprecation-Notice: This endpoint is deprecated. Please migrate to /api/v2/migrations by Feb 1, 2027.
```

---

## 4. Migration Support

### 4.1 Migration Resources

For each deprecated endpoint, we provide:
- Migration guide with before/after examples
- SDK updates with backwards compatibility
- Sandbox environment for testing
- Office hours for migration questions

### 4.2 Migration Guide Template

```markdown
# Migration Guide: v1 → v2

## Summary
Endpoint `/api/v1/migrations` is being replaced by `/api/v2/migrations`

## Timeline
- Deprecation announced: Feb 1, 2026
- Deprecated status: May 1, 2026
- Sunset date: Feb 1, 2027

## Changes

### Request Changes
| v1 Field | v2 Field | Notes |
|----------|----------|-------|
| `file_name` | `filename` | Renamed |
| `company` | `company_name` | Renamed |
| - | `source_version` | New required field |

### Response Changes
| v1 Field | v2 Field | Notes |
|----------|----------|-------|
| `id` | `migration_id` | Now UUID format |
| `status` | `status` | No change |

### Code Examples

**Before (v1):**
```python
response = client.post('/api/v1/migrations', json={
    'file_name': 'company.qbw',
    'company': 'Acme Corp'
})
```

**After (v2):**
```python
response = client.post('/api/v2/migrations', json={
    'filename': 'company.qbw',
    'company_name': 'Acme Corp',
    'source_version': 'QuickBooks 2024'
})
```
```

---

## 5. Communication Plan

### 5.1 Notification Channels

| Channel | Audience | Timing |
|---------|----------|--------|
| Email | All registered developers | Immediate |
| In-app banner | Dashboard users | Immediate |
| API response headers | All API consumers | Immediate |
| Changelog | Public | Within 24 hours |
| Developer blog | Public | Within 1 week |
| Status page | Public | If service impact |

### 5.2 Email Templates

**Deprecation Announcement:**
```
Subject: [Action Required] ForensicBridge API Deprecation Notice

Dear Developer,

We are deprecating the following API endpoint(s):
- GET /api/v1/migrations (sunset: Feb 1, 2027)

Please migrate to the new endpoint:
- GET /api/v2/migrations

Migration guide: https://docs.forensicbridge.io/migration/v1-to-v2

Timeline:
- May 1, 2026: Deprecated status begins
- Feb 1, 2027: Endpoint sunset (returns 410 Gone)

Need help? Contact support@forensicbridge.io

Best regards,
ForensicBridge Engineering Team
```

---

## 6. Backwards Compatibility

### 6.1 Compatibility Guarantees

Within a major version, we guarantee:
- Existing endpoints remain functional
- Existing request fields remain valid
- Existing response fields remain present
- Error codes remain consistent
- Authentication methods remain valid

### 6.2 SDK Support

| SDK | v1 Support | v2 Support |
|-----|------------|------------|
| Python | ✅ | ✅ (when available) |
| JavaScript | ✅ | ✅ (when available) |
| C# | ✅ | ✅ (when available) |

SDKs automatically handle:
- Version negotiation
- Deprecation warnings
- Backwards compatibility shims

---

## 7. Exception Process

### 7.1 Extended Support Requests

Enterprise customers may request extended support for deprecated APIs:
1. Submit request 90 days before sunset
2. Provide migration timeline and blockers
3. Subject to approval by engineering leadership
4. Maximum extension: 6 months
5. May require additional support fees

### 7.2 Emergency Deprecation

In rare cases (security vulnerabilities, legal requirements), we may:
- Shorten deprecation timeline with justification
- Provide 30-day minimum notice
- Offer priority migration support
- Waive standard fees for migration assistance

---

## 8. Rate Limiting by Version

### 8.1 Rate Limits

| Version | Standard | Professional | Enterprise |
|---------|----------|--------------|------------|
| **v1** (Current) | 100/min | 500/min | 2000/min |
| **Deprecated** | 50/min | 250/min | 1000/min |

Note: Deprecated versions have reduced rate limits to encourage migration.

### 8.2 Rate Limit Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1706745600
X-RateLimit-Version: v1
```

---

## 9. Documentation

### 9.1 API Documentation Requirements

Each API version must have:
- OpenAPI 3.0 specification
- Interactive documentation (Swagger UI)
- Code examples in 3+ languages
- Changelog with all changes
- Migration guide (if not initial version)

### 9.2 Documentation URLs

| Version | Documentation | OpenAPI Spec |
|---------|---------------|--------------|
| v1 | https://docs.forensicbridge.io/api/v1 | https://api.forensicbridge.io/api/v1/openapi.yaml |
| v2 | https://docs.forensicbridge.io/api/v2 | https://api.forensicbridge.io/api/v2/openapi.yaml |

---

## 10. Changelog

### v1.0.0 (February 1, 2026)
- Initial API release
- Authentication endpoints
- Migration management endpoints
- QBO OAuth integration
- File upload with hybrid encryption
- Health check endpoints

---

**Document Control:**
- Version: 1.0
- Owner: Engineering Team
- Review Cycle: Quarterly
- Next Review: May 1, 2026

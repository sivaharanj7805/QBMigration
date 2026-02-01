# ForensicBridge Service Level Agreement (SLA)

**Version:** 1.0
**Effective Date:** February 1, 2026
**Last Updated:** February 1, 2026

---

## 1. Service Availability Commitment

### 1.1 Uptime Guarantee

ForensicBridge commits to the following monthly uptime percentages:

| Tier | Monthly Uptime | Max Downtime/Month | Max Downtime/Year |
|------|----------------|--------------------|--------------------|
| **Standard** | 99.5% | 3.6 hours | 43.8 hours |
| **Professional** | 99.9% | 43.8 minutes | 8.76 hours |
| **Enterprise** | 99.95% | 21.9 minutes | 4.38 hours |

### 1.2 Uptime Calculation

```
Uptime % = ((Total Minutes in Month - Downtime Minutes) / Total Minutes in Month) × 100
```

**Excluded from downtime calculation:**
- Scheduled maintenance windows (see Section 3)
- Force majeure events
- Customer-caused issues
- Third-party service outages (AWS, Intuit, Stripe)

---

## 2. Incident Response Times

### 2.1 Severity Definitions

| Severity | Definition | Examples |
|----------|------------|----------|
| **P1 - Critical** | Complete service outage affecting all users | API down, data loss risk |
| **P2 - High** | Major feature unavailable, no workaround | Migration processing halted |
| **P3 - Medium** | Feature degraded, workaround available | Slow response times |
| **P4 - Low** | Minor issue, minimal impact | UI cosmetic issues |

### 2.2 Response Time Commitments

| Severity | Initial Response | Status Update | Target Resolution |
|----------|------------------|---------------|-------------------|
| **P1** | 15 minutes | Every 30 minutes | 4 hours |
| **P2** | 1 hour | Every 2 hours | 8 hours |
| **P3** | 4 hours | Every 8 hours | 48 hours |
| **P4** | 24 hours | As needed | 10 business days |

### 2.3 Support Hours

- **Standard Tier:** Business hours (9 AM - 6 PM EST, Mon-Fri)
- **Professional Tier:** Extended hours (7 AM - 10 PM EST, Mon-Fri)
- **Enterprise Tier:** 24/7/365

---

## 3. Scheduled Maintenance

### 3.1 Maintenance Windows

| Type | Frequency | Window | Advance Notice |
|------|-----------|--------|----------------|
| **Routine** | Weekly | Sunday 2:00 - 4:00 AM EST | 48 hours |
| **Security** | As needed | Any time | 24 hours (or immediate for critical) |
| **Major Upgrade** | Quarterly | Saturday 11 PM - Sunday 5 AM EST | 14 days |

### 3.2 Maintenance Notification

Notifications sent via:
- Email to account administrators
- In-app notification banner
- Status page (status.forensicbridge.io)

---

## 4. Service Credits

### 4.1 Credit Calculation

If monthly uptime falls below guaranteed level:

| Uptime Achieved | Service Credit |
|-----------------|----------------|
| 99.0% - 99.5% | 10% of monthly fee |
| 98.0% - 99.0% | 25% of monthly fee |
| 95.0% - 98.0% | 50% of monthly fee |
| < 95.0% | 100% of monthly fee |

### 4.2 Credit Request Process

1. Submit credit request within 30 days of incident
2. Include: Account ID, incident date/time, affected services
3. Credits applied to next billing cycle
4. Maximum credit: 100% of monthly fee

### 4.3 Credit Exclusions

Credits not applicable for:
- Scheduled maintenance
- Beta/preview features
- Customer network issues
- Abuse or policy violations

---

## 5. Data Protection

### 5.1 Data Durability

| Data Type | Durability | Redundancy |
|-----------|------------|------------|
| Migration Data | 99.999999999% (11 9s) | Multi-AZ S3 |
| Database | 99.99% | Multi-AZ RDS |
| Backups | 99.999999999% | Cross-region S3 |

### 5.2 Recovery Objectives

| Metric | Standard | Professional | Enterprise |
|--------|----------|--------------|------------|
| **RPO** (Recovery Point) | 24 hours | 1 hour | 15 minutes |
| **RTO** (Recovery Time) | 8 hours | 4 hours | 1 hour |

### 5.3 Data Retention

- Active migration data: Deleted after 24 hours
- Migration metadata: 90 days
- Audit logs: 7 years (CRA IC05-1R1 compliance)
- Account data: 365 days after closure

---

## 6. Performance Guarantees

### 6.1 API Response Times

| Endpoint Category | P95 Response Time |
|-------------------|-------------------|
| Authentication | < 500ms |
| File Upload (initiate) | < 1 second |
| Migration Status | < 200ms |
| Health Check | < 100ms |

### 6.2 Throughput

| Metric | Guaranteed |
|--------|------------|
| Concurrent migrations per account | 5 (Standard), 20 (Pro), Unlimited (Enterprise) |
| API requests per minute | 100 (Standard), 500 (Pro), 2000 (Enterprise) |
| Maximum file size | 2GB (Standard), 10GB (Pro), 50GB (Enterprise) |

---

## 7. Security Commitments

### 7.1 Security Standards

- **Encryption in Transit:** TLS 1.3
- **Encryption at Rest:** AES-256-GCM
- **Password Storage:** Argon2id
- **Key Management:** AWS KMS with automatic rotation

### 7.2 Compliance

| Standard | Status |
|----------|--------|
| GDPR | Compliant |
| PIPEDA | Compliant |
| PCI-DSS | Compliant (via Stripe) |
| SOC 2 Type II | In Progress (Target: Q4 2026) |

### 7.3 Security Incident Response

- Breach notification: Within 72 hours (GDPR/PIPEDA requirement)
- Post-incident report: Within 14 days
- Root cause analysis: Within 30 days

---

## 8. Support Services

### 8.1 Support Channels

| Channel | Standard | Professional | Enterprise |
|---------|----------|--------------|------------|
| Email | ✅ | ✅ | ✅ |
| Chat | ❌ | ✅ | ✅ |
| Phone | ❌ | ❌ | ✅ |
| Dedicated CSM | ❌ | ❌ | ✅ |
| Slack/Teams | ❌ | ❌ | ✅ |

### 8.2 Documentation

- API Documentation: https://api.forensicbridge.io/docs
- Knowledge Base: https://help.forensicbridge.io
- Status Page: https://status.forensicbridge.io

---

## 9. Limitations and Exclusions

This SLA does not apply to:

1. **Free trials** and evaluation accounts
2. **Beta features** clearly marked as such
3. **Customer-caused issues** including:
   - Misconfiguration
   - Unauthorized modifications
   - Abuse or policy violations
4. **Third-party dependencies** including:
   - QuickBooks Online API outages
   - AWS regional outages
   - Internet connectivity issues
5. **Force majeure events**

---

## 10. SLA Modifications

ForensicBridge may modify this SLA with:
- 30 days notice for improvements
- 90 days notice for reductions in service levels

Current customers retain existing SLA terms until contract renewal.

---

## 11. Contact Information

**Support:** support@forensicbridge.io
**Security:** security@forensicbridge.io
**Status Page:** https://status.forensicbridge.io
**Emergency (Enterprise):** +1-XXX-XXX-XXXX

---

**Document Control:**
- Version: 1.0
- Approved by: [Executive Team]
- Review Date: Quarterly
- Next Review: May 1, 2026

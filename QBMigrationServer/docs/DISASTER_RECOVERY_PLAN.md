# ForensicBridge Disaster Recovery Plan (DRP)

**Version:** 1.0
**Effective Date:** February 1, 2026
**Classification:** Confidential
**Owner:** Engineering Team
**Review Cycle:** Quarterly

---

## 1. Executive Summary

This Disaster Recovery Plan (DRP) defines procedures for recovering ForensicBridge services following a disaster or major incident. The plan ensures business continuity and data protection for all customers.

### 1.1 Recovery Objectives

| Metric | Target | Description |
|--------|--------|-------------|
| **RTO** (Recovery Time Objective) | 4 hours | Maximum acceptable downtime |
| **RPO** (Recovery Point Objective) | 1 hour | Maximum acceptable data loss |
| **MTTR** (Mean Time to Recovery) | 2 hours | Average recovery time |

---

## 2. Scope and Definitions

### 2.1 Covered Systems

| System | Priority | RTO | RPO |
|--------|----------|-----|-----|
| Production API (api.forensicbridge.io) | Critical | 1 hour | 15 min |
| PostgreSQL Database | Critical | 2 hours | 15 min |
| S3 Migration Storage | Critical | 1 hour | 0 (durable) |
| Redis Cache | High | 4 hours | N/A (cache) |
| Frontend Dashboard | High | 2 hours | N/A (static) |
| Monitoring/Logging | Medium | 8 hours | 1 hour |

### 2.2 Disaster Classifications

| Level | Definition | Examples | Response |
|-------|------------|----------|----------|
| **Level 1** | Minor incident | Single service degradation | On-call engineer |
| **Level 2** | Major incident | Multiple services affected | Incident Commander + Team |
| **Level 3** | Disaster | Complete regional failure | Full DR activation |

---

## 3. Infrastructure Architecture

### 3.1 Current Production Environment

```
Primary Region: ca-central-1 (Montreal)
├── VPC: 10.0.0.0/16
│   ├── Public Subnets: ALB, NAT Gateways
│   ├── Private Subnets: EC2, RDS, ElastiCache
│   └── Isolated Subnets: Database replicas
├── RDS PostgreSQL: Multi-AZ
├── ElastiCache Redis: Multi-AZ
├── S3: Cross-region replication to us-east-1
└── CloudFront: Global CDN
```

### 3.2 Backup Architecture

| Component | Backup Method | Frequency | Retention | Location |
|-----------|---------------|-----------|-----------|----------|
| PostgreSQL | Automated snapshots | Continuous | 35 days | ca-central-1 |
| PostgreSQL | Cross-region | Daily | 7 days | us-east-1 |
| S3 Data | Cross-region replication | Real-time | 90 days | us-east-1 |
| Application Config | Git + S3 | On change | Unlimited | Multi-region |
| Secrets | AWS Secrets Manager | Versioned | 30 versions | Multi-region |

---

## 4. Disaster Recovery Procedures

### 4.1 Level 1: Minor Incident (Single Service)

**Trigger:** Service health check failure, isolated errors

**Procedure:**
1. On-call engineer receives PagerDuty alert
2. Assess impact using CloudWatch dashboards
3. Check recent deployments (rollback if needed)
4. Restart affected service(s)
5. Monitor for 30 minutes
6. Document in incident log

**Estimated Recovery:** 15-30 minutes

### 4.2 Level 2: Major Incident (Multi-Service)

**Trigger:** Database connection failures, API unavailable, multiple services down

**Procedure:**
1. Incident Commander takes ownership
2. Assemble response team (Slack #incident-response)
3. Post status update to status page
4. Execute diagnostic runbook:
   ```bash
   # Check service health
   ./scripts/check_all_services.sh

   # Check database connectivity
   ./scripts/check_database.sh

   # Check AWS infrastructure
   ./scripts/check_aws_status.sh
   ```
5. Identify root cause
6. Execute appropriate recovery procedure
7. Verify recovery
8. Post-incident review within 48 hours

**Estimated Recovery:** 1-4 hours

### 4.3 Level 3: Disaster (Regional Failure)

**Trigger:** AWS region outage, data center failure, catastrophic data loss

**Procedure:**

#### Phase 1: Declaration (0-15 minutes)
1. Incident Commander declares disaster
2. Notify executive team
3. Update status page: "Major Outage - DR Activated"
4. Begin customer communication

#### Phase 2: Failover (15-60 minutes)
1. Activate DR region (us-east-1):
   ```bash
   # Promote RDS read replica to master
   aws rds promote-read-replica \
     --db-instance-identifier forensicbridge-dr-replica

   # Update Route53 to DR region
   aws route53 change-resource-record-sets \
     --hosted-zone-id $ZONE_ID \
     --change-batch file://dr-dns-failover.json

   # Deploy application to DR region
   ./scripts/deploy_to_dr.sh
   ```

2. Verify DR environment:
   ```bash
   ./scripts/verify_dr_environment.sh
   ```

3. Redirect traffic:
   - Update CloudFront origin
   - Update API Gateway
   - Update webhook endpoints

#### Phase 3: Validation (60-120 minutes)
1. Run integration tests against DR environment
2. Verify data integrity (last known good state)
3. Test critical user flows:
   - Authentication
   - Migration creation
   - QBO OAuth
   - File upload
4. Monitor error rates

#### Phase 4: Communication
1. Update status page every 30 minutes
2. Email affected customers
3. Prepare incident summary

**Estimated Recovery:** 2-4 hours

---

## 5. Data Recovery Procedures

### 5.1 Database Recovery

**Point-in-Time Recovery:**
```bash
# Restore to specific timestamp
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier forensicbridge-prod \
  --target-db-instance-identifier forensicbridge-recovered \
  --restore-time "2026-02-01T12:00:00Z"
```

**From Snapshot:**
```bash
# List available snapshots
aws rds describe-db-snapshots \
  --db-instance-identifier forensicbridge-prod

# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier forensicbridge-restored \
  --db-snapshot-identifier rds:forensicbridge-prod-2026-02-01
```

### 5.2 S3 Data Recovery

**From Versioning:**
```bash
# List object versions
aws s3api list-object-versions \
  --bucket forensicbridge-migrations \
  --prefix migrations/

# Restore specific version
aws s3api copy-object \
  --bucket forensicbridge-migrations \
  --copy-source forensicbridge-migrations/migrations/file.dat?versionId=xxx \
  --key migrations/file.dat
```

**From Cross-Region Replica:**
```bash
# Sync from DR bucket
aws s3 sync s3://forensicbridge-migrations-dr s3://forensicbridge-migrations
```

### 5.3 Application Recovery

**Rollback Deployment:**
```bash
# Identify previous working version
git log --oneline -10

# Deploy previous version
./scripts/deploy.sh --version v2.3.4

# Or use blue-green deployment
./scripts/switch_to_blue.sh
```

---

## 6. Communication Plan

### 6.1 Internal Communication

| Stakeholder | Notification Method | Timeline |
|-------------|---------------------|----------|
| On-call Engineer | PagerDuty | Immediate |
| Engineering Team | Slack #incident-response | 5 minutes |
| Executive Team | Phone + Slack | 15 minutes |
| All Staff | Email | 30 minutes |

### 6.2 External Communication

| Audience | Method | Timeline | Template |
|----------|--------|----------|----------|
| All Customers | Status Page | 15 minutes | "Investigating Issue" |
| Affected Customers | Email | 30 minutes | Incident notification |
| Enterprise Customers | Phone | 1 hour | Dedicated CSM call |
| Public | Twitter/Status | As needed | Brief update |

### 6.3 Status Page Updates

```
Template 1: Investigating
"We are investigating reports of [issue]. Services may be impacted.
Next update in 30 minutes."

Template 2: Identified
"We have identified the issue affecting [services].
Our team is working on a fix. ETA: [time]"

Template 3: Resolved
"The issue has been resolved. All services are operating normally.
We will publish a post-incident report within 48 hours."
```

---

## 7. Testing and Maintenance

### 7.1 DR Testing Schedule

| Test Type | Frequency | Duration | Participants |
|-----------|-----------|----------|--------------|
| Backup Verification | Weekly | 1 hour | Automated |
| Failover Drill (tabletop) | Monthly | 2 hours | Engineering |
| Full DR Test | Quarterly | 4 hours | Full team |
| Chaos Engineering | Ongoing | Varies | SRE team |

### 7.2 DR Test Checklist

- [ ] Verify backup integrity
- [ ] Test database failover
- [ ] Test S3 cross-region access
- [ ] Validate DNS failover
- [ ] Test application deployment to DR
- [ ] Verify monitoring in DR region
- [ ] Test customer notification system
- [ ] Document lessons learned

### 7.3 Plan Maintenance

- Review DRP quarterly
- Update after any infrastructure changes
- Update after any DR test
- Annual third-party review

---

## 8. Roles and Responsibilities

### 8.1 DR Team

| Role | Primary | Backup | Responsibilities |
|------|---------|--------|------------------|
| Incident Commander | [Name] | [Name] | Overall coordination |
| Technical Lead | [Name] | [Name] | Technical decisions |
| Communications Lead | [Name] | [Name] | Customer/stakeholder updates |
| Operations | [Name] | [Name] | Infrastructure actions |
| QA Lead | [Name] | [Name] | Validation testing |

### 8.2 Escalation Matrix

| Time Elapsed | Escalation |
|--------------|------------|
| 0 minutes | On-call engineer |
| 15 minutes | Engineering manager |
| 30 minutes | VP Engineering |
| 1 hour | CEO |
| 4 hours | Board notification |

---

## 9. Post-Incident Procedures

### 9.1 Immediate (0-24 hours)
1. Verify all services restored
2. Monitor for recurring issues
3. Begin incident timeline documentation
4. Customer communication: resolution confirmed

### 9.2 Short-term (24-72 hours)
1. Conduct blameless post-mortem
2. Document root cause analysis
3. Identify action items
4. Publish incident report to customers

### 9.3 Long-term (1-4 weeks)
1. Implement preventive measures
2. Update runbooks and documentation
3. Update DR plan if needed
4. Schedule follow-up review

---

## 10. Appendices

### Appendix A: Contact List

| Role | Name | Phone | Email |
|------|------|-------|-------|
| Primary On-call | [Name] | [Phone] | [Email] |
| Secondary On-call | [Name] | [Phone] | [Email] |
| Engineering Manager | [Name] | [Phone] | [Email] |
| VP Engineering | [Name] | [Phone] | [Email] |
| CEO | [Name] | [Phone] | [Email] |

### Appendix B: AWS Resources

| Resource | Primary (ca-central-1) | DR (us-east-1) |
|----------|------------------------|----------------|
| RDS Instance | forensicbridge-prod | forensicbridge-dr-replica |
| S3 Bucket | forensicbridge-migrations | forensicbridge-migrations-dr |
| ElastiCache | forensicbridge-redis | forensicbridge-redis-dr |
| EC2 ASG | forensicbridge-asg | forensicbridge-asg-dr |

### Appendix C: Runbook Links

- [Database Failover Runbook](./runbooks/database-failover.md)
- [S3 Recovery Runbook](./runbooks/s3-recovery.md)
- [Application Deployment Runbook](./runbooks/deployment.md)
- [DNS Failover Runbook](./runbooks/dns-failover.md)

---

**Document Control:**
- Version: 1.0
- Approved by: [VP Engineering]
- Last DR Test: [Date]
- Next DR Test: [Date]
- Review Date: Quarterly

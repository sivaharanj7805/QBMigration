# ForensicBridge Platform - Operations Runbook

**Version:** 1.0.0
**Last Updated:** 2026-02-09
**Classification:** Internal / Confidential - M&A Due Diligence
**Owner:** ForensicBridge Platform Engineering
**Review Cadence:** Quarterly (next review: 2026-05-09)

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Service Health Checks](#2-service-health-checks)
3. [Common Incidents and Response Procedures](#3-common-incidents-and-response-procedures)
4. [Deployment Procedures](#4-deployment-procedures)
5. [Database Operations](#5-database-operations)
6. [Monitoring and Alerting](#6-monitoring-and-alerting)
7. [Security Incident Response](#7-security-incident-response)
8. [Disaster Recovery](#8-disaster-recovery)
9. [Appendix](#9-appendix)

---

## 1. System Architecture Overview

### 1.1 High-Level Architecture

```
                                    ForensicBridge Platform Architecture
                                    ====================================

    CLIENT TIER                         EDGE / INGRESS                         APPLICATION TIER
   +-----------------+              +------------------------+              +------------------------+
   |                 |              |                        |              |                        |
   | QBDesktopReader |   HTTPS      |  +-----------------+  |   HTTPS      |  +------------------+  |
   | (Windows)       |------------->|  | AWS WAF         |  |------------->|  | ALB              |  |
   |                 |              |  | (Rate Limit,    |  |              |  | (TLS 1.3 Term.)  |  |
   | - QB SDK        |              |  |  SQLi, XSS)     |  |              |  +--------+---------+  |
   | - Merkle Tree   |              |  +-----------------+  |              |           |             |
   | - SHA-256 Hash  |              |                        |              |           v             |
   +-----------------+              |  +-----------------+  |              |  +------------------+  |
                                    |  | CloudFront CDN  |  |              |  | ECS Fargate      |  |
   +-----------------+              |  | (Dashboard)     |  |              |  | Cluster          |  |
   |                 |   HTTPS      |  +-----------------+  |              |  |                  |  |
   | Dashboard       |<------------>|                        |              |  | +------+ +-----+ |  |
   | (Next.js 16)    |              |  +-----------------+  |              |  | | API  | | API | |  |
   |                 |              |  | Route 53        |  |              |  | | (x2) | | (x2)| |  |
   | - React 19      |              |  | (DNS + Health)  |  |              |  | +--+---+ +--+--+ |  |
   | - Verification  |              |  +-----------------+  |              |  |    |        |     |  |
   | - Reconciliation|              |                        |              |  +----+--------+-----+  |
   +-----------------+              +------------------------+              |       |        |        |
                                                                           +-------+--------+--------+
                                                                                   |        |
                                DATA TIER                                          |        |
   +--------------------------------------------------------------------------------+--------+-------+
   |                                                                                                  |
   |  +------------------+  +------------------+  +------------------+  +-------------------+         |
   |  | RDS PostgreSQL   |  | ElastiCache      |  | S3               |  | Secrets Manager   |         |
   |  | (Multi-AZ)       |  | (Redis)          |  | (Archives)       |  |                   |         |
   |  |                  |  |                  |  |                  |  | - DB Credentials  |         |
   |  | - Extractions    |  | - Rate Limiting  |  | - QBW Archives   |  | - API Keys        |         |
   |  | - Records        |  | - Session Cache  |  | - Export Bundles  |  | - QBO Secrets     |         |
   |  | - Audit Logs     |  | - Job Queues     |  | - Backup Dumps   |  | - Encryption Keys |         |
   |  | - Verifications  |  |                  |  |                  |  |                   |         |
   |  | - Users/Auth     |  | Failover: CLOSED |  | Versioned + KMS  |  | Rotation: 90 days|         |
   |  +------------------+  +------------------+  +------------------+  +-------------------+         |
   |                                                                                                  |
   |  +------------------+  +------------------+  +------------------+                                |
   |  | CloudWatch       |  | SNS              |  | KMS              |                                |
   |  | (Logs + Metrics) |  | (Alert Routing)  |  | (Encryption)     |                                |
   |  |                  |  |                  |  |                  |                                |
   |  | - App Logs       |  | - PagerDuty      |  | - S3 SSE         |                                |
   |  | - Audit Logs     |  | - Email          |  | - RDS TDE        |                                |
   |  | - Security Logs  |  | - Slack          |  | - Secrets Enc.   |                                |
   |  +------------------+  +------------------+  +------------------+                                |
   |                                                                                                  |
   |  Region: ca-central-1 (Canadian Data Residency - PIPEDA/CRA Compliance)                         |
   +--------------------------------------------------------------------------------------------------+
```

### 1.2 Component Inventory

| Component | Technology | Instance Type | Count | Purpose |
|-----------|-----------|---------------|-------|---------|
| API Server | Flask + Gunicorn (gevent) | ECS Fargate (1 vCPU, 2GB) | 2 (min) | REST API, business logic |
| Dashboard | Next.js 16 / React 19 | CloudFront + S3 | 1 distribution | Web UI |
| Database | PostgreSQL 16 | RDS db.r6g.large (Multi-AZ) | 1 primary + 1 standby | Persistent storage |
| Cache | Redis 7 | ElastiCache cache.r6g.large | 1 node | Rate limiting, sessions |
| Object Store | S3 | Standard + IA lifecycle | 1 bucket | File archives, backups |
| Migration Workers | Python on EC2 | t3.medium (on-demand) | 0-N (auto) | QB data extraction |
| Load Balancer | ALB | Managed | 1 | TLS termination, routing |
| WAF | AWS WAF v2 | Managed | 1 WebACL | Request filtering |
| DNS | Route 53 | Managed | 1 hosted zone | DNS + health checks |
| CDN | CloudFront | Managed | 1 distribution | Static asset delivery |

### 1.3 Network Topology

| Subnet | CIDR | Resources | Internet Access |
|--------|------|-----------|----------------|
| public-1a | 10.0.1.0/24 | ALB, NAT Gateway | Direct (IGW) |
| public-1b | 10.0.2.0/24 | ALB | Direct (IGW) |
| private-1a | 10.0.10.0/24 | ECS, RDS primary | NAT Gateway |
| private-1b | 10.0.11.0/24 | ECS, RDS standby | NAT Gateway |

### 1.4 Port Reference

| Service | Port | Protocol | Source |
|---------|------|----------|--------|
| ALB (public) | 443 | HTTPS | Internet (via WAF) |
| API (internal) | 5000 | HTTP | ALB only |
| PostgreSQL | 5432 | TCP | ECS security group only |
| Redis | 6379 | TCP | ECS security group only |
| QuickBooks SDK | 8471 | TCP | Migration workers only |

---

## 2. Service Health Checks

### 2.1 API Server Health

**Endpoint:** `GET /health`

```bash
# Quick health check
curl -sf https://api.forensicbridge.ca/health | python3 -m json.tool

# Expected response (HTTP 200):
# {
#     "status": "healthy",
#     "version": "1.0.0",
#     "database": "connected",
#     "cache": "connected"
# }

# Automated check via ALB (every 30s)
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:ca-central-1:ACCOUNT_ID:targetgroup/forensicbridge-tg/xxx \
  --region ca-central-1
```

**Healthy criteria:**
- HTTP 200 response within 5 seconds
- `database` field reports `connected`
- `cache` field reports `connected`

**Degraded states:**
- `database: disconnected` -- DB unreachable, investigate RDS
- `cache: disconnected` -- Redis unreachable, rate limiting fails closed (requests blocked)

### 2.2 Database (RDS PostgreSQL)

```bash
# RDS instance status
aws rds describe-db-instances \
  --db-instance-identifier forensicbridge-prod \
  --query 'DBInstances[0].{Status:DBInstanceStatus,MultiAZ:MultiAZ,Storage:AllocatedStorage,CPU:DBInstanceClass}' \
  --region ca-central-1

# Active connections count
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=forensicbridge-prod \
  --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 60 --statistics Average \
  --region ca-central-1

# Connection check via psql (from bastion/VPN)
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge \
  -c "SELECT 1 AS health_check;"
```

**Healthy baselines:**
- Status: `available`
- Connections: 10-50 (normal), >80 (warning), >150 (critical -- pool exhaustion imminent)
- CPU: <60% (normal), >80% (warning)
- Freeable memory: >500MB
- Read/Write IOPS: <3000 sustained

### 2.3 Redis (ElastiCache)

```bash
# ElastiCache cluster status
aws elasticache describe-cache-clusters \
  --cache-cluster-id forensicbridge-prod-redis \
  --show-cache-node-info \
  --region ca-central-1

# Redis connectivity test (from within VPC)
redis-cli -h forensicbridge-prod-redis.xxxxx.ca-central-1.cache.amazonaws.com \
  -a $REDIS_PASSWORD --tls PING

# Memory usage
redis-cli -h $REDIS_HOST -a $REDIS_PASSWORD --tls INFO memory | grep used_memory_human
```

**Healthy baselines:**
- Status: `available`
- Memory: <75% used
- Evictions: 0 (warning if >0 sustained)
- Connected clients: 5-30

**CRITICAL:** Redis failure causes rate limiting to fail **closed** (all requests denied). This is by design to prevent abuse during outages, but means a Redis failure is effectively a full service outage for authenticated endpoints.

### 2.4 S3 (Archive Storage)

```bash
# Bucket accessibility
aws s3 ls s3://forensicbridge-archives-prod --region ca-central-1

# Bucket metrics (object count, total size)
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name NumberOfObjects \
  --dimensions Name=BucketName,Value=forensicbridge-archives-prod Name=StorageType,Value=AllStorageTypes \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 --statistics Average \
  --region ca-central-1

# Verify encryption is active
aws s3api get-bucket-encryption --bucket forensicbridge-archives-prod --region ca-central-1
```

### 2.5 ECS Service Health

```bash
# Service status
aws ecs describe-services \
  --cluster forensicbridge-prod \
  --services forensicbridge-api \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Deployments:deployments[*].{Status:status,Running:runningCount}}' \
  --region ca-central-1

# Recent task failures
aws ecs list-tasks \
  --cluster forensicbridge-prod \
  --service-name forensicbridge-api \
  --desired-status STOPPED \
  --region ca-central-1

# Container logs (last 30 min)
aws logs filter-log-events \
  --log-group-name /ecs/forensicbridge-api \
  --start-time $(date -u -d '30 minutes ago' +%s)000 \
  --filter-pattern "ERROR" \
  --region ca-central-1
```

### 2.6 Full Stack Verification Script

```bash
#!/bin/bash
# save as: verify-stack.sh
# Usage: ./verify-stack.sh [prod|staging]

ENV=${1:-prod}
echo "=== ForensicBridge Stack Verification (${ENV}) ==="
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# 1. API Health
echo "[1/5] API Health Check..."
API_RESP=$(curl -sf --max-time 10 https://api.forensicbridge.ca/health 2>&1)
if [ $? -eq 0 ]; then
    echo "  PASS: API responding"
    echo "  Response: ${API_RESP}"
else
    echo "  FAIL: API not responding"
fi

# 2. RDS Status
echo "[2/5] RDS Database..."
RDS_STATUS=$(aws rds describe-db-instances \
  --db-instance-identifier forensicbridge-${ENV} \
  --query 'DBInstances[0].DBInstanceStatus' --output text \
  --region ca-central-1 2>&1)
echo "  Status: ${RDS_STATUS}"

# 3. ElastiCache Status
echo "[3/5] Redis Cache..."
REDIS_STATUS=$(aws elasticache describe-cache-clusters \
  --cache-cluster-id forensicbridge-${ENV}-redis \
  --query 'CacheClusters[0].CacheClusterStatus' --output text \
  --region ca-central-1 2>&1)
echo "  Status: ${REDIS_STATUS}"

# 4. ECS Service
echo "[4/5] ECS Service..."
ECS_INFO=$(aws ecs describe-services \
  --cluster forensicbridge-${ENV} \
  --services forensicbridge-api \
  --query 'services[0].{Running:runningCount,Desired:desiredCount}' --output text \
  --region ca-central-1 2>&1)
echo "  Tasks: ${ECS_INFO}"

# 5. S3 Bucket
echo "[5/5] S3 Archive Bucket..."
aws s3 ls s3://forensicbridge-archives-${ENV} --region ca-central-1 > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  PASS: Bucket accessible"
else
    echo "  FAIL: Bucket not accessible"
fi

echo ""
echo "=== Verification Complete ==="
```

---

## 3. Common Incidents and Response Procedures

### 3.1 Database Connection Pool Exhaustion

**Symptoms:**
- API returns HTTP 503 or slow responses (>5s)
- CloudWatch alarm: `forensicbridge-db-high-connections` fires
- Health endpoint reports `database: disconnected` or times out
- Application logs: `QueuePool limit of size X overflow Y reached`

**Severity:** P1 (Service degradation/outage)

**Diagnosis:**

```bash
# 1. Check current connection count
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=forensicbridge-prod \
  --start-time $(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 60 --statistics Maximum \
  --region ca-central-1

# 2. Identify long-running queries (via bastion/VPN)
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge \
  -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
      FROM pg_stat_activity
      WHERE (now() - pg_stat_activity.query_start) > interval '1 minute'
      AND state != 'idle'
      ORDER BY duration DESC
      LIMIT 20;"

# 3. Check for idle connections consuming pool
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge \
  -c "SELECT state, count(*)
      FROM pg_stat_activity
      WHERE datname = 'forensicbridge'
      GROUP BY state;"
```

**Resolution:**

```bash
# Step 1: Terminate long-running idle connections
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge \
  -c "SELECT pg_terminate_backend(pid)
      FROM pg_stat_activity
      WHERE datname = 'forensicbridge'
      AND state = 'idle'
      AND (now() - state_change) > interval '10 minutes';"

# Step 2: If connections still high, rolling restart of ECS tasks
# This forces new connection pools to be created
aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --force-new-deployment \
  --region ca-central-1

# Step 3: Monitor recovery
watch -n 10 "aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=forensicbridge-prod \
  --start-time \$(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time \$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 60 --statistics Maximum \
  --region ca-central-1 \
  --query 'Datapoints | sort_by(@, &Timestamp) | [-1].Maximum'"
```

**Prevention:**
- SQLAlchemy pool configured: `pool_size=20, max_overflow=10, pool_recycle=3600`
- Set `pool_pre_ping=True` to detect stale connections
- Monitor connection count with CloudWatch alarms (threshold: 80% of `max_connections`)

---

### 3.2 Redis Failure (Rate Limiting Fails Closed)

**Symptoms:**
- All authenticated API requests return HTTP 429 or HTTP 503
- Health endpoint reports `cache: disconnected`
- CloudWatch alarm: `forensicbridge-redis-unreachable` fires
- Application logs: `ConnectionError: Error connecting to Redis`

**Severity:** P1 (Full service outage -- rate limiter blocks all requests)

**CRITICAL CONTEXT:** The ForensicBridge rate limiter is configured to **fail closed**. When Redis is unreachable, all rate-limited endpoints reject requests. This is a deliberate security decision to prevent abuse during cache failures, but it means Redis availability directly equals API availability for authenticated endpoints.

**Diagnosis:**

```bash
# 1. Check ElastiCache node status
aws elasticache describe-cache-clusters \
  --cache-cluster-id forensicbridge-prod-redis \
  --show-cache-node-info \
  --region ca-central-1

# 2. Check for ElastiCache events (maintenance, failover)
aws elasticache describe-events \
  --source-type cache-cluster \
  --duration 60 \
  --region ca-central-1

# 3. Verify security group allows ECS -> Redis traffic
aws ec2 describe-security-groups \
  --group-ids sg-REDIS_SG_ID \
  --region ca-central-1

# 4. Check network connectivity from ECS task
# (Exec into running container if ECS Exec is enabled)
aws ecs execute-command \
  --cluster forensicbridge-prod \
  --task TASK_ID \
  --container api \
  --interactive \
  --command "python -c \"import redis; r = redis.Redis(host='REDIS_HOST', port=6379, password='REDIS_PASS', ssl=True); print(r.ping())\""
```

**Resolution:**

```bash
# Step 1: If ElastiCache node is unhealthy, reboot it
aws elasticache reboot-cache-cluster \
  --cache-cluster-id forensicbridge-prod-redis \
  --cache-node-ids-to-reboot 0001 \
  --region ca-central-1

# Step 2: If reboot does not resolve within 5 minutes, check for
# ElastiCache maintenance events
aws elasticache describe-events \
  --source-type cache-cluster \
  --region ca-central-1

# Step 3: If persistent failure, create a new Redis node
aws elasticache create-cache-cluster \
  --cache-cluster-id forensicbridge-prod-redis-failover \
  --cache-node-type cache.r6g.large \
  --engine redis \
  --engine-version 7.0 \
  --num-cache-nodes 1 \
  --cache-subnet-group-name forensicbridge-cache-subnet \
  --security-group-ids sg-REDIS_SG_ID \
  --region ca-central-1

# Step 4: Update application REDIS_URL via Secrets Manager and redeploy
aws secretsmanager update-secret \
  --secret-id forensicbridge/prod/redis \
  --secret-string '{"url":"redis://NEW_REDIS_HOST:6379/0"}' \
  --region ca-central-1

aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --force-new-deployment \
  --region ca-central-1

# Step 5: Monitor recovery
watch -n 5 "curl -sf https://api.forensicbridge.ca/health | python3 -m json.tool"
```

**Prevention:**
- Consider ElastiCache Multi-AZ with automatic failover for production
- Set up CloudWatch alarm on `EngineCPUUtilization` and `CurrConnections`
- Test Redis failover quarterly during maintenance windows

---

### 3.3 High CPU on Migration Workers (EC2)

**Symptoms:**
- CloudWatch alarm: `forensicbridge-worker-high-cpu` fires
- Migrations stall or time out
- EC2 instance status checks fail

**Severity:** P2 (Migration processing degraded)

**Diagnosis:**

```bash
# 1. Identify the affected instance(s)
aws ec2 describe-instances \
  --filters "Name=tag:Project,Values=ForensicBridge" "Name=tag:Role,Values=migration-worker" \
  --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name,Type:InstanceType,LaunchTime:LaunchTime}' \
  --region ca-central-1

# 2. Check CPU metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-XXXXXXXXX \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 300 --statistics Average \
  --region ca-central-1

# 3. Check instance system/instance status
aws ec2 describe-instance-status \
  --instance-ids i-XXXXXXXXX \
  --region ca-central-1

# 4. If SSM is installed, check top processes
aws ssm send-command \
  --instance-ids i-XXXXXXXXX \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["top -bn1 | head -20","ps aux --sort=-%cpu | head -15"]' \
  --region ca-central-1
```

**Resolution:**

```bash
# Option A: If the migration is still valid, let it complete (monitor)
# Large QuickBooks files (>2GB) can legitimately cause sustained high CPU

# Option B: If the instance is stuck, terminate and let the system retry
aws ec2 terminate-instances --instance-ids i-XXXXXXXXX --region ca-central-1

# The cleanup Lambda will detect the orphaned migration and mark it for retry

# Option C: If the instance type is undersized, update the EC2 config
# Edit the EC2 instance type in environment config:
#   AWS_EC2_INSTANCE_TYPE=t3.large (upgrade from t3.medium)
```

**Prevention:**
- EC2 instances have a `MIGRATION_MAX_DURATION_HOURS=8` timeout
- Lambda cleanup function runs every 15 minutes to catch orphaned instances
- `FORCE_CLEANUP_AFTER_HOURS=48` ensures no instance runs indefinitely

---

### 3.4 S3 Upload Failures

**Symptoms:**
- Migration extraction completes but archive upload fails
- Application logs: `ClientError: An error occurred (AccessDenied)` or `EndpointConnectionError`
- Users see "Upload failed" in dashboard

**Severity:** P2 (Migrations complete but archives not stored)

**Diagnosis:**

```bash
# 1. Check S3 bucket accessibility
aws s3 ls s3://forensicbridge-archives-prod --region ca-central-1

# 2. Verify bucket policy and permissions
aws s3api get-bucket-policy --bucket forensicbridge-archives-prod --region ca-central-1
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::ACCOUNT_ID:role/QB-Migration-Instance-Role \
  --action-names s3:PutObject s3:GetObject s3:ListBucket \
  --resource-arns arn:aws:s3:::forensicbridge-archives-prod arn:aws:s3:::forensicbridge-archives-prod/*

# 3. Check for S3 service issues
aws health describe-events \
  --filter '{
    "services": ["S3"],
    "regions": ["ca-central-1"],
    "eventStatusCodes": ["open","upcoming"]
  }' --region us-east-1  # NOTE: AWS Health API is a global service; must use us-east-1 as API endpoint (no data leaves Canada)

# 4. Check VPC endpoint (if using Gateway endpoint for S3)
aws ec2 describe-vpc-endpoints \
  --filters "Name=service-name,Values=com.amazonaws.ca-central-1.s3" \
  --region ca-central-1

# 5. Review recent upload errors in logs
aws logs filter-log-events \
  --log-group-name /ecs/forensicbridge-api \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --filter-pattern '"S3" "error"' \
  --region ca-central-1
```

**Resolution:**

```bash
# If IAM permissions issue:
# Verify the ECS task role or EC2 instance profile has s3:PutObject permission
aws iam get-role-policy \
  --role-name QB-Migration-Instance-Role \
  --policy-name S3AccessPolicy \
  --region ca-central-1

# If bucket policy is blocking, update it:
aws s3api put-bucket-policy --bucket forensicbridge-archives-prod \
  --policy file://corrected-bucket-policy.json --region ca-central-1

# If network issue (VPC endpoint), verify route table
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=subnet-PRIVATE_SUBNET_ID" \
  --region ca-central-1

# Retry failed uploads (application will auto-retry up to 3 times)
# Manual retry: trigger re-extraction from dashboard
```

**Prevention:**
- S3 uploads use multipart upload with automatic retry (3 attempts)
- VPC Gateway Endpoint for S3 avoids NAT Gateway bottleneck
- `WEBHOOK_RETRY_ATTEMPTS=3` ensures upload status is reported reliably

---

### 3.5 Certificate Expiry

**Symptoms:**
- Browser shows certificate warning
- API clients fail with SSL errors
- CloudWatch alarm: `forensicbridge-cert-expiry` fires (fires at 30 days before expiry)

**Severity:** P1 (Service inaccessible if expired)

**Diagnosis:**

```bash
# 1. Check ACM certificate status and expiry
aws acm list-certificates \
  --certificate-statuses ISSUED EXPIRED \
  --region ca-central-1 \
  --query 'CertificateSummaryList[?contains(DomainName, `forensicbridge`)]'

aws acm describe-certificate \
  --certificate-arn arn:aws:acm:ca-central-1:ACCOUNT_ID:certificate/CERT_ID \
  --region ca-central-1 \
  --query 'Certificate.{Domain:DomainName,Status:Status,NotAfter:NotAfter,RenewalSummary:RenewalSummary}'

# 2. Check from external perspective
echo | openssl s_client -servername api.forensicbridge.ca -connect api.forensicbridge.ca:443 2>/dev/null | openssl x509 -noout -dates

# 3. Check CloudFront distribution certificate (for dashboard)
aws cloudfront get-distribution \
  --id DISTRIBUTION_ID \
  --query 'Distribution.DistributionConfig.ViewerCertificate' \
  --region us-east-1  # NOTE: CloudFront API is a global service; must use us-east-1 as API endpoint (no data leaves Canada)
```

**Resolution:**

```bash
# ACM certificates auto-renew if DNS validation is configured.
# If auto-renewal failed:

# Step 1: Check why renewal failed
aws acm describe-certificate \
  --certificate-arn $CERT_ARN \
  --region ca-central-1 \
  --query 'Certificate.RenewalSummary'

# Step 2: If DNS validation record is missing, re-add it
aws acm describe-certificate \
  --certificate-arn $CERT_ARN \
  --region ca-central-1 \
  --query 'Certificate.DomainValidationOptions'

# Add the CNAME record to Route 53:
aws route53 change-resource-record-sets \
  --hosted-zone-id ZONE_ID \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "_validation.forensicbridge.ca",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "_validation_value.acm-validations.aws"}]
      }
    }]
  }'

# Step 3: If certificate is expired and cannot renew, request a new one
aws acm request-certificate \
  --domain-name "*.forensicbridge.ca" \
  --subject-alternative-names "forensicbridge.ca" \
  --validation-method DNS \
  --region ca-central-1

# Step 4: Update ALB listener with new certificate ARN
aws elbv2 modify-listener \
  --listener-arn $LISTENER_ARN \
  --certificates CertificateArn=$NEW_CERT_ARN \
  --region ca-central-1
```

**Prevention:**
- Use ACM with DNS validation (auto-renewal)
- CloudWatch alarm on `DaysToExpiry` metric (threshold: 30 days)
- Monthly certificate audit in ops review

---

### 3.6 Memory Leaks

**Symptoms:**
- ECS task memory utilization steadily increases over hours/days
- CloudWatch alarm: `forensicbridge-ecs-high-memory` fires
- Tasks get OOM-killed and restarted by ECS
- Application logs: `MemoryError` or sudden task termination

**Severity:** P2 (Gradual degradation, auto-recovers via restart but causes brief outages)

**Diagnosis:**

```bash
# 1. Check ECS memory utilization trend
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ClusterName,Value=forensicbridge-prod Name=ServiceName,Value=forensicbridge-api \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 3600 --statistics Average \
  --region ca-central-1

# 2. Check if tasks are being OOM-killed
aws ecs describe-tasks \
  --cluster forensicbridge-prod \
  --tasks $(aws ecs list-tasks --cluster forensicbridge-prod \
    --service-name forensicbridge-api --desired-status STOPPED \
    --query 'taskArns[0:5]' --output text --region ca-central-1) \
  --query 'tasks[].{StopCode:stopCode,StoppedReason:stoppedReason,StoppedAt:stoppedAt}' \
  --region ca-central-1

# 3. Check Gunicorn worker restarts (GUNICORN_MAX_REQUESTS=1000)
aws logs filter-log-events \
  --log-group-name /ecs/forensicbridge-api \
  --start-time $(date -u -d '24 hours ago' +%s)000 \
  --filter-pattern '"worker restarting"' \
  --region ca-central-1
```

**Resolution:**

```bash
# Immediate: Force new deployment (restarts all tasks with fresh memory)
aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --force-new-deployment \
  --region ca-central-1

# Long-term: Gunicorn is configured with GUNICORN_MAX_REQUESTS=1000
# which automatically recycles workers after 1000 requests.
# If memory leaks persist between worker restarts, investigate application code.

# Verify max_requests is set:
aws ecs describe-task-definition \
  --task-definition forensicbridge-api \
  --query 'taskDefinition.containerDefinitions[0].environment' \
  --region ca-central-1
```

**Prevention:**
- `GUNICORN_MAX_REQUESTS=1000` recycles workers automatically
- ECS task memory hard limit (2GB) prevents runaway memory usage
- CloudWatch alarm at 80% memory utilization
- Weekly review of memory utilization trends

---

## 4. Deployment Procedures

### 4.1 Pre-Deployment Checklist

Before **every** production deployment, verify the following:

| # | Check | Command / Action | Required |
|---|-------|-----------------|----------|
| 1 | All tests pass | `cd QBMigrationServer && pytest tests/ -v` | YES |
| 2 | Test coverage >= 88% | `pytest tests/ --cov=. --cov-report=term-missing` | YES |
| 3 | No security vulnerabilities | `pip-audit` and `npm audit` | YES |
| 4 | Database migrations reviewed | Review pending Alembic migrations | YES |
| 5 | Environment variables verified | Compare staging.env vs production.env | YES |
| 6 | Rollback plan documented | Identify previous task definition version | YES |
| 7 | Staging validated | Full smoke test on staging environment | YES |
| 8 | Change window approved | Confirm maintenance window (if applicable) | YES |
| 9 | On-call engineer notified | Post in #ops-deployments channel | YES |
| 10 | Backup verified | Confirm RDS snapshot within last 24h | YES |

```bash
# Automated pre-deployment verification
echo "=== Pre-Deployment Checklist ==="

# 1. Run tests
echo "[1/5] Running test suite..."
cd /home/user/QBMigration/QBMigrationServer && pytest tests/ -q --tb=short
TEST_EXIT=$?
echo "Tests: $([ $TEST_EXIT -eq 0 ] && echo 'PASS' || echo 'FAIL')"

# 2. Check coverage
echo "[2/5] Checking coverage..."
pytest tests/ --cov=. --cov-fail-under=88 -q 2>&1 | tail -1

# 3. Verify latest RDS snapshot
echo "[3/5] Latest RDS backup..."
aws rds describe-db-snapshots \
  --db-instance-identifier forensicbridge-prod \
  --query 'DBSnapshots | sort_by(@, &SnapshotCreateTime) | [-1].{Time:SnapshotCreateTime,Status:Status}' \
  --region ca-central-1

# 4. Current production task definition (for rollback)
echo "[4/5] Current task definition (save for rollback)..."
aws ecs describe-services \
  --cluster forensicbridge-prod \
  --services forensicbridge-api \
  --query 'services[0].taskDefinition' \
  --region ca-central-1

# 5. Staging health
echo "[5/5] Staging health..."
curl -sf https://staging-api.forensicbridge.ca/health | python3 -m json.tool
```

### 4.2 Rolling Deployment Steps

ForensicBridge uses ECS rolling deployments with the following parameters:
- **Minimum healthy percent:** 100% (no downtime)
- **Maximum percent:** 200% (new tasks start before old tasks stop)
- **Health check grace period:** 120 seconds

```bash
# ============================================================
# STEP 1: Build and push new Docker image
# ============================================================
cd /home/user/QBMigration/QBMigrationServer

# Build the image with the new version tag
VERSION=$(git describe --tags --always)
docker build -t forensicbridge-api:${VERSION} .

# Tag and push to ECR
aws ecr get-login-password --region ca-central-1 | \
  docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.ca-central-1.amazonaws.com

docker tag forensicbridge-api:${VERSION} \
  ACCOUNT_ID.dkr.ecr.ca-central-1.amazonaws.com/forensicbridge-api:${VERSION}

docker tag forensicbridge-api:${VERSION} \
  ACCOUNT_ID.dkr.ecr.ca-central-1.amazonaws.com/forensicbridge-api:latest

docker push ACCOUNT_ID.dkr.ecr.ca-central-1.amazonaws.com/forensicbridge-api:${VERSION}
docker push ACCOUNT_ID.dkr.ecr.ca-central-1.amazonaws.com/forensicbridge-api:latest

# ============================================================
# STEP 2: Register new task definition
# ============================================================
# Update the image tag in the task definition JSON
# Then register:
aws ecs register-task-definition \
  --cli-input-json file://task-definition-${VERSION}.json \
  --region ca-central-1

# Capture the new revision number
NEW_REVISION=$(aws ecs describe-task-definition \
  --task-definition forensicbridge-api \
  --query 'taskDefinition.revision' --output text \
  --region ca-central-1)
echo "New task definition revision: ${NEW_REVISION}"

# ============================================================
# STEP 3: Update ECS service (triggers rolling deployment)
# ============================================================
aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --task-definition forensicbridge-api:${NEW_REVISION} \
  --region ca-central-1

# ============================================================
# STEP 4: Monitor deployment progress
# ============================================================
echo "Monitoring deployment..."
aws ecs wait services-stable \
  --cluster forensicbridge-prod \
  --services forensicbridge-api \
  --region ca-central-1

# Or watch in real-time:
watch -n 10 "aws ecs describe-services \
  --cluster forensicbridge-prod \
  --services forensicbridge-api \
  --query 'services[0].deployments[*].{Status:status,Running:runningCount,Desired:desiredCount,Revision:taskDefinition}' \
  --region ca-central-1 --output table"

# ============================================================
# STEP 5: Post-deployment verification
# ============================================================
echo "Running post-deployment checks..."

# Health check
curl -sf https://api.forensicbridge.ca/health | python3 -m json.tool

# Verify version
curl -sf https://api.forensicbridge.ca/health | python3 -c "import sys,json; print('Version:', json.load(sys.stdin).get('version','unknown'))"

# Check for errors in new task logs (last 5 min)
aws logs filter-log-events \
  --log-group-name /ecs/forensicbridge-api \
  --start-time $(date -u -d '5 minutes ago' +%s)000 \
  --filter-pattern "ERROR" \
  --region ca-central-1

echo "Deployment complete. Monitor for 15 minutes before closing change window."
```

### 4.3 Rollback Procedure

**Decision criteria for rollback:**
- Health check failing after deployment for >5 minutes
- Error rate >5% (vs baseline <0.5%)
- P95 latency >2s (vs baseline <500ms)
- Any data corruption or integrity failure

```bash
# ============================================================
# EMERGENCY ROLLBACK
# ============================================================
# Time to execute: ~3-5 minutes

# Step 1: Identify the previous stable task definition
PREVIOUS_REVISION=$((NEW_REVISION - 1))
echo "Rolling back to revision: ${PREVIOUS_REVISION}"

# Or find the last known good revision:
aws ecs list-task-definitions \
  --family-prefix forensicbridge-api \
  --sort DESC \
  --query 'taskDefinitionArns[0:5]' \
  --region ca-central-1

# Step 2: Update service to previous revision
aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --task-definition forensicbridge-api:${PREVIOUS_REVISION} \
  --region ca-central-1

# Step 3: Wait for rollback to stabilize
aws ecs wait services-stable \
  --cluster forensicbridge-prod \
  --services forensicbridge-api \
  --region ca-central-1

# Step 4: Verify health
curl -sf https://api.forensicbridge.ca/health | python3 -m json.tool

# Step 5: Notify team
echo "ROLLBACK COMPLETE: forensicbridge-api rolled back to revision ${PREVIOUS_REVISION}"
echo "Action required: Investigate root cause before re-attempting deployment"
```

### 4.4 Database Migration Deployment

Database schema changes require special handling to avoid downtime.

```bash
# Step 1: Take a manual RDS snapshot before migration
aws rds create-db-snapshot \
  --db-instance-identifier forensicbridge-prod \
  --db-snapshot-identifier "pre-migration-$(date +%Y%m%d-%H%M%S)" \
  --region ca-central-1

# Wait for snapshot to complete
aws rds wait db-snapshot-available \
  --db-snapshot-identifier "pre-migration-$(date +%Y%m%d-%H%M%S)" \
  --region ca-central-1

# Step 2: Run migration on staging first
cd /home/user/QBMigration/QBMigrationServer
FLASK_ENV=staging flask db upgrade

# Step 3: Validate staging
pytest tests/ -v --tb=short

# Step 4: Run migration on production
FLASK_ENV=production flask db upgrade

# Step 5: Verify schema
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge \
  -c "\dt forensic.*"
```

---

## 5. Database Operations

### 5.1 Backup Verification

**Automated backups:** RDS automated backups run daily at 03:00-04:00 UTC with 35-day retention.

```bash
# List recent automated backups
aws rds describe-db-snapshots \
  --db-instance-identifier forensicbridge-prod \
  --snapshot-type automated \
  --query 'DBSnapshots | sort_by(@, &SnapshotCreateTime) | [-5:].{ID:DBSnapshotIdentifier,Time:SnapshotCreateTime,Status:Status,Size:AllocatedStorage}' \
  --region ca-central-1 --output table

# Verify latest backup is within last 24 hours
LATEST_BACKUP=$(aws rds describe-db-snapshots \
  --db-instance-identifier forensicbridge-prod \
  --snapshot-type automated \
  --query 'DBSnapshots | sort_by(@, &SnapshotCreateTime) | [-1].SnapshotCreateTime' \
  --output text --region ca-central-1)
echo "Latest backup: ${LATEST_BACKUP}"

# Monthly: Restore backup to a test instance to verify integrity
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier forensicbridge-backup-test-$(date +%Y%m%d) \
  --db-snapshot-identifier $LATEST_SNAPSHOT_ID \
  --db-instance-class db.t3.medium \
  --no-multi-az \
  --region ca-central-1

# After verification, delete the test instance
aws rds delete-db-instance \
  --db-instance-identifier forensicbridge-backup-test-$(date +%Y%m%d) \
  --skip-final-snapshot \
  --region ca-central-1
```

### 5.2 Point-in-Time Recovery (PITR)

RDS supports PITR to any second within the backup retention period (35 days).

```bash
# Step 1: Determine the target restore time
# Example: Restore to 5 minutes before an incident
RESTORE_TIME="2026-02-09T14:55:00Z"

# Step 2: Restore to a new instance (does NOT overwrite production)
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier forensicbridge-prod \
  --target-db-instance-identifier forensicbridge-pitr-recovery \
  --restore-time "${RESTORE_TIME}" \
  --db-instance-class db.r6g.large \
  --vpc-security-group-ids sg-RDS_SG_ID \
  --db-subnet-group-name forensicbridge-db-subnet \
  --region ca-central-1

# Step 3: Wait for the restored instance to become available
aws rds wait db-instance-available \
  --db-instance-identifier forensicbridge-pitr-recovery \
  --region ca-central-1

# Step 4: Verify the restored data
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-pitr-recovery.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge \
  -c "SELECT count(*) FROM forensic.extractions;
      SELECT count(*) FROM forensic.records;
      SELECT max(created_at) FROM forensic.audit_logs;"

# Step 5: If data is correct, swap the application to use the restored instance
# Update DATABASE_URL in Secrets Manager
aws secretsmanager update-secret \
  --secret-id forensicbridge/prod/database \
  --secret-string '{
    "host": "forensicbridge-pitr-recovery.xxxxx.ca-central-1.rds.amazonaws.com",
    "port": 5432,
    "database": "forensicbridge",
    "username": "fbadmin",
    "password": "SECURE_PASSWORD"
  }' \
  --region ca-central-1

# Force ECS to pick up new secrets
aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --force-new-deployment \
  --region ca-central-1

# Step 6: Rename instances for clarity
aws rds modify-db-instance \
  --db-instance-identifier forensicbridge-prod \
  --new-db-instance-identifier forensicbridge-prod-old \
  --apply-immediately --region ca-central-1

aws rds modify-db-instance \
  --db-instance-identifier forensicbridge-pitr-recovery \
  --new-db-instance-identifier forensicbridge-prod \
  --apply-immediately --region ca-central-1
```

### 5.3 Schema Migration Procedure

```bash
# ============================================================
# SCHEMA MIGRATION STANDARD OPERATING PROCEDURE
# ============================================================

# Pre-migration (1 hour before)
# 1. Notify team in #ops-deployments
# 2. Take manual snapshot
aws rds create-db-snapshot \
  --db-instance-identifier forensicbridge-prod \
  --db-snapshot-identifier "pre-schema-$(date +%Y%m%d-%H%M%S)" \
  --region ca-central-1

# 3. Verify snapshot completed
aws rds wait db-snapshot-available \
  --db-snapshot-identifier "pre-schema-$(date +%Y%m%d-%H%M%S)" \
  --region ca-central-1

# Migration execution
# 4. Run on staging first, verify
cd /home/user/QBMigration/QBMigrationServer
FLASK_ENV=staging flask db upgrade
# ... run tests against staging ...

# 5. Run on production
FLASK_ENV=production flask db upgrade

# Post-migration
# 6. Verify schema
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge \
  -c "SELECT version_num FROM alembic_version;"

# 7. Run smoke tests
curl -sf https://api.forensicbridge.ca/health | python3 -m json.tool

# 8. Monitor error rates for 30 minutes
```

### 5.4 Manual Backup to S3

For additional backup protection beyond RDS automated snapshots:

```bash
# Export database to S3 (for long-term archival or cross-account transfer)
aws rds start-export-task \
  --export-task-identifier "forensicbridge-export-$(date +%Y%m%d)" \
  --source-arn arn:aws:rds:ca-central-1:ACCOUNT_ID:snapshot:pre-schema-TIMESTAMP \
  --s3-bucket-name forensicbridge-archives-prod \
  --s3-prefix db-exports/ \
  --iam-role-arn arn:aws:iam::ACCOUNT_ID:role/forensicbridge-rds-export-role \
  --kms-key-id alias/forensicbridge \
  --region ca-central-1
```

---

## 6. Monitoring and Alerting

### 6.1 CloudWatch Alarm Response Matrix

| Alarm Name | Metric | Threshold | Severity | Response |
|-----------|--------|-----------|----------|----------|
| `fb-api-5xx-rate` | HTTPCode_Target_5XX_Count | >10 per 5min | P1 | Check API logs, consider rollback |
| `fb-api-latency-p99` | TargetResponseTime (p99) | >2000ms | P2 | Check DB connections, Redis |
| `fb-db-high-cpu` | RDS CPUUtilization | >80% for 15min | P2 | Check slow queries, consider scaling |
| `fb-db-high-connections` | RDS DatabaseConnections | >150 | P1 | See Section 3.1 |
| `fb-db-low-storage` | RDS FreeStorageSpace | <10GB | P2 | Increase allocated storage |
| `fb-redis-high-memory` | ElastiCache DatabaseMemoryUsagePercentage | >75% | P2 | Check eviction policy, scale up |
| `fb-redis-unreachable` | ElastiCache ReplicationLag | N/A (missing data) | P1 | See Section 3.2 |
| `fb-ecs-high-cpu` | ECS CPUUtilization | >80% for 10min | P2 | Scale out ECS tasks |
| `fb-ecs-high-memory` | ECS MemoryUtilization | >80% | P2 | See Section 3.6 |
| `fb-cert-expiry` | ACM DaysToExpiry | <30 days | P3 | See Section 3.5 |
| `fb-waf-block-rate` | WAF BlockedRequests | >1000 per 5min | P3 | Review WAF logs for attack patterns |

### 6.2 Log Analysis Queries

**CloudWatch Logs Insights** queries for common investigations:

```
# ---- Top errors in the last hour ----
fields @timestamp, @message
| filter @message like /ERROR/
| stats count(*) as error_count by @message
| sort error_count desc
| limit 20

# ---- Slow API requests (>2 seconds) ----
fields @timestamp, @message
| filter @message like /request_duration/
| parse @message '"request_duration": *,' as duration
| filter duration > 2.0
| sort duration desc
| limit 50

# ---- Failed login attempts (brute force detection) ----
fields @timestamp, @message
| filter @message like /login_failed/ or @message like /authentication_failed/
| stats count(*) as attempts by bin(5m)
| sort attempts desc

# ---- Rate limit hits ----
fields @timestamp, @message
| filter @message like /rate_limit/ or @message like /429/
| stats count(*) as rate_limited by bin(5m)

# ---- Migration extraction errors ----
fields @timestamp, @message
| filter @message like /extraction/ and @message like /ERROR/
| sort @timestamp desc
| limit 50

# ---- Audit trail for a specific user ----
fields @timestamp, @message
| filter @message like /user_id.*TARGET_USER_ID/
| sort @timestamp asc
| limit 100

# ---- PII redaction verification ----
# Confirm that no raw emails/SSNs appear in logs
fields @timestamp, @message
| filter @message like /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}\b/
| limit 10
# Expected result: 0 matches (PII redaction should mask all emails)
```

### 6.3 Performance Baselines

These baselines were established during load testing (100 concurrent users, January 2026):

| Metric | P50 | P95 | P99 | Alert Threshold |
|--------|-----|-----|-----|----------------|
| API response time (GET) | 45ms | 120ms | 250ms | >500ms (P95) |
| API response time (POST) | 80ms | 200ms | 450ms | >1000ms (P95) |
| Database query time | 5ms | 25ms | 80ms | >200ms (P95) |
| S3 upload (10MB file) | 800ms | 1.5s | 3s | >5s |
| Login + MFA flow | 150ms | 400ms | 800ms | >2s |
| Extraction start (webhook) | 200ms | 500ms | 1.2s | >3s |
| Health check | 10ms | 30ms | 50ms | >200ms |

| Resource Metric | Normal | Warning | Critical |
|----------------|--------|---------|----------|
| ECS CPU | <50% | 50-80% | >80% |
| ECS Memory | <60% | 60-80% | >80% |
| RDS CPU | <40% | 40-80% | >80% |
| RDS Connections | 10-50 | 50-100 | >150 |
| RDS Free Storage | >50GB | 10-50GB | <10GB |
| Redis Memory | <50% | 50-75% | >75% |
| Redis Connections | 5-20 | 20-50 | >50 |
| ALB 5xx Rate | <0.1% | 0.1-1% | >1% |

### 6.4 Dashboard URLs

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| CloudWatch Main | `https://ca-central-1.console.aws.amazon.com/cloudwatch/home?region=ca-central-1#dashboards:name=ForensicBridge-Prod` | Primary ops dashboard |
| ECS Service | `https://ca-central-1.console.aws.amazon.com/ecs/home?region=ca-central-1#/clusters/forensicbridge-prod/services` | Container status |
| RDS Performance | `https://ca-central-1.console.aws.amazon.com/rds/home?region=ca-central-1#performance-insights-v2:` | Database performance |
| Sentry | `https://sentry.io/organizations/forensicbridge/issues/` | Error tracking |
| WAF Dashboard | `https://ca-central-1.console.aws.amazon.com/wafv2/homev2/web-acl/forensicbridge-waf/overview` | Security events |

---

## 7. Security Incident Response

### 7.1 Incident Severity Classification

| Level | Description | Response Time | Examples |
|-------|-------------|--------------|---------|
| SEV-1 | Active breach, data exfiltration suspected | 15 minutes | Unauthorized data access, credential compromise |
| SEV-2 | Vulnerability actively being exploited | 30 minutes | SQL injection attempts succeeding, auth bypass |
| SEV-3 | Security anomaly detected | 4 hours | Unusual access patterns, failed brute force |
| SEV-4 | Policy violation or configuration drift | 24 hours | Expired certificate, missing encryption |

### 7.2 Suspected Breach Procedure

**Immediate Actions (first 15 minutes):**

```bash
# ============================================================
# STEP 1: PRESERVE EVIDENCE (do NOT modify/delete anything yet)
# ============================================================

# Capture current state of all running tasks
aws ecs list-tasks --cluster forensicbridge-prod --region ca-central-1 > /tmp/incident-ecs-tasks-$(date +%s).json

# Capture current CloudWatch logs
aws logs create-export-task \
  --log-group-name /ecs/forensicbridge-api \
  --from $(date -u -d '24 hours ago' +%s)000 \
  --to $(date -u +%s)000 \
  --destination forensicbridge-archives-prod \
  --destination-prefix "incident-logs/$(date +%Y%m%d-%H%M%S)/" \
  --region ca-central-1

aws logs create-export-task \
  --log-group-name /forensicbridge/audit \
  --from $(date -u -d '7 days ago' +%s)000 \
  --to $(date -u +%s)000 \
  --destination forensicbridge-archives-prod \
  --destination-prefix "incident-audit-logs/$(date +%Y%m%d-%H%M%S)/" \
  --region ca-central-1

aws logs create-export-task \
  --log-group-name /forensicbridge/security \
  --from $(date -u -d '7 days ago' +%s)000 \
  --to $(date -u +%s)000 \
  --destination forensicbridge-archives-prod \
  --destination-prefix "incident-security-logs/$(date +%Y%m%d-%H%M%S)/" \
  --region ca-central-1

# Snapshot the database immediately (for forensic analysis)
aws rds create-db-snapshot \
  --db-instance-identifier forensicbridge-prod \
  --db-snapshot-identifier "incident-$(date +%Y%m%d-%H%M%S)" \
  --region ca-central-1

# ============================================================
# STEP 2: CONTAIN THE THREAT
# ============================================================

# Option A: Block suspicious IP(s) at WAF level
aws wafv2 update-ip-set \
  --name forensicbridge-blocked-ips \
  --scope REGIONAL \
  --id IP_SET_ID \
  --addresses "SUSPICIOUS_IP/32" \
  --lock-token LOCK_TOKEN \
  --region ca-central-1

# Option B: If breach is via compromised credentials, rotate immediately
# (See Section 7.4 for key rotation)

# Option C: If breach severity warrants, isolate the service
# WARNING: This takes the service offline
aws elbv2 modify-listener \
  --listener-arn $LISTENER_ARN \
  --default-actions Type=fixed-response,FixedResponseConfig='{MessageBody="Service temporarily unavailable",StatusCode="503",ContentType="text/plain"}' \
  --region ca-central-1

# ============================================================
# STEP 3: ASSESS SCOPE
# ============================================================

# Check for unauthorized data access in audit logs
aws logs filter-log-events \
  --log-group-name /forensicbridge/audit \
  --start-time $(date -u -d '7 days ago' +%s)000 \
  --filter-pattern '"unauthorized" OR "forbidden" OR "privilege_escalation"' \
  --region ca-central-1

# Check for unusual API patterns
aws logs filter-log-events \
  --log-group-name /ecs/forensicbridge-api \
  --start-time $(date -u -d '24 hours ago' +%s)000 \
  --filter-pattern '"GET /api/" AND "200"' \
  --region ca-central-1

# Check IAM credential usage (last 24h)
aws cloudtrail lookup-events \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=s3.amazonaws.com \
  --region ca-central-1
```

**Notification chain:**
1. Immediately: Engineering lead + Security lead (phone call)
2. Within 1 hour: CTO + Legal counsel
3. Within 24 hours (if PII affected): Privacy officer (PIPEDA notification obligations)
4. Within 72 hours (if PII affected): Office of the Privacy Commissioner of Canada

### 7.3 Account Lockout Mass-Trigger

If a credential stuffing attack or mass compromise is detected, lock all user accounts.

```bash
# ============================================================
# EMERGENCY: LOCK ALL USER ACCOUNTS
# ============================================================
# This prevents all user logins until accounts are individually unlocked.

# Connect to production database (via bastion/VPN)
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge << 'SQL'

-- Record the mass lockout in audit log
INSERT INTO forensic.audit_logs (action, entity_type, details, created_at)
VALUES ('mass_account_lockout', 'security_incident',
  '{"reason": "Suspected credential compromise", "operator": "ops-runbook"}',
  NOW());

-- Lock all non-admin accounts
UPDATE users SET
  is_locked = true,
  locked_at = NOW(),
  lock_reason = 'Security incident - mass lockout'
WHERE role != 'superadmin';

-- Force invalidate all active sessions
DELETE FROM sessions WHERE created_at < NOW();

-- Report affected count
SELECT count(*) AS locked_accounts FROM users WHERE is_locked = true;

SQL

# Force all ECS tasks to restart (clears in-memory session caches)
aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --force-new-deployment \
  --region ca-central-1

# Notify users via email (if email service is operational)
echo "Trigger mass notification: Account locked for security review"
```

**Unlocking accounts after investigation:**

```bash
# Selective unlock (after verifying accounts are not compromised)
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge << 'SQL'

-- Unlock specific verified accounts
UPDATE users SET
  is_locked = false,
  locked_at = NULL,
  lock_reason = NULL,
  failed_login_attempts = 0
WHERE email IN ('verified-user@example.com');

-- Log the unlock action
INSERT INTO forensic.audit_logs (action, entity_type, details, created_at)
VALUES ('account_unlock', 'security_incident',
  '{"reason": "Verified clean after security review", "operator": "ops-runbook"}',
  NOW());

SQL
```

### 7.4 Key Rotation Emergency Procedure

Rotate all secrets if a key compromise is suspected.

```bash
# ============================================================
# EMERGENCY KEY ROTATION
# Total time: ~15 minutes
# Impact: Brief service restart (rolling deployment)
# ============================================================

echo "=== Emergency Key Rotation Started at $(date -u) ==="

# 1. Generate new secrets
NEW_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
NEW_WEBHOOK_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
NEW_INTERNAL_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
NEW_ADMIN_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
NEW_KDF_SALT=$(python3 -c "import os; print(os.urandom(32).hex())")

# 2. Update Secrets Manager
aws secretsmanager update-secret \
  --secret-id forensicbridge/prod/flask-secret \
  --secret-string "{\"SECRET_KEY\": \"${NEW_SECRET_KEY}\"}" \
  --region ca-central-1

aws secretsmanager update-secret \
  --secret-id forensicbridge/prod/webhook-secret \
  --secret-string "{\"WEBHOOK_SECRET\": \"${NEW_WEBHOOK_SECRET}\"}" \
  --region ca-central-1

aws secretsmanager update-secret \
  --secret-id forensicbridge/prod/internal-api-key \
  --secret-string "{\"INTERNAL_API_KEY\": \"${NEW_INTERNAL_API_KEY}\"}" \
  --region ca-central-1

aws secretsmanager update-secret \
  --secret-id forensicbridge/prod/admin-api-key \
  --secret-string "{\"ADMIN_API_KEY\": \"${NEW_ADMIN_API_KEY}\"}" \
  --region ca-central-1

# 3. Rotate database password
NEW_DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
aws rds modify-db-instance \
  --db-instance-identifier forensicbridge-prod \
  --master-user-password "${NEW_DB_PASSWORD}" \
  --apply-immediately \
  --region ca-central-1

aws secretsmanager update-secret \
  --secret-id forensicbridge/prod/database \
  --secret-string "{
    \"host\": \"forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com\",
    \"port\": 5432,
    \"database\": \"forensicbridge\",
    \"username\": \"fbadmin\",
    \"password\": \"${NEW_DB_PASSWORD}\"
  }" \
  --region ca-central-1

# 4. Rotate Redis password
NEW_REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
aws elasticache modify-replication-group \
  --replication-group-id forensicbridge-prod-redis \
  --auth-token "${NEW_REDIS_PASSWORD}" \
  --auth-token-update-strategy ROTATE \
  --region ca-central-1

aws secretsmanager update-secret \
  --secret-id forensicbridge/prod/redis-password \
  --secret-string "{\"REDIS_PASSWORD\": \"${NEW_REDIS_PASSWORD}\"}" \
  --region ca-central-1

# 5. Rotate KMS key (creates new key version, old version still decrypts existing data)
aws kms create-key \
  --description "ForensicBridge encryption key (rotated $(date +%Y%m%d))" \
  --key-usage ENCRYPT_DECRYPT --origin AWS_KMS \
  --region ca-central-1
# Update alias to point to new key
aws kms update-alias \
  --alias-name alias/forensicbridge \
  --target-key-id NEW_KEY_ID \
  --region ca-central-1

# 6. Force service restart to pick up new credentials
aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --force-new-deployment \
  --region ca-central-1

# 7. Wait for stable
aws ecs wait services-stable \
  --cluster forensicbridge-prod \
  --services forensicbridge-api \
  --region ca-central-1

# 8. Verify health
curl -sf https://api.forensicbridge.ca/health | python3 -m json.tool

# 9. Audit log entry
echo "=== Key Rotation Complete at $(date -u) ==="
echo "Rotated: SECRET_KEY, WEBHOOK_SECRET, INTERNAL_API_KEY, ADMIN_API_KEY, DB_PASSWORD, REDIS_PASSWORD, KMS_KEY"
echo "NOTE: All existing user sessions have been invalidated. Users must re-authenticate."
```

**Post-rotation actions:**
- Verify all webhook integrations work (QBDesktopReader needs updated webhook secret)
- Update any CI/CD pipelines that use INTERNAL_API_KEY
- Confirm Lambda cleanup function can authenticate with new INTERNAL_API_KEY
- Document rotation in incident report

---

## 8. Disaster Recovery

### 8.1 RTO/RPO Targets

| Scenario | RTO (Recovery Time Objective) | RPO (Recovery Point Objective) |
|----------|------------------------------|-------------------------------|
| Single component failure (ECS task, Redis node) | 5 minutes | 0 (no data loss) |
| Database failure (RDS failover) | 10 minutes | 0 (synchronous Multi-AZ replication) |
| Full region failure (ca-central-1) | 4 hours | 1 hour (cross-region snapshot lag) |
| Data corruption (logical) | 30 minutes | 5 minutes (PITR granularity) |
| Complete infrastructure loss | 8 hours | 1 hour |
| Ransomware / malicious deletion | 4 hours | 1 hour (S3 versioning + MFA delete) |

### 8.2 Cross-Region Failover

**DR Region:** ca-west-1 (Calgary) -- maintains Canadian data residency for PIPEDA compliance.

**Pre-positioned resources (warm standby):**
- RDS cross-region read replica (asynchronous, ~1 minute lag)
- S3 cross-region replication (enabled on archives bucket)
- ECR image replication to ca-west-1
- CloudFormation template for full infrastructure in ca-west-1

```bash
# ============================================================
# CROSS-REGION FAILOVER PROCEDURE
# Execute only when ca-central-1 is confirmed unavailable
# Estimated time: 2-4 hours
# ============================================================

DR_REGION="ca-west-1"

# Step 1: Promote RDS read replica to standalone primary
aws rds promote-read-replica \
  --db-instance-identifier forensicbridge-dr-replica \
  --region ${DR_REGION}

aws rds wait db-instance-available \
  --db-instance-identifier forensicbridge-dr-replica \
  --region ${DR_REGION}

# Step 2: Deploy application infrastructure in DR region
# Using pre-staged CloudFormation template
aws cloudformation create-stack \
  --stack-name forensicbridge-dr-stack \
  --template-url https://s3.ca-west-1.amazonaws.com/forensicbridge-dr-templates/infrastructure.yaml \
  --parameters \
    ParameterKey=DatabaseEndpoint,ParameterValue=forensicbridge-dr-replica.xxxxx.ca-west-1.rds.amazonaws.com \
    ParameterKey=Environment,ParameterValue=production-dr \
  --capabilities CAPABILITY_IAM \
  --region ${DR_REGION}

aws cloudformation wait stack-create-complete \
  --stack-name forensicbridge-dr-stack \
  --region ${DR_REGION}

# Step 3: Create ElastiCache Redis in DR region (new, empty - rate limiting state is ephemeral)
aws elasticache create-cache-cluster \
  --cache-cluster-id forensicbridge-dr-redis \
  --cache-node-type cache.r6g.large \
  --engine redis --engine-version 7.0 \
  --num-cache-nodes 1 \
  --cache-subnet-group-name forensicbridge-dr-cache-subnet \
  --security-group-ids sg-DR_REDIS_SG \
  --region ${DR_REGION}

# Step 4: Deploy ECS service in DR region
aws ecs create-service \
  --cluster forensicbridge-dr \
  --service-name forensicbridge-api \
  --task-definition forensicbridge-api \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[DR_SUBNET_1,DR_SUBNET_2],securityGroups=[DR_ECS_SG],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=DR_TARGET_GROUP_ARN,containerName=api,containerPort=5000" \
  --region ${DR_REGION}

# Step 5: Update Route 53 to point to DR region
aws route53 change-resource-record-sets \
  --hosted-zone-id ZONE_ID \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "api.forensicbridge.ca",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "DR_ALB_HOSTED_ZONE_ID",
          "DNSName": "forensicbridge-dr-alb.ca-west-1.elb.amazonaws.com",
          "EvaluateTargetHealth": true
        }
      }
    }]
  }'

# Step 6: Verify DR environment
curl -sf https://api.forensicbridge.ca/health | python3 -m json.tool

echo "=== FAILOVER COMPLETE ==="
echo "Region: ${DR_REGION}"
echo "IMPORTANT: Monitor closely for 1 hour after failover"
echo "IMPORTANT: Plan fail-back to ca-central-1 when primary region recovers"
```

### 8.3 Data Restoration from S3/RDS Backups

**Scenario: Restoring from S3 archives (file-level recovery)**

```bash
# List available archives
aws s3 ls s3://forensicbridge-archives-prod/ --region ca-central-1

# Restore a specific extraction archive
aws s3 cp \
  s3://forensicbridge-archives-prod/extractions/EXTRACTION_ID/archive.zip \
  /tmp/restored-archive.zip \
  --region ca-central-1

# If S3 versioning was used and files were deleted, restore previous version
aws s3api list-object-versions \
  --bucket forensicbridge-archives-prod \
  --prefix "extractions/EXTRACTION_ID/" \
  --region ca-central-1

aws s3api get-object \
  --bucket forensicbridge-archives-prod \
  --key "extractions/EXTRACTION_ID/archive.zip" \
  --version-id "VERSION_ID" \
  /tmp/restored-archive.zip \
  --region ca-central-1
```

**Scenario: Full database restoration from RDS snapshot**

```bash
# List available snapshots (automated + manual)
aws rds describe-db-snapshots \
  --db-instance-identifier forensicbridge-prod \
  --query 'DBSnapshots | sort_by(@, &SnapshotCreateTime) | [-10:].{ID:DBSnapshotIdentifier,Time:SnapshotCreateTime,Type:SnapshotType,Status:Status}' \
  --region ca-central-1 --output table

# Restore from specific snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier forensicbridge-restored \
  --db-snapshot-identifier TARGET_SNAPSHOT_ID \
  --db-instance-class db.r6g.large \
  --vpc-security-group-ids sg-RDS_SG_ID \
  --db-subnet-group-name forensicbridge-db-subnet \
  --multi-az \
  --region ca-central-1

aws rds wait db-instance-available \
  --db-instance-identifier forensicbridge-restored \
  --region ca-central-1

# Verify data integrity
PGPASSWORD=$DB_PASSWORD psql \
  -h forensicbridge-restored.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d forensicbridge << 'SQL'

-- Verify record counts
SELECT 'extractions' AS table_name, count(*) AS row_count FROM forensic.extractions
UNION ALL SELECT 'records', count(*) FROM forensic.records
UNION ALL SELECT 'audit_logs', count(*) FROM forensic.audit_logs
UNION ALL SELECT 'verifications', count(*) FROM forensic.verifications;

-- Verify latest data timestamps
SELECT max(created_at) AS latest_extraction FROM forensic.extractions;
SELECT max(created_at) AS latest_audit FROM forensic.audit_logs;

-- Verify Merkle tree integrity (spot check)
SELECT id, merkle_root, total_records
FROM forensic.extractions
ORDER BY created_at DESC
LIMIT 5;

SQL
```

### 8.4 DR Testing Schedule

| Test | Frequency | Last Tested | Next Due | Owner |
|------|-----------|------------|----------|-------|
| RDS snapshot restore | Monthly | 2026-01-15 | 2026-02-15 | DBA |
| PITR recovery | Quarterly | 2025-12-10 | 2026-03-10 | DBA |
| Cross-region failover | Semi-annually | 2025-11-20 | 2026-05-20 | Platform Eng |
| Full DR exercise | Annually | 2025-09-01 | 2026-09-01 | All Eng |
| S3 versioned object recovery | Quarterly | 2026-01-05 | 2026-04-05 | Platform Eng |
| Key rotation drill | Quarterly | 2025-12-15 | 2026-03-15 | Security |
| Mass account lockout drill | Semi-annually | 2025-10-01 | 2026-04-01 | Security |

---

## 9. Appendix

### 9.1 Contact and Escalation Matrix

| Role | Name | Contact | Escalation Time |
|------|------|---------|----------------|
| On-call Engineer | Rotation schedule | PagerDuty | Immediate |
| Engineering Lead | TBD | Phone + Slack | 15 minutes |
| Security Lead | TBD | Phone + Slack | 15 minutes (SEV-1/2) |
| CTO | TBD | Phone | 1 hour (SEV-1) |
| AWS Support | Enterprise Support | AWS Console | As needed |
| Legal Counsel | TBD | Phone | 4 hours (data breach) |
| Privacy Officer | TBD | Phone | 24 hours (PII breach) |

### 9.2 Useful AWS CLI Shortcuts

```bash
# Add these to ~/.bashrc or ~/.zshrc for the ops team

alias fb-health='curl -sf https://api.forensicbridge.ca/health | python3 -m json.tool'
alias fb-ecs='aws ecs describe-services --cluster forensicbridge-prod --services forensicbridge-api --query "services[0].{Status:status,Running:runningCount,Desired:desiredCount}" --region ca-central-1'
alias fb-rds='aws rds describe-db-instances --db-instance-identifier forensicbridge-prod --query "DBInstances[0].{Status:DBInstanceStatus,CPU:DBInstanceClass,MultiAZ:MultiAZ}" --region ca-central-1'
alias fb-logs='aws logs tail /ecs/forensicbridge-api --since 30m --region ca-central-1'
alias fb-errors='aws logs filter-log-events --log-group-name /ecs/forensicbridge-api --start-time $(date -u -d "1 hour ago" +%s)000 --filter-pattern "ERROR" --region ca-central-1'
alias fb-deploy='aws ecs update-service --cluster forensicbridge-prod --service forensicbridge-api --force-new-deployment --region ca-central-1'
```

### 9.3 Compliance and Regulatory Notes

- **PIPEDA:** All data must remain in Canadian regions (ca-central-1 or ca-west-1). Cross-border transfer requires explicit consent.
- **CRA Requirements:** Audit logs retained for 7 years (2,555 days) per CRA record-keeping requirements.
- **Breach Notification:** Under PIPEDA, organizations must report breaches that pose a "real risk of significant harm" to the Privacy Commissioner and affected individuals.
- **Data Retention:** Migration metadata retained 90 days, user data 365 days, audit logs 7 years.

### 9.4 Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-02-09 | Platform Engineering | Initial release |

---

**Document Classification:** Internal / Confidential
**Review Status:** Current
**Next Scheduled Review:** 2026-05-09

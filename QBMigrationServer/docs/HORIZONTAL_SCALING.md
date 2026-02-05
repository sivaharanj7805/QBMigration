# Horizontal Scaling Guide

This document describes how to scale the QBMigration platform horizontally to handle increased load.

## Architecture Overview

```
                                    ┌─────────────────┐
                                    │   CloudFront    │
                                    │   (CDN/WAF)     │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │  Application    │
                                    │  Load Balancer  │
                                    └────────┬────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
           ┌────────▼────────┐     ┌────────▼────────┐     ┌────────▼────────┐
           │   Flask App     │     │   Flask App     │     │   Flask App     │
           │   (Gunicorn)    │     │   (Gunicorn)    │     │   (Gunicorn)    │
           │   Instance 1    │     │   Instance 2    │     │   Instance N    │
           └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
                    │                        │                        │
                    └────────────────────────┼────────────────────────┘
                                             │
              ┌──────────────────────────────┼──────────────────────────────┐
              │                              │                              │
     ┌────────▼────────┐           ┌────────▼────────┐           ┌────────▼────────┐
     │    PostgreSQL   │           │      Redis      │           │       S3        │
     │   (RDS Multi-AZ)│           │  (ElastiCache)  │           │   (Storage)     │
     └─────────────────┘           └─────────────────┘           └─────────────────┘
```

## Scaling Components

### 1. Flask Application Servers

**Auto Scaling Configuration:**

```yaml
# AWS Auto Scaling Group Configuration
AutoScalingGroup:
  MinSize: 2
  MaxSize: 10
  DesiredCapacity: 2

  ScalingPolicies:
    - PolicyName: ScaleUp
      ScalingAdjustment: 2
      Cooldown: 300
      MetricAggregationType: Average
      Trigger:
        MetricName: CPUUtilization
        Threshold: 70
        ComparisonOperator: GreaterThanThreshold
        Period: 60
        EvaluationPeriods: 3

    - PolicyName: ScaleDown
      ScalingAdjustment: -1
      Cooldown: 600
      Trigger:
        MetricName: CPUUtilization
        Threshold: 30
        ComparisonOperator: LessThanThreshold
        Period: 300
        EvaluationPeriods: 5
```

**Instance Sizing Recommendations:**

| Load Level | Instance Type | Workers | Concurrent Users |
|------------|---------------|---------|------------------|
| Low        | t3.small      | 4       | 50-100           |
| Medium     | t3.medium     | 8       | 100-500          |
| High       | t3.large      | 16      | 500-1000         |
| Enterprise | c5.xlarge     | 32      | 1000+            |

### 2. Database Scaling

**PostgreSQL RDS Configuration:**

```yaml
# Production RDS Configuration
RDS:
  InstanceClass: db.r5.large  # Start here
  MultiAZ: true               # High availability
  StorageType: gp3            # SSD storage
  IOPS: 3000                  # Provisioned IOPS

  ReadReplicas:
    - Region: ca-central-1a   # Same region for low latency
    - Region: ca-central-1b   # Cross-AZ for HA
```

**Connection Pooling:**

```python
# config.py settings for high-load scenarios
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 20,           # Increase from 10
    'pool_recycle': 1800,      # Recycle every 30 min
    'pool_pre_ping': True,     # Verify connections
    'pool_timeout': 30,
    'max_overflow': 40,        # Allow 60 total connections
}
```

**PgBouncer Configuration (Optional):**

```ini
# pgbouncer.ini for connection pooling
[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 50
reserve_pool_size = 10
```

### 3. Redis Scaling

**ElastiCache Configuration:**

```yaml
# Production ElastiCache Configuration
ElastiCache:
  NodeType: cache.r5.large
  NumCacheNodes: 2  # Primary + Replica
  AutomaticFailover: true

  # For high-traffic rate limiting
  ClusterMode: enabled
  NumNodeGroups: 3
  ReplicasPerNodeGroup: 1
```

**Rate Limiting Distribution:**

Rate limiting is automatically distributed across Redis nodes. No code changes required.

### 4. Celery Workers

**Scaling Celery Workers:**

```bash
# Docker Compose scaling
docker-compose up -d --scale celery-worker=5

# Kubernetes scaling
kubectl scale deployment celery-worker --replicas=5
```

**Worker Configuration by Task Type:**

```python
# celery_worker.py configuration for scaled deployment
celery.conf.update(
    worker_prefetch_multiplier=1,  # Fair distribution
    task_acks_late=True,           # Reliable delivery

    # Task routing for specialization
    task_routes={
        'tasks.execute_migration': {'queue': 'migrations'},
        'tasks.cleanup_*': {'queue': 'maintenance'},
        'tasks.send_*': {'queue': 'notifications'},
    }
)
```

### 5. S3 Storage

S3 scales automatically. Optimize with:

```python
# Multi-part upload configuration
MULTIPART_THRESHOLD = 100 * 1024 * 1024  # 100MB
MULTIPART_CHUNKSIZE = 50 * 1024 * 1024   # 50MB chunks
MAX_CONCURRENT_UPLOADS = 10
```

## Load Testing

### Prerequisites

```bash
pip install locust
```

### Load Test Script

```python
# locustfile.py
from locust import HttpUser, task, between

class QBMigrationUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        # Login
        response = self.client.post("/api/auth/login", json={
            "email": "loadtest@example.com",
            "password": "testpassword123"
        })
        self.token = response.json().get("token")

    @task(3)
    def get_migrations(self):
        self.client.get(
            "/api/migrations",
            headers={"Authorization": f"Bearer {self.token}"}
        )

    @task(1)
    def get_dashboard(self):
        self.client.get(
            "/api/dashboard/stats",
            headers={"Authorization": f"Bearer {self.token}"}
        )
```

### Running Load Tests

```bash
# Run load test
locust -f locustfile.py --host=https://your-api.com

# Headless mode
locust -f locustfile.py --host=https://your-api.com \
    --users 100 --spawn-rate 10 --run-time 5m --headless
```

### Target Metrics

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Response Time (p95) | < 500ms | > 1s | > 3s |
| Error Rate | < 0.1% | > 1% | > 5% |
| Throughput | > 100 rps | < 50 rps | < 10 rps |
| CPU Utilization | < 70% | > 80% | > 90% |
| Memory Utilization | < 80% | > 85% | > 95% |

## Monitoring for Scale

### Prometheus Queries

```promql
# Request rate per instance
sum(rate(http_requests_total[5m])) by (instance)

# P95 latency
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket[5m])
)

# Error rate
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
/ sum(rate(http_requests_total[5m]))

# Active migrations
migrations_in_progress
```

### CloudWatch Alarms

```yaml
Alarms:
  - Name: HighCPU
    Metric: CPUUtilization
    Threshold: 80
    Period: 300
    Action: ScaleUp

  - Name: HighLatency
    Metric: TargetResponseTime
    Threshold: 1.0
    Period: 60
    Action: AlertOps

  - Name: High5xxRate
    Metric: HTTPCode_Target_5XX_Count
    Threshold: 10
    Period: 60
    Action: AlertOps
```

## Deployment Checklist

### Pre-Scaling

- [ ] Enable Redis cluster mode
- [ ] Configure RDS read replicas
- [ ] Setup CloudWatch dashboards
- [ ] Configure auto-scaling policies
- [ ] Test failover scenarios

### During Scaling

- [ ] Monitor error rates
- [ ] Watch database connections
- [ ] Check Redis memory usage
- [ ] Verify Celery task queue depth

### Post-Scaling

- [ ] Validate response times
- [ ] Check data consistency
- [ ] Review cost impact
- [ ] Update capacity planning docs

## Troubleshooting

### Connection Pool Exhaustion

**Symptoms:** `QueuePool limit` errors

**Solution:**
```python
# Increase pool size
SQLALCHEMY_ENGINE_OPTIONS['pool_size'] = 30
SQLALCHEMY_ENGINE_OPTIONS['max_overflow'] = 60
```

### Rate Limit Inconsistency

**Symptoms:** Rate limits not applied evenly

**Solution:** Ensure all instances use the same Redis cluster:
```bash
REDIS_URL=redis://elasticache-cluster.xxx.cache.amazonaws.com:6379
```

### Session Stickiness Issues

**Symptoms:** Users logged out randomly

**Solution:** Use Redis for session storage:
```python
SESSION_TYPE = 'redis'
SESSION_REDIS = Redis(host='elasticache-cluster')
```

## Cost Optimization

### Reserved Instances

For predictable load, use Reserved Instances:
- 1-year commitment: 30-40% savings
- 3-year commitment: 50-60% savings

### Spot Instances for Workers

Celery workers can use Spot Instances:
```yaml
# AWS Auto Scaling with Spot
MixedInstancesPolicy:
  InstancesDistribution:
    OnDemandBaseCapacity: 1
    OnDemandPercentageAboveBaseCapacity: 25
    SpotAllocationStrategy: capacity-optimized
```

### Scheduled Scaling

For predictable traffic patterns:
```yaml
ScheduledActions:
  - Name: ScaleUpMorning
    Schedule: "cron(0 8 * * MON-FRI)"
    DesiredCapacity: 5

  - Name: ScaleDownEvening
    Schedule: "cron(0 20 * * *)"
    DesiredCapacity: 2
```

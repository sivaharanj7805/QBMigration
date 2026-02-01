# EC2 Deployment Guide for QBMigration

This guide covers deploying QBMigration to AWS EC2 with all required services.

## Architecture Overview

```
                    ┌─────────────────────────────────────────────┐
                    │                 EC2 Instance                 │
                    │  ┌─────────────────────────────────────────┐│
   Internet ──────► │  │              Nginx (80/443)             ││
                    │  │    Reverse Proxy + SSL Termination      ││
                    │  └────────────────┬────────────────────────┘│
                    │                   │                          │
                    │    ┌──────────────┴──────────────┐          │
                    │    ▼                             ▼          │
                    │ ┌──────────────┐    ┌───────────────────┐   │
                    │ │ Flask API    │    │ Next.js Frontend  │   │
                    │ │ (Gunicorn)   │    │ (Port 3000)       │   │
                    │ │ Port 5000    │    │                   │   │
                    │ └──────┬───────┘    └───────────────────┘   │
                    │        │                                     │
                    │        ▼                                     │
                    │ ┌──────────────┐    ┌───────────────────┐   │
                    │ │ Celery       │    │ Celery Beat       │   │
                    │ │ Worker       │    │ (Scheduler)       │   │
                    │ └──────────────┘    └───────────────────┘   │
                    │        │                    │                │
                    │        └────────┬───────────┘                │
                    │                 ▼                            │
                    │          ┌─────────────┐                     │
                    │          │   Redis     │                     │
                    │          │ (Port 6379) │                     │
                    │          └─────────────┘                     │
                    └─────────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────────┐
                    │            AWS Services                      │
                    │  ┌─────────────┐    ┌─────────────────────┐ │
                    │  │ RDS         │    │ S3 Bucket           │ │
                    │  │ PostgreSQL  │    │ (File Storage)      │ │
                    │  └─────────────┘    └─────────────────────┘ │
                    └─────────────────────────────────────────────┘
```

## Prerequisites

1. **AWS Account** with permissions to create:
   - EC2 instances
   - RDS PostgreSQL database
   - S3 bucket
   - Security groups
   - IAM roles

2. **Domain name** (optional but recommended for SSL)

3. **QuickBooks Developer Account** (for QBO integration)

## Quick Start

### 1. Launch EC2 Instance

**Recommended Instance:**
- **Type:** t3.medium (2 vCPU, 4GB RAM) minimum
- **AMI:** Ubuntu 22.04 LTS
- **Storage:** 30GB gp3 SSD
- **Security Group:** Allow ports 22 (SSH), 80 (HTTP), 443 (HTTPS)

### 2. Run Setup Script

SSH into your instance and run:

```bash
# Download and run the setup script
curl -fsSL https://raw.githubusercontent.com/sivaharanj7805/QBMigration/main/deploy/ec2/user-data.sh | sudo bash
```

Or use it as EC2 User Data during instance launch.

### 3. Configure Environment

```bash
# Edit the environment file
sudo nano /etc/qbmigration/environment
```

**Required settings:**
```bash
# Generate these values:
SECRET_KEY=$(openssl rand -base64 32)
BACKUP_ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

# Database (use your RDS endpoint)
DATABASE_URL=postgresql://qbmigration:password@your-rds.region.rds.amazonaws.com:5432/qbmigration

# CORS (your domain)
ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com

# AWS (use IAM role or access keys)
AWS_REGION=ca-central-1
AWS_S3_BUCKET=your-bucket-name
```

### 4. Start Services

```bash
sudo systemctl start qbmigration-api
sudo systemctl start qbmigration-celery-worker
sudo systemctl start qbmigration-celery-beat
sudo systemctl start qbmigration-frontend
```

### 5. Setup SSL (optional but recommended)

```bash
sudo certbot --nginx -d your-domain.com
```

### 6. Verify Deployment

```bash
# Check all services
sudo systemctl status qbmigration-api
sudo systemctl status qbmigration-frontend

# Test health endpoint
curl http://localhost/health
```

## Detailed Setup

### AWS RDS Setup

1. Create a PostgreSQL 15 instance in RDS
2. Configure security group to allow EC2 access on port 5432
3. Note the endpoint URL

```bash
# Test RDS connection from EC2
psql -h your-rds-endpoint.region.rds.amazonaws.com -U qbmigration -d qbmigration
```

### S3 Bucket Setup

1. Create an S3 bucket in your preferred region
2. Create IAM role for EC2 with S3 access:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::your-bucket-name",
                "arn:aws:s3:::your-bucket-name/*"
            ]
        }
    ]
}
```

3. Attach the IAM role to your EC2 instance

### Security Group Configuration

**Inbound Rules:**
| Port | Protocol | Source | Description |
|------|----------|--------|-------------|
| 22 | TCP | Your IP | SSH access |
| 80 | TCP | 0.0.0.0/0 | HTTP |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

**Outbound Rules:**
| Port | Protocol | Destination | Description |
|------|----------|-------------|-------------|
| 5432 | TCP | RDS Security Group | PostgreSQL |
| 443 | TCP | 0.0.0.0/0 | HTTPS (APIs, S3) |

## Service Management

### Start/Stop Services

```bash
# Individual services
sudo systemctl start qbmigration-api
sudo systemctl stop qbmigration-api
sudo systemctl restart qbmigration-api

# All services
sudo systemctl restart qbmigration-api qbmigration-celery-worker qbmigration-celery-beat qbmigration-frontend
```

### View Logs

```bash
# Real-time API logs
sudo journalctl -u qbmigration-api -f

# Frontend logs
sudo journalctl -u qbmigration-frontend -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Check Status

```bash
# All services
sudo systemctl status qbmigration-*

# Health check
curl http://localhost/health
```

## Updating the Application

Use the deployment script for updates:

```bash
sudo /opt/qbmigration/deploy/ec2/deploy.sh --branch main --restart-services
```

Or manually:

```bash
cd /opt/qbmigration
sudo -u qbmigration git pull origin main
source venv/bin/activate
pip install -r requirements.txt
cd forensicbridge-dashboard && npm ci && npm run build
sudo systemctl restart qbmigration-api qbmigration-frontend
```

## Scaling Considerations

### Horizontal Scaling

For high traffic, consider:

1. **Load Balancer:** Use AWS ALB in front of multiple EC2 instances
2. **Shared Database:** All instances connect to same RDS
3. **Shared Redis:** Use AWS ElastiCache Redis cluster
4. **Shared Storage:** S3 already handles this

### Vertical Scaling

Increase instance size for more capacity:
- t3.large (2 vCPU, 8GB) - Medium load
- t3.xlarge (4 vCPU, 16GB) - High load
- m5.xlarge (4 vCPU, 16GB) - Production

## Monitoring

### CloudWatch Metrics

Enable detailed monitoring:
```bash
aws ec2 monitor-instances --instance-ids i-xxxxx
```

### Health Checks

The API provides health endpoints:
- `/health` - Basic health check
- `/api/health` - Detailed health with DB status

### Alerts (optional)

Set up CloudWatch Alarms for:
- CPU > 80% for 5 minutes
- Memory > 80% for 5 minutes
- Disk > 80%
- 5xx errors > 10/minute

## Backup & Recovery

### Database Backups

RDS provides automated backups. Additionally:

```bash
# Manual backup
pg_dump -h your-rds-endpoint -U qbmigration qbmigration > backup.sql

# Restore
psql -h your-rds-endpoint -U qbmigration qbmigration < backup.sql
```

### Application Backups

The deploy script creates automatic backups:
```bash
ls /opt/qbmigration-backups/
```

### Recovery

```bash
# Restore from backup
cd /opt
sudo tar -xzf /opt/qbmigration-backups/backup-YYYYMMDD-HHMMSS.tar.gz
sudo systemctl restart qbmigration-api qbmigration-frontend
```

## Troubleshooting

See [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for common issues and solutions.

## Files in This Directory

| File | Description |
|------|-------------|
| `user-data.sh` | EC2 bootstrap script (run once on new instance) |
| `deploy.sh` | Deployment script for updates |
| `environment.template` | Environment variables template |
| `TROUBLESHOOTING.md` | Common issues and solutions |
| `README.md` | This file |

## Support

- GitHub Issues: https://github.com/sivaharanj7805/QBMigration/issues
- Documentation: See `/docs` directory in main repo

# ForensicBridge Platform - Complete Deployment Guide

**Version:** 1.0.0
**Last Updated:** 2026-01-25
**Classification:** Internal / M&A Due Diligence

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [AWS Infrastructure Setup](#3-aws-infrastructure-setup)
4. [Database Setup](#4-database-setup)
5. [Backend Services Deployment](#5-backend-services-deployment)
6. [QBDesktopReader Setup](#6-qbdesktopreader-setup)
7. [Dashboard Frontend Deployment](#7-dashboard-frontend-deployment)
8. [Security Configuration](#8-security-configuration)
9. [Monitoring & Logging](#9-monitoring--logging)
10. [Verification & Testing](#10-verification--testing)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ForensicBridge Architecture                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────┐     ┌─────────────────────────────────────────────────┐    │
│  │ QBDesktop   │     │              AWS ca-central-1                    │    │
│  │ Reader      │     │  (Canadian Data Residency - PIPEDA/CRA)         │    │
│  │ (Windows)   │     │                                                  │    │
│  │             │     │  ┌─────────┐  ┌─────────────┐  ┌────────────┐   │    │
│  │ - Extract   │────▶│  │   WAF   │──│     ALB     │──│   ECS      │   │    │
│  │ - Hash      │     │  └─────────┘  └─────────────┘  │  Fargate   │   │    │
│  │ - Upload    │     │                                 │            │   │    │
│  └─────────────┘     │                                 │ - API      │   │    │
│                      │                                 │ - Workers  │   │    │
│  ┌─────────────┐     │                                 └──────┬─────┘   │    │
│  │ Dashboard   │     │                                        │         │    │
│  │ (React)     │     │  ┌──────────────┐  ┌─────────────────┐ │         │    │
│  │             │◀───▶│  │  CloudFront  │  │    RDS          │◀┘         │    │
│  │ - View      │     │  │  (CDN)       │  │  PostgreSQL     │           │    │
│  │ - Verify    │     │  └──────────────┘  │  (Encrypted)    │           │    │
│  │ - Reconcile │     │                     └─────────────────┘           │    │
│  └─────────────┘     │                                                   │    │
│                      │  ┌────────────┐  ┌────────────┐  ┌────────────┐  │    │
│                      │  │ S3 Bucket  │  │ ElastiCache│  │ Secrets    │  │    │
│                      │  │ (Archives) │  │ (Redis)    │  │ Manager    │  │    │
│                      │  └────────────┘  └────────────┘  └────────────┘  │    │
│                      └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Prerequisites

### 2.1 Required Accounts & Access

| Service | Requirement |
|---------|-------------|
| AWS Account | With admin access to ca-central-1 |
| GitHub | Access to sivaharanj7805/QBMigration repository |
| Docker Hub | (Optional) For custom image storage |
| Domain | DNS access for forensicbridge.io (or your domain) |
| SSL Certificate | ACM certificate for your domain |

### 2.2 Development Tools

```bash
# Required tools with minimum versions
aws-cli >= 2.15.0
terraform >= 1.6.0
docker >= 24.0.0
docker-compose >= 2.23.0
node >= 20.0.0
npm >= 10.0.0
python >= 3.11.0
dotnet >= 8.0.0
```

### 2.3 Install Development Tools

```bash
# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# Terraform
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip && sudo mv terraform /usr/local/bin/

# Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh

# Node.js (via nvm)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install 20 && nvm use 20

# Python
sudo apt-get install python3.11 python3.11-venv python3-pip

# .NET 8
wget https://dot.net/v1/dotnet-install.sh
chmod +x dotnet-install.sh && ./dotnet-install.sh --channel 8.0
```

---

## 3. AWS Infrastructure Setup

### 3.1 Configure AWS Credentials

```bash
# Configure AWS CLI with ca-central-1 as default region
aws configure
# AWS Access Key ID: [YOUR_ACCESS_KEY]
# AWS Secret Access Key: [YOUR_SECRET_KEY]
# Default region name: ca-central-1
# Default output format: json

# Verify configuration
aws sts get-caller-identity
```

### 3.2 Create VPC and Networking

```bash
# Create VPC with private/public subnets
aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=forensicbridge-vpc}]' \
  --region ca-central-1

# Store VPC ID
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=forensicbridge-vpc" \
  --query 'Vpcs[0].VpcId' --output text)

# Create public subnets (for ALB)
aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 \
  --availability-zone ca-central-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=public-1a}]'

aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.2.0/24 \
  --availability-zone ca-central-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=public-1b}]'

# Create private subnets (for ECS, RDS)
aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.10.0/24 \
  --availability-zone ca-central-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=private-1a}]'

aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.11.0/24 \
  --availability-zone ca-central-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=private-1b}]'

# Create Internet Gateway
aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=forensicbridge-igw}]'

# Create NAT Gateway for private subnets
aws ec2 allocate-address --domain vpc
# Use the allocation ID for NAT Gateway
aws ec2 create-nat-gateway --subnet-id [PUBLIC_SUBNET_ID] --allocation-id [EIP_ALLOCATION_ID]
```

### 3.3 Create Security Groups

```bash
# ALB Security Group (public)
aws ec2 create-security-group \
  --group-name forensicbridge-alb-sg \
  --description "ALB Security Group" \
  --vpc-id $VPC_ID

ALB_SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=forensicbridge-alb-sg" \
  --query 'SecurityGroups[0].GroupId' --output text)

# Allow HTTPS from anywhere
aws ec2 authorize-security-group-ingress \
  --group-id $ALB_SG_ID --protocol tcp --port 443 --cidr 0.0.0.0/0

# ECS Security Group (private)
aws ec2 create-security-group \
  --group-name forensicbridge-ecs-sg \
  --description "ECS Security Group" \
  --vpc-id $VPC_ID

ECS_SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=forensicbridge-ecs-sg" \
  --query 'SecurityGroups[0].GroupId' --output text)

# Allow traffic from ALB only
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG_ID --protocol tcp --port 8000 \
  --source-group $ALB_SG_ID

# RDS Security Group
aws ec2 create-security-group \
  --group-name forensicbridge-rds-sg \
  --description "RDS Security Group" \
  --vpc-id $VPC_ID

RDS_SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=forensicbridge-rds-sg" \
  --query 'SecurityGroups[0].GroupId' --output text)

# Allow PostgreSQL from ECS only
aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG_ID --protocol tcp --port 5432 \
  --source-group $ECS_SG_ID
```

### 3.4 Create S3 Buckets

```bash
# Archive storage bucket (for Data Museum)
aws s3 mb s3://forensicbridge-archives-prod --region ca-central-1

# Enable versioning for audit compliance
aws s3api put-bucket-versioning \
  --bucket forensicbridge-archives-prod \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket forensicbridge-archives-prod \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "alias/aws/s3"
      }
    }]
  }'

# Block public access
aws s3api put-public-access-block \
  --bucket forensicbridge-archives-prod \
  --public-access-block-configuration '{
    "BlockPublicAcls": true,
    "IgnorePublicAcls": true,
    "BlockPublicPolicy": true,
    "RestrictPublicBuckets": true
  }'
```

---

## 4. Database Setup

### 4.1 Create RDS PostgreSQL Instance

```bash
# Create DB subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name forensicbridge-db-subnet \
  --db-subnet-group-description "ForensicBridge DB Subnets" \
  --subnet-ids [PRIVATE_SUBNET_1A_ID] [PRIVATE_SUBNET_1B_ID]

# Create parameter group for forensic auditing
aws rds create-db-parameter-group \
  --db-parameter-group-name forensicbridge-pg16 \
  --db-parameter-group-family postgres16 \
  --description "ForensicBridge PostgreSQL 16 params"

# Enable logging for audit compliance
aws rds modify-db-parameter-group \
  --db-parameter-group-name forensicbridge-pg16 \
  --parameters \
    "ParameterName=log_statement,ParameterValue=all,ApplyMethod=immediate" \
    "ParameterName=log_connections,ParameterValue=1,ApplyMethod=immediate" \
    "ParameterName=log_disconnections,ParameterValue=1,ApplyMethod=immediate"

# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier forensicbridge-prod \
  --db-instance-class db.r6g.large \
  --engine postgres \
  --engine-version 16.1 \
  --master-username fbadmin \
  --master-user-password [SECURE_PASSWORD] \
  --allocated-storage 100 \
  --storage-type gp3 \
  --storage-encrypted \
  --vpc-security-group-ids $RDS_SG_ID \
  --db-subnet-group-name forensicbridge-db-subnet \
  --db-parameter-group-name forensicbridge-pg16 \
  --backup-retention-period 35 \
  --preferred-backup-window "03:00-04:00" \
  --multi-az \
  --deletion-protection \
  --enable-cloudwatch-logs-exports '["postgresql","upgrade"]' \
  --tags Key=Project,Value=ForensicBridge
```

### 4.2 Initialize Database Schema

```bash
# Connect to RDS (via bastion or VPN)
psql -h forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com \
  -U fbadmin -d postgres

# Create database and schema
CREATE DATABASE forensicbridge;
\c forensicbridge

-- Create schema
CREATE SCHEMA IF NOT EXISTS forensic;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Core tables
CREATE TABLE forensic.extractions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_file_path VARCHAR(500) NOT NULL,
    company_name VARCHAR(255),
    extraction_started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    extraction_completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    merkle_root VARCHAR(64),
    total_records INTEGER DEFAULT 0,
    extraction_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE forensic.records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    extraction_id UUID REFERENCES forensic.extractions(id),
    record_type VARCHAR(100) NOT NULL,
    record_id VARCHAR(100) NOT NULL,
    record_data JSONB NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE forensic.audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    user_id UUID,
    ip_address INET,
    user_agent TEXT,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE forensic.verifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    extraction_id UUID REFERENCES forensic.extractions(id),
    verification_type VARCHAR(50) NOT NULL,
    verified_at TIMESTAMP WITH TIME ZONE NOT NULL,
    verified_by VARCHAR(255),
    merkle_root_verified VARCHAR(64),
    records_verified INTEGER,
    discrepancies_found INTEGER DEFAULT 0,
    verification_report JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_records_extraction_id ON forensic.records(extraction_id);
CREATE INDEX idx_records_record_type ON forensic.records(record_type);
CREATE INDEX idx_records_sha256_hash ON forensic.records(sha256_hash);
CREATE INDEX idx_audit_logs_created_at ON forensic.audit_logs(created_at);
CREATE INDEX idx_audit_logs_entity ON forensic.audit_logs(entity_type, entity_id);

-- Row-level security for multi-tenant isolation
ALTER TABLE forensic.extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE forensic.records ENABLE ROW LEVEL SECURITY;
```

### 4.3 Store Database Credentials in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name forensicbridge/prod/database \
  --description "ForensicBridge Production Database Credentials" \
  --secret-string '{
    "host": "forensicbridge-prod.xxxxx.ca-central-1.rds.amazonaws.com",
    "port": 5432,
    "database": "forensicbridge",
    "username": "fbadmin",
    "password": "[SECURE_PASSWORD]"
  }' \
  --region ca-central-1
```

---

## 5. Backend Services Deployment

### 5.1 Build Docker Image

```bash
cd /home/user/QBMigration/QBMigrationService

# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

# Security: Run as non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set ownership
RUN chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Build image
docker build -t forensicbridge-api:latest .

# Tag for ECR
aws ecr get-login-password --region ca-central-1 | \
  docker login --username AWS --password-stdin [ACCOUNT_ID].dkr.ecr.ca-central-1.amazonaws.com

docker tag forensicbridge-api:latest \
  [ACCOUNT_ID].dkr.ecr.ca-central-1.amazonaws.com/forensicbridge-api:latest

docker push [ACCOUNT_ID].dkr.ecr.ca-central-1.amazonaws.com/forensicbridge-api:latest
```

### 5.2 Create ECS Cluster and Service

```bash
# Create ECS cluster
aws ecs create-cluster \
  --cluster-name forensicbridge-prod \
  --capacity-providers FARGATE FARGATE_SPOT \
  --default-capacity-provider-strategy \
    capacityProvider=FARGATE,weight=1,base=1 \
  --settings name=containerInsights,value=enabled

# Create task execution role
aws iam create-role \
  --role-name forensicbridge-ecs-execution-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

aws iam attach-role-policy \
  --role-name forensicbridge-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Create task definition
cat > task-definition.json << 'EOF'
{
  "family": "forensicbridge-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::[ACCOUNT_ID]:role/forensicbridge-ecs-execution-role",
  "taskRoleArn": "arn:aws:iam::[ACCOUNT_ID]:role/forensicbridge-ecs-task-role",
  "containerDefinitions": [{
    "name": "api",
    "image": "[ACCOUNT_ID].dkr.ecr.ca-central-1.amazonaws.com/forensicbridge-api:latest",
    "portMappings": [{
      "containerPort": 8000,
      "protocol": "tcp"
    }],
    "environment": [
      {"name": "ENVIRONMENT", "value": "production"},
      {"name": "AWS_REGION", "value": "ca-central-1"}
    ],
    "secrets": [{
      "name": "DATABASE_URL",
      "valueFrom": "arn:aws:secretsmanager:ca-central-1:[ACCOUNT_ID]:secret:forensicbridge/prod/database"
    }],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/forensicbridge-api",
        "awslogs-region": "ca-central-1",
        "awslogs-stream-prefix": "api"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
      "interval": 30,
      "timeout": 5,
      "retries": 3,
      "startPeriod": 60
    }
  }]
}
EOF

aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create ECS service
aws ecs create-service \
  --cluster forensicbridge-prod \
  --service-name forensicbridge-api \
  --task-definition forensicbridge-api \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[PRIVATE_SUBNET_1A,PRIVATE_SUBNET_1B],securityGroups=[$ECS_SG_ID],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:ca-central-1:[ACCOUNT_ID]:targetgroup/forensicbridge-tg/xxx,containerName=api,containerPort=8000" \
  --health-check-grace-period-seconds 120
```

### 5.3 Create Application Load Balancer

```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name forensicbridge-alb \
  --subnets [PUBLIC_SUBNET_1A] [PUBLIC_SUBNET_1B] \
  --security-groups $ALB_SG_ID \
  --scheme internet-facing \
  --type application \
  --ip-address-type ipv4

# Create target group
aws elbv2 create-target-group \
  --name forensicbridge-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3

# Create HTTPS listener (requires ACM certificate)
aws elbv2 create-listener \
  --load-balancer-arn [ALB_ARN] \
  --protocol HTTPS \
  --port 443 \
  --ssl-policy ELBSecurityPolicy-TLS13-1-2-2021-06 \
  --certificates CertificateArn=[ACM_CERT_ARN] \
  --default-actions Type=forward,TargetGroupArn=[TARGET_GROUP_ARN]
```

---

## 6. QBDesktopReader Setup

### 6.1 Build the Desktop Application

```bash
cd /home/user/QBMigration/QBDesktopReader

# Restore dependencies
dotnet restore

# Build release version
dotnet build --configuration Release

# Publish self-contained executable
dotnet publish -c Release -r win-x64 --self-contained true \
  -o ./publish/win-x64
```

### 6.2 Configure the Reader

Create configuration file `appsettings.json`:

```json
{
  "ForensicBridge": {
    "ApiEndpoint": "https://api.forensicbridge.io",
    "ApiKey": "${API_KEY}",
    "Region": "ca-central-1"
  },
  "QuickBooks": {
    "SdkVersion": "16.0",
    "ConnectionTimeout": 300,
    "RetryAttempts": 3
  },
  "Forensics": {
    "EnableMerkleTree": true,
    "HashAlgorithm": "SHA256",
    "ChunkSize": 10000,
    "EnableCompression": true
  },
  "Logging": {
    "Level": "Information",
    "FilePath": "%LOCALAPPDATA%/ForensicBridge/logs"
  }
}
```

### 6.3 Windows Installation

```powershell
# Create installation directory
$installPath = "C:\Program Files\ForensicBridge"
New-Item -ItemType Directory -Path $installPath -Force

# Copy files
Copy-Item -Path ".\publish\win-x64\*" -Destination $installPath -Recurse

# Register COM components for QuickBooks SDK
cd $installPath
regsvr32 /s QBXMLRP2.dll

# Create Start Menu shortcut
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:ProgramData\Microsoft\Windows\Start Menu\Programs\ForensicBridge Reader.lnk")
$Shortcut.TargetPath = "$installPath\QBDesktopReader.exe"
$Shortcut.Save()
```

---

## 7. Dashboard Frontend Deployment

### 7.1 Build React Application

```bash
cd /home/user/QBMigration/forensicbridge-dashboard

# Install dependencies
npm install

# Build for production
npm run build

# Output is in ./dist or ./build directory
```

### 7.2 Deploy to CloudFront + S3

```bash
# Create S3 bucket for static hosting
aws s3 mb s3://forensicbridge-dashboard-prod --region ca-central-1

# Upload build files
aws s3 sync ./dist s3://forensicbridge-dashboard-prod \
  --delete \
  --cache-control "public, max-age=31536000" \
  --exclude "index.html"

aws s3 cp ./dist/index.html s3://forensicbridge-dashboard-prod/index.html \
  --cache-control "no-cache, no-store, must-revalidate"

# Create CloudFront distribution
cat > cloudfront-config.json << 'EOF'
{
  "CallerReference": "forensicbridge-dashboard-$(date +%s)",
  "Origins": {
    "Quantity": 1,
    "Items": [{
      "Id": "S3-forensicbridge-dashboard",
      "DomainName": "forensicbridge-dashboard-prod.s3.ca-central-1.amazonaws.com",
      "S3OriginConfig": {
        "OriginAccessIdentity": ""
      }
    }]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "S3-forensicbridge-dashboard",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 2,
      "Items": ["GET", "HEAD"]
    },
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    "Compress": true
  },
  "DefaultRootObject": "index.html",
  "CustomErrorResponses": {
    "Quantity": 1,
    "Items": [{
      "ErrorCode": 404,
      "ResponsePagePath": "/index.html",
      "ResponseCode": "200",
      "ErrorCachingMinTTL": 300
    }]
  },
  "ViewerCertificate": {
    "ACMCertificateArn": "[ACM_CERT_ARN]",
    "SSLSupportMethod": "sni-only",
    "MinimumProtocolVersion": "TLSv1.2_2021"
  },
  "Enabled": true
}
EOF

aws cloudfront create-distribution --distribution-config file://cloudfront-config.json
```

---

## 8. Security Configuration

### 8.1 WAF Rules

```bash
# Create WAF WebACL
aws wafv2 create-web-acl \
  --name forensicbridge-waf \
  --scope REGIONAL \
  --default-action Allow={} \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=forensicbridge-waf \
  --rules '[
    {
      "Name": "AWSManagedRulesCommonRuleSet",
      "Priority": 1,
      "OverrideAction": {"None": {}},
      "Statement": {
        "ManagedRuleGroupStatement": {
          "VendorName": "AWS",
          "Name": "AWSManagedRulesCommonRuleSet"
        }
      },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "CommonRuleSet"
      }
    },
    {
      "Name": "AWSManagedRulesKnownBadInputsRuleSet",
      "Priority": 2,
      "OverrideAction": {"None": {}},
      "Statement": {
        "ManagedRuleGroupStatement": {
          "VendorName": "AWS",
          "Name": "AWSManagedRulesKnownBadInputsRuleSet"
        }
      },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "KnownBadInputs"
      }
    },
    {
      "Name": "AWSManagedRulesSQLiRuleSet",
      "Priority": 3,
      "OverrideAction": {"None": {}},
      "Statement": {
        "ManagedRuleGroupStatement": {
          "VendorName": "AWS",
          "Name": "AWSManagedRulesSQLiRuleSet"
        }
      },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "SQLiRuleSet"
      }
    },
    {
      "Name": "RateLimitRule",
      "Priority": 4,
      "Action": {"Block": {}},
      "Statement": {
        "RateBasedStatement": {
          "Limit": 2000,
          "AggregateKeyType": "IP"
        }
      },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "RateLimit"
      }
    }
  ]' \
  --region ca-central-1
```

### 8.2 Enable AWS Shield Advanced (Optional)

```bash
# Enable Shield Advanced for DDoS protection
aws shield create-subscription

# Associate with ALB
aws shield create-protection \
  --name forensicbridge-alb-protection \
  --resource-arn arn:aws:elasticloadbalancing:ca-central-1:[ACCOUNT_ID]:loadbalancer/app/forensicbridge-alb/xxx
```

### 8.3 KMS Key for Encryption

```bash
# Create customer-managed KMS key
aws kms create-key \
  --description "ForensicBridge encryption key" \
  --key-usage ENCRYPT_DECRYPT \
  --origin AWS_KMS \
  --tags TagKey=Project,TagValue=ForensicBridge

# Create alias
aws kms create-alias \
  --alias-name alias/forensicbridge \
  --target-key-id [KEY_ID]
```

---

## 9. Monitoring & Logging

### 9.1 CloudWatch Log Groups

```bash
# Create log groups with retention
aws logs create-log-group --log-group-name /ecs/forensicbridge-api
aws logs put-retention-policy --log-group-name /ecs/forensicbridge-api --retention-in-days 365

aws logs create-log-group --log-group-name /forensicbridge/audit
aws logs put-retention-policy --log-group-name /forensicbridge/audit --retention-in-days 2555  # 7 years for CRA

aws logs create-log-group --log-group-name /forensicbridge/security
aws logs put-retention-policy --log-group-name /forensicbridge/security --retention-in-days 365
```

### 9.2 CloudWatch Alarms

```bash
# High error rate alarm
aws cloudwatch put-metric-alarm \
  --alarm-name forensicbridge-high-error-rate \
  --alarm-description "High 5xx error rate on API" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:ca-central-1:[ACCOUNT_ID]:forensicbridge-alerts

# Database CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name forensicbridge-db-high-cpu \
  --alarm-description "High CPU on RDS instance" \
  --metric-name CPUUtilization \
  --namespace AWS/RDS \
  --dimensions Name=DBInstanceIdentifier,Value=forensicbridge-prod \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 3 \
  --alarm-actions arn:aws:sns:ca-central-1:[ACCOUNT_ID]:forensicbridge-alerts
```

### 9.3 CloudWatch Dashboard

```bash
cat > dashboard.json << 'EOF'
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "title": "API Request Count",
        "metrics": [
          ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", "app/forensicbridge-alb/xxx"]
        ],
        "period": 60,
        "stat": "Sum"
      }
    },
    {
      "type": "metric",
      "properties": {
        "title": "API Latency",
        "metrics": [
          ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", "app/forensicbridge-alb/xxx"]
        ],
        "period": 60,
        "stat": "p99"
      }
    },
    {
      "type": "metric",
      "properties": {
        "title": "Database Connections",
        "metrics": [
          ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", "forensicbridge-prod"]
        ],
        "period": 60,
        "stat": "Average"
      }
    },
    {
      "type": "metric",
      "properties": {
        "title": "ECS CPU/Memory",
        "metrics": [
          ["AWS/ECS", "CPUUtilization", "ClusterName", "forensicbridge-prod"],
          ["AWS/ECS", "MemoryUtilization", "ClusterName", "forensicbridge-prod"]
        ],
        "period": 60,
        "stat": "Average"
      }
    }
  ]
}
EOF

aws cloudwatch put-dashboard --dashboard-name ForensicBridge-Prod --dashboard-body file://dashboard.json
```

---

## 10. Verification & Testing

### 10.1 Health Check Verification

```bash
# Check API health
curl -s https://api.forensicbridge.io/health | jq .

# Expected response:
# {
#   "status": "healthy",
#   "version": "1.0.0",
#   "database": "connected",
#   "cache": "connected"
# }
```

### 10.2 Run Integration Tests

```bash
cd /home/user/QBMigration/QBMigrationService

# Activate virtual environment
python -m venv venv
source venv/bin/activate

# Install test dependencies
pip install -r requirements-dev.txt

# Run full test suite
pytest tests/ -v --cov=. --cov-report=html

# Run performance benchmarks
pytest tests/test_performance_benchmarks.py -v -s
```

### 10.3 Verify Forensic Integrity

```bash
# Test Merkle tree verification
python -c "
from verifier import MerkleTreeBuilder, verify_merkle_root

# Create test tree
builder = MerkleTreeBuilder()
builder.add_leaf_hash('hash1')
builder.add_leaf_hash('hash2')
builder.add_leaf_hash('hash3')
root = builder.build_tree()
print(f'Merkle Root: {root}')

# Verify a leaf
is_valid, proof = builder.get_proof_path(0)
print(f'Proof valid: {builder.verify_proof(\"hash1\", proof, root)}')
"
```

### 10.4 Load Testing

```bash
# Install k6 for load testing
brew install k6  # macOS
# or
sudo apt install k6  # Ubuntu

# Create load test script
cat > load-test.js << 'EOF'
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Ramp up
    { duration: '5m', target: 100 },  // Sustained load
    { duration: '1m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% under 500ms
    http_req_failed: ['rate<0.01'],    // Less than 1% errors
  },
};

export default function () {
  const res = http.get('https://api.forensicbridge.io/health');
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
  sleep(1);
}
EOF

# Run load test
k6 run load-test.js
```

---

## 11. Troubleshooting

### 11.1 Common Issues

#### Issue: QuickBooks SDK Connection Timeout

```
Error: COM Exception - QuickBooks is not responding
```

**Solution:**
1. Ensure QuickBooks Desktop is running
2. Check that the company file is open
3. Verify SDK permissions are granted
4. Restart QuickBooks and try again

#### Issue: Database Connection Failed

```
Error: Connection refused to PostgreSQL
```

**Solution:**
1. Check security group rules
2. Verify RDS instance is running: `aws rds describe-db-instances`
3. Check credentials in Secrets Manager
4. Verify network connectivity from ECS tasks

#### Issue: Merkle Root Mismatch

```
Error: Merkle root verification failed
```

**Solution:**
1. Check for data corruption during transfer
2. Re-extract from source with fresh hashes
3. Verify no records were modified post-extraction
4. Review audit logs for tampering attempts

### 11.2 Log Analysis

```bash
# View recent API logs
aws logs filter-log-events \
  --log-group-name /ecs/forensicbridge-api \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "ERROR"

# Search audit logs for specific extraction
aws logs filter-log-events \
  --log-group-name /forensicbridge/audit \
  --filter-pattern '{ $.extraction_id = "uuid-here" }'
```

### 11.3 Emergency Procedures

#### Database Failover
```bash
# Force RDS failover (if Multi-AZ)
aws rds reboot-db-instance \
  --db-instance-identifier forensicbridge-prod \
  --force-failover
```

#### Rollback ECS Deployment
```bash
# List recent task definitions
aws ecs list-task-definitions --family-prefix forensicbridge-api

# Update service to previous version
aws ecs update-service \
  --cluster forensicbridge-prod \
  --service forensicbridge-api \
  --task-definition forensicbridge-api:PREVIOUS_VERSION
```

---

## Appendix A: Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://...` |
| `AWS_REGION` | AWS region | `ca-central-1` |
| `S3_ARCHIVE_BUCKET` | Archive storage bucket | `forensicbridge-archives-prod` |
| `REDIS_URL` | Redis connection string | `redis://...` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `MERKLE_ENABLED` | Enable Merkle tree hashing | `true` |
| `API_KEY_SALT` | Salt for API key hashing | `[secure-random]` |

## Appendix B: Port Reference

| Service | Port | Protocol |
|---------|------|----------|
| API Gateway | 443 | HTTPS |
| API (internal) | 8000 | HTTP |
| PostgreSQL | 5432 | TCP |
| Redis | 6379 | TCP |
| QuickBooks SDK | 8471 | TCP |

## Appendix C: Compliance Checklist

- [x] Canadian data residency (ca-central-1)
- [x] Encryption at rest (AES-256)
- [x] Encryption in transit (TLS 1.3)
- [x] Audit logging (7-year retention)
- [x] Access controls (IAM + RBAC)
- [x] Backup procedures (35-day retention)
- [x] Incident response plan
- [x] Penetration testing schedule

---

**Document Version:** 1.0.0
**Last Updated:** 2026-01-25
**Author:** ForensicBridge Security Team

# ForensicBridge AWS Deployment Guide

## Prerequisites
- AWS CLI installed and configured
- AWS account with admin access
- Domain name (e.g., forensicbridge.io)

## Quick Start

### 1. Deploy Infrastructure
```powershell
# Set your database password (min 16 chars)
$DB_PASSWORD = "YourSecurePassword123!"

# Deploy the stack
aws cloudformation create-stack `
  --stack-name forensicbridge-prod `
  --template-body file://cloudformation.yaml `
  --parameters ParameterKey=DBPassword,ParameterValue=$DB_PASSWORD `
  --capabilities CAPABILITY_IAM `
  --region ca-central-1

# Wait for completion (~15 minutes)
aws cloudformation wait stack-create-complete --stack-name forensicbridge-prod
```

### 2. Get Outputs
```powershell
aws cloudformation describe-stacks --stack-name forensicbridge-prod --query "Stacks[0].Outputs"
```

### 3. Deploy Application Code
```bash
# SSH to EC2
ssh -i your-key.pem ubuntu@<EC2-IP>

# Clone your repo
cd /opt/forensicbridge
git clone https://github.com/yourusername/QBMigration.git .

# Install dependencies
pip3 install -r QBMigrationServer/requirements.txt
pip3 install -r QBMigrationService/requirements.txt

# Run migrations
python3 -m flask db upgrade

# Start services
sudo systemctl enable forensicbridge
sudo systemctl start forensicbridge
```

## Estimated Monthly Cost
| Service | Cost |
|---------|------|
| EC2 t3.small | $15 |
| RDS db.t3.micro | $15 |
| ElastiCache t3.micro | $12 |
| S3 (100GB) | $3 |
| ALB | $20 |
| Data Transfer | $10 |
| **Total** | **~$75** |

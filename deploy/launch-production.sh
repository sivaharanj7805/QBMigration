#!/bin/bash
# =============================================================================
# ForensicBridge Production Deployment Script
# =============================================================================
# Launches a complete production environment on AWS EC2.
#
# This script:
#   1. Validates prerequisites (AWS CLI, credentials, domain)
#   2. Creates AWS infrastructure (S3 bucket, security group, key pair)
#   3. Launches an EC2 instance with the full stack
#   4. Configures SSL via Let's Encrypt
#   5. Runs health checks
#
# Usage:
#   chmod +x deploy/launch-production.sh
#   ./deploy/launch-production.sh
#
# Prerequisites:
#   - AWS CLI v2 installed and configured (aws configure)
#   - A registered domain name (optional but recommended)
#   - QuickBooks Online developer credentials (optional for initial test)
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Defaults
AWS_REGION="${AWS_REGION:-ca-central-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
ENVIRONMENT="${ENVIRONMENT:-production}"
APP_NAME="forensicbridge"
STACK_NAME="${APP_NAME}-${ENVIRONMENT}"
KEY_NAME="${APP_NAME}-${ENVIRONMENT}-key"
S3_BUCKET="${APP_NAME}-${ENVIRONMENT}-data-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo 'unknown')"
REPO_URL="https://github.com/sivaharanj7805/QBMigration.git"
BRANCH="${DEPLOY_BRANCH:-main}"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# =============================================================================
# Helper Functions
# =============================================================================

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

prompt_value() {
    local prompt="$1"
    local default="${2:-}"
    local value
    if [ -n "$default" ]; then
        read -r -p "$(echo -e "${BLUE}?${NC}") $prompt [$default]: " value
        echo "${value:-$default}"
    else
        read -r -p "$(echo -e "${BLUE}?${NC}") $prompt: " value
        echo "$value"
    fi
}

prompt_secret() {
    local prompt="$1"
    local value
    read -r -s -p "$(echo -e "${BLUE}?${NC}") $prompt: " value
    echo ""
    echo "$value"
}

generate_secret() {
    openssl rand -base64 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
}

generate_fernet_key() {
    python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || \
    openssl rand -base64 32
}

# =============================================================================
# Step 0: Banner
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         ForensicBridge Production Deployment            ║${NC}"
echo -e "${GREEN}║     QuickBooks Desktop → QuickBooks Online Migration    ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# Step 1: Preflight Checks
# =============================================================================
log_info "Running preflight checks..."

# Check AWS CLI
if ! command -v aws &>/dev/null; then
    log_error "AWS CLI not found. Install it: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi
log_ok "AWS CLI found: $(aws --version 2>&1 | head -1)"

# Check AWS credentials
if ! aws sts get-caller-identity &>/dev/null; then
    log_error "AWS credentials not configured. Run: aws configure"
    exit 1
fi
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_USER=$(aws sts get-caller-identity --query Arn --output text)
log_ok "AWS Account: $AWS_ACCOUNT ($AWS_USER)"

# Check region
AWS_REGION=$(prompt_value "AWS Region" "$AWS_REGION")
export AWS_DEFAULT_REGION="$AWS_REGION"
log_ok "Region: $AWS_REGION"

# =============================================================================
# Step 2: Gather Configuration
# =============================================================================
echo ""
log_info "Gathering deployment configuration..."

DOMAIN_NAME=$(prompt_value "Domain name (leave empty for IP-only access)" "")
ALERT_EMAIL=$(prompt_value "Alert email for monitoring notifications" "")
SSH_CIDR=$(prompt_value "Your IP for SSH access (CIDR format)" "$(curl -s https://checkip.amazonaws.com 2>/dev/null)/32")

echo ""
log_info "Optional: QuickBooks Online OAuth credentials"
log_info "(Skip these for now — you can add them later in /etc/qbmigration/environment)"
QBO_CLIENT_ID=$(prompt_value "QBO Client ID (press Enter to skip)" "")
QBO_CLIENT_SECRET=""
if [ -n "$QBO_CLIENT_ID" ]; then
    QBO_CLIENT_SECRET=$(prompt_secret "QBO Client Secret")
fi

# Generate secrets
log_info "Generating security keys..."
SECRET_KEY=$(generate_secret)
BACKUP_KEY=$(generate_fernet_key)
DB_PASSWORD=$(generate_secret | tr -dc 'a-zA-Z0-9' | head -c 24)
REDIS_PASSWORD=$(generate_secret | tr -dc 'a-zA-Z0-9' | head -c 24)
MFA_KEY=$(generate_fernet_key)

log_ok "All security keys generated"

# =============================================================================
# Step 3: Create AWS Resources
# =============================================================================
echo ""
log_info "Creating AWS resources..."

# S3 Bucket
S3_BUCKET="${APP_NAME}-${ENVIRONMENT}-data-${AWS_ACCOUNT}"
if aws s3 ls "s3://${S3_BUCKET}" 2>/dev/null; then
    log_ok "S3 bucket already exists: $S3_BUCKET"
else
    log_info "Creating S3 bucket: $S3_BUCKET"
    if [ "$AWS_REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$S3_BUCKET"
    else
        aws s3api create-bucket --bucket "$S3_BUCKET" \
            --create-bucket-configuration LocationConstraint="$AWS_REGION"
    fi
    # Enable encryption
    aws s3api put-bucket-encryption --bucket "$S3_BUCKET" \
        --server-side-encryption-configuration '{
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        }'
    # Block public access
    aws s3api put-public-access-block --bucket "$S3_BUCKET" \
        --public-access-block-configuration '{
            "BlockPublicAcls": true,
            "IgnorePublicAcls": true,
            "BlockPublicPolicy": true,
            "RestrictPublicBuckets": true
        }'
    # Enable versioning
    aws s3api put-bucket-versioning --bucket "$S3_BUCKET" \
        --versioning-configuration Status=Enabled
    log_ok "S3 bucket created with encryption, versioning, and public access blocked"
fi

# EC2 Key Pair
KEY_FILE="$PROJECT_DIR/deploy/${KEY_NAME}.pem"
if aws ec2 describe-key-pairs --key-names "$KEY_NAME" &>/dev/null; then
    log_ok "Key pair already exists: $KEY_NAME"
    if [ ! -f "$KEY_FILE" ]; then
        log_warn "Key file not found locally at $KEY_FILE — you'll need the existing PEM file to SSH"
    fi
else
    log_info "Creating EC2 key pair: $KEY_NAME"
    aws ec2 create-key-pair --key-name "$KEY_NAME" --query 'KeyMaterial' --output text > "$KEY_FILE"
    chmod 400 "$KEY_FILE"
    log_ok "Key pair created: $KEY_FILE"
fi

# Security Group
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text)
SG_NAME="${APP_NAME}-${ENVIRONMENT}-sg"
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)

if [ "$SG_ID" != "None" ] && [ -n "$SG_ID" ]; then
    log_ok "Security group already exists: $SG_ID"
else
    log_info "Creating security group: $SG_NAME"
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SG_NAME" \
        --description "ForensicBridge ${ENVIRONMENT} - HTTP/HTTPS/SSH" \
        --vpc-id "$VPC_ID" \
        --query 'GroupId' --output text)

    # HTTP
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
        --protocol tcp --port 80 --cidr 0.0.0.0/0
    # HTTPS
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
        --protocol tcp --port 443 --cidr 0.0.0.0/0
    # SSH (restricted to user's IP)
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
        --protocol tcp --port 22 --cidr "$SSH_CIDR"

    log_ok "Security group created: $SG_ID (HTTP, HTTPS, SSH from $SSH_CIDR)"
fi

# Find latest Ubuntu 22.04 AMI
log_info "Finding latest Ubuntu 22.04 AMI..."
AMI_ID=$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
              "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text)
log_ok "AMI: $AMI_ID (Ubuntu 22.04 LTS)"

# =============================================================================
# Step 4: Create User Data Script
# =============================================================================
log_info "Generating EC2 user data script..."

# Build the environment file content
ENV_CONTENT="FLASK_APP=app.py
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=${SECRET_KEY}
BACKUP_ENCRYPTION_KEY=${BACKUP_KEY}
MFA_ENCRYPTION_KEY=${MFA_KEY}
DATABASE_URL=postgresql://qbmigration:${DB_PASSWORD}@localhost:5432/qbmigration
POSTGRES_USER=qbmigration
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=qbmigration
REDIS_URL=redis://:${REDIS_PASSWORD}@localhost:6379/0
REDIS_PASSWORD=${REDIS_PASSWORD}
AWS_REGION=${AWS_REGION}
AWS_S3_BUCKET=${S3_BUCKET}
QBO_CLIENT_ID=${QBO_CLIENT_ID}
QBO_CLIENT_SECRET=${QBO_CLIENT_SECRET}
QBO_ENVIRONMENT=production
ALLOWED_ORIGINS=https://${DOMAIN_NAME:-localhost},http://${DOMAIN_NAME:-localhost}
RATELIMIT_ENABLED=true
RATELIMIT_STORAGE_URL=redis://:${REDIS_PASSWORD}@localhost:6379/1
SENTRY_DSN=
MAIL_SERVER=
MAIL_PORT=587
MAIL_USERNAME=
MAIL_PASSWORD=
NEXT_PUBLIC_API_URL=${DOMAIN_NAME:+https://${DOMAIN_NAME}}${DOMAIN_NAME:-http://localhost}
NEXT_PUBLIC_APP_URL=${DOMAIN_NAME:+https://${DOMAIN_NAME}}${DOMAIN_NAME:-http://localhost}
FRONTEND_URL=${DOMAIN_NAME:+https://${DOMAIN_NAME}}${DOMAIN_NAME:-http://localhost}
LOG_LEVEL=INFO
ALERT_EMAIL=${ALERT_EMAIL}"

# Build user data script (combines setup + auto-configure)
USER_DATA=$(cat << 'USERDATA_SCRIPT'
#!/bin/bash
set -e
exec > >(tee /var/log/forensicbridge-deploy.log) 2>&1

echo "============================================"
echo "ForensicBridge Production Deployment"
echo "Started: $(date)"
echo "============================================"

# System setup
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# Install dependencies
apt-get install -y \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    postgresql postgresql-client \
    redis-server \
    nginx git curl wget unzip build-essential \
    libpq-dev libssl-dev libffi-dev \
    certbot python3-certbot-nginx \
    jq fail2ban unattended-upgrades

# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Create app user
useradd -m -s /bin/bash qbmigration || true

# Write environment file
mkdir -p /etc/qbmigration
cat > /etc/qbmigration/environment << 'ENVEOF'
__ENV_PLACEHOLDER__
ENVEOF
chmod 600 /etc/qbmigration/environment
chown root:qbmigration /etc/qbmigration/environment

# Source environment
set -a
source /etc/qbmigration/environment
set +a

# ---- PostgreSQL Setup ----
echo "Setting up PostgreSQL..."
sudo -u postgres psql -c "CREATE USER qbmigration WITH PASSWORD '${POSTGRES_PASSWORD}';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE qbmigration OWNER qbmigration;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE qbmigration TO qbmigration;" 2>/dev/null || true

# ---- Redis Setup ----
echo "Setting up Redis..."
cat > /etc/redis/redis.conf.d/forensicbridge.conf 2>/dev/null << REDISCONF || true
maxmemory 512mb
maxmemory-policy allkeys-lru
appendonly yes
requirepass ${REDIS_PASSWORD}
REDISCONF
# If conf.d doesn't exist, modify main config
if [ ! -d /etc/redis/redis.conf.d ]; then
    sed -i "s/^# requirepass .*/requirepass ${REDIS_PASSWORD}/" /etc/redis/redis.conf
    echo "appendonly yes" >> /etc/redis/redis.conf
    echo "maxmemory 512mb" >> /etc/redis/redis.conf
    echo "maxmemory-policy allkeys-lru" >> /etc/redis/redis.conf
fi
systemctl restart redis-server

# ---- Clone Application ----
echo "Cloning application..."
APP_DIR="/opt/forensicbridge"
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull origin __BRANCH__
else
    git clone --branch __BRANCH__ __REPO_URL__ "$APP_DIR"
fi
chown -R qbmigration:qbmigration "$APP_DIR"

# ---- Python Setup ----
echo "Setting up Python environment..."
cd "$APP_DIR"
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r QBMigrationServer/requirements.txt || true
pip install gunicorn gevent

# ---- Database Migrations ----
echo "Running database migrations..."
cd "$APP_DIR/QBMigrationServer"
FLASK_APP=app.py python3 -c "
from app import create_app
from models.database import db
app = create_app()
with app.app_context():
    db.create_all()
    print('Database tables created successfully')
" || echo "Warning: DB migration had issues, will retry on first request"

# ---- Frontend Build ----
echo "Building Next.js frontend..."
cd "$APP_DIR/forensicbridge-dashboard"
cat > .env.local << FRONTENV
NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-http://localhost:5000}
NEXT_PUBLIC_APP_URL=${NEXT_PUBLIC_APP_URL:-http://localhost:3000}
FRONTENV
npm ci --production=false
npm run build

chown -R qbmigration:qbmigration "$APP_DIR"

# ---- Systemd Services ----
echo "Creating systemd services..."
mkdir -p /var/log/forensicbridge /var/lib/forensicbridge
chown -R qbmigration:qbmigration /var/log/forensicbridge /var/lib/forensicbridge

# Flask API
cat > /etc/systemd/system/forensicbridge-api.service << SVCEOF
[Unit]
Description=ForensicBridge Flask API
After=network.target redis-server.service postgresql.service
Wants=redis-server.service postgresql.service

[Service]
User=qbmigration
Group=qbmigration
WorkingDirectory=$APP_DIR/QBMigrationServer
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=/etc/qbmigration/environment
ExecStart=$APP_DIR/venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --workers 4 \
    --worker-class gthread \
    --threads 2 \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile /var/log/forensicbridge/gunicorn-access.log \
    --error-logfile /var/log/forensicbridge/gunicorn-error.log \
    "app:create_app()"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

# Celery Worker
cat > /etc/systemd/system/forensicbridge-celery.service << SVCEOF
[Unit]
Description=ForensicBridge Celery Worker
After=network.target redis-server.service forensicbridge-api.service

[Service]
User=qbmigration
Group=qbmigration
WorkingDirectory=$APP_DIR/QBMigrationServer
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=/etc/qbmigration/environment
ExecStart=$APP_DIR/venv/bin/celery -A celery_worker worker \
    --loglevel=info --concurrency=4 \
    --logfile=/var/log/forensicbridge/celery-worker.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

# Celery Beat
cat > /etc/systemd/system/forensicbridge-beat.service << SVCEOF
[Unit]
Description=ForensicBridge Celery Beat
After=network.target redis-server.service forensicbridge-api.service

[Service]
User=qbmigration
Group=qbmigration
WorkingDirectory=$APP_DIR/QBMigrationServer
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=/etc/qbmigration/environment
ExecStart=$APP_DIR/venv/bin/celery -A celery_worker beat \
    --loglevel=info \
    --logfile=/var/log/forensicbridge/celery-beat.log \
    --schedule=/var/lib/forensicbridge/celerybeat-schedule
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

# Next.js Frontend
cat > /etc/systemd/system/forensicbridge-frontend.service << SVCEOF
[Unit]
Description=ForensicBridge Next.js Frontend
After=network.target forensicbridge-api.service

[Service]
User=qbmigration
Group=qbmigration
WorkingDirectory=$APP_DIR/forensicbridge-dashboard
Environment="NODE_ENV=production"
EnvironmentFile=/etc/qbmigration/environment
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

# ---- Nginx ----
echo "Configuring Nginx..."
cat > /etc/nginx/sites-available/forensicbridge << 'NGINXEOF'
limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
limit_req_zone $binary_remote_addr zone=upload:10m rate=10r/m;

upstream flask_api {
    server 127.0.0.1:5000 fail_timeout=0;
    keepalive 32;
}

upstream nextjs {
    server 127.0.0.1:3000 fail_timeout=0;
    keepalive 32;
}

server {
    listen 80;
    server_name _;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml;

    client_max_body_size 50M;

    location /api/health {
        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        access_log off;
    }

    location /api/auth {
        limit_req zone=auth burst=5 nodelay;
        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/upload {
        limit_req zone=upload burst=3 nodelay;
        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 300s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
        proxy_buffering off;
        proxy_request_buffering off;
    }

    location /api {
        limit_req zone=api burst=50 nodelay;
        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /_next/static {
        proxy_pass http://nextjs;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://nextjs;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINXEOF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/forensicbridge /etc/nginx/sites-enabled/
nginx -t

# ---- Start Everything ----
echo "Starting all services..."
systemctl daemon-reload
systemctl enable --now nginx
systemctl enable --now forensicbridge-api
systemctl enable --now forensicbridge-celery
systemctl enable --now forensicbridge-beat
systemctl enable --now forensicbridge-frontend

# Wait for services to start
sleep 10

# Health check
echo "Running health check..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:5000/api/health > /dev/null 2>&1; then
        echo "API is healthy!"
        break
    fi
    echo "Waiting for API to start... ($i/30)"
    sleep 5
done

# ---- Configure fail2ban ----
cat > /etc/fail2ban/jail.local << 'F2BEOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
maxretry = 3
bantime = 7200

[nginx-http-auth]
enabled = true
port    = http,https
logpath = /var/log/nginx/error.log
F2BEOF
systemctl enable --now fail2ban

# Enable auto security updates
dpkg-reconfigure -plow unattended-upgrades || true

echo ""
echo "============================================"
echo "ForensicBridge deployment complete!"
echo "============================================"
echo "API Health: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'localhost')/api/health"
echo "Dashboard:  http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'localhost')/"
echo "============================================"
USERDATA_SCRIPT
)

# Replace placeholders
USER_DATA="${USER_DATA//__ENV_PLACEHOLDER__/$ENV_CONTENT}"
USER_DATA="${USER_DATA//__BRANCH__/$BRANCH}"
USER_DATA="${USER_DATA//__REPO_URL__/$REPO_URL}"

# =============================================================================
# Step 5: Launch EC2 Instance
# =============================================================================
echo ""
log_info "Launching EC2 instance..."
echo ""
echo "  Instance type: $INSTANCE_TYPE"
echo "  AMI:           $AMI_ID"
echo "  Region:        $AWS_REGION"
echo "  Key pair:      $KEY_NAME"
echo "  Security group: $SG_ID"
echo "  S3 bucket:     $S3_BUCKET"
echo ""

read -r -p "$(echo -e "${YELLOW}Launch EC2 instance now? (y/N): ${NC}")" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    log_warn "Deployment cancelled."
    # Save config for later
    echo "$USER_DATA" > "$PROJECT_DIR/deploy/user-data-generated.sh"
    log_info "User data script saved to: deploy/user-data-generated.sh"
    log_info "You can launch manually with: aws ec2 run-instances ..."
    exit 0
fi

# Encode user data
USER_DATA_B64=$(echo "$USER_DATA" | base64 -w0)

# Launch instance
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --block-device-mappings '[{
        "DeviceName": "/dev/sda1",
        "Ebs": {
            "VolumeSize": 50,
            "VolumeType": "gp3",
            "Encrypted": true,
            "DeleteOnTermination": true
        }
    }]' \
    --user-data "$USER_DATA_B64" \
    --tag-specifications "ResourceType=instance,Tags=[
        {Key=Name,Value=${APP_NAME}-${ENVIRONMENT}},
        {Key=Environment,Value=${ENVIRONMENT}},
        {Key=Application,Value=forensicbridge},
        {Key=ManagedBy,Value=launch-production-script}
    ]" \
    --query 'Instances[0].InstanceId' --output text)

log_ok "Instance launched: $INSTANCE_ID"

# =============================================================================
# Step 6: Wait for Instance
# =============================================================================
log_info "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

log_ok "Instance is running at: $PUBLIC_IP"

# =============================================================================
# Step 7: Wait for Deployment to Complete
# =============================================================================
echo ""
log_info "Waiting for application deployment (this takes 5-10 minutes)..."
log_info "You can monitor progress with: ssh -i $KEY_FILE ubuntu@$PUBLIC_IP 'tail -f /var/log/forensicbridge-deploy.log'"
echo ""

# Poll health endpoint
HEALTHY=false
for i in $(seq 1 60); do
    if curl -sf "http://$PUBLIC_IP/api/health" > /dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    echo -ne "\r  Waiting... ($i/60) - $(( i * 10 ))s elapsed"
    sleep 10
done
echo ""

if [ "$HEALTHY" = true ]; then
    HEALTH_RESPONSE=$(curl -sf "http://$PUBLIC_IP/api/health" 2>/dev/null || echo '{}')
    log_ok "Application is healthy!"
    echo "  Health: $HEALTH_RESPONSE"
else
    log_warn "Health check timed out. Deployment may still be in progress."
    log_info "Check logs: ssh -i $KEY_FILE ubuntu@$PUBLIC_IP 'tail -100 /var/log/forensicbridge-deploy.log'"
fi

# =============================================================================
# Step 8: SSL Setup (if domain provided)
# =============================================================================
if [ -n "$DOMAIN_NAME" ]; then
    echo ""
    log_info "To enable HTTPS with Let's Encrypt:"
    echo ""
    echo "  1. Point your domain DNS to: $PUBLIC_IP"
    echo "     (Create an A record: $DOMAIN_NAME → $PUBLIC_IP)"
    echo ""
    echo "  2. Once DNS propagates, SSH in and run:"
    echo "     ssh -i $KEY_FILE ubuntu@$PUBLIC_IP"
    echo "     sudo certbot --nginx -d $DOMAIN_NAME --non-interactive --agree-tos -m $ALERT_EMAIL"
    echo ""
fi

# =============================================================================
# Step 9: Summary
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Deployment Complete!                        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Instance ID:  $INSTANCE_ID"
echo "  Public IP:    $PUBLIC_IP"
echo "  Dashboard:    http://$PUBLIC_IP/"
echo "  API Health:   http://$PUBLIC_IP/api/health"
echo "  SSH Access:   ssh -i $KEY_FILE ubuntu@$PUBLIC_IP"
echo ""
echo "  S3 Bucket:    $S3_BUCKET"
echo "  Key Pair:     $KEY_FILE"
echo ""
if [ -n "$DOMAIN_NAME" ]; then
    echo "  Domain:       $DOMAIN_NAME (configure DNS A record → $PUBLIC_IP)"
    echo "  HTTPS:        Run certbot after DNS propagation (see above)"
    echo ""
fi
echo "  Environment:  /etc/qbmigration/environment (on EC2)"
echo "  Logs:         ssh -i $KEY_FILE ubuntu@$PUBLIC_IP 'journalctl -u forensicbridge-api -f'"
echo ""
echo "  Estimated monthly cost: ~\$35-50/month (t3.medium)"
echo ""
echo -e "${YELLOW}  IMPORTANT: Save your key file: $KEY_FILE${NC}"
echo -e "${YELLOW}  IMPORTANT: Add QBO OAuth credentials to /etc/qbmigration/environment${NC}"
echo ""

# Save deployment info
cat > "$PROJECT_DIR/deploy/.last-deploy" << DEPLOYINFO
INSTANCE_ID=$INSTANCE_ID
PUBLIC_IP=$PUBLIC_IP
KEY_FILE=$KEY_FILE
S3_BUCKET=$S3_BUCKET
SG_ID=$SG_ID
AWS_REGION=$AWS_REGION
DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DEPLOYINFO

log_ok "Deployment info saved to: deploy/.last-deploy"

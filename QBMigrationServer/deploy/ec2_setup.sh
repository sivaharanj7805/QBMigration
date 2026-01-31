#!/bin/bash
# ============================================================================
# QB Migration Server - EC2 Deployment Script
# ============================================================================
# This script sets up the QB Migration Server on an Amazon EC2 instance.
#
# Prerequisites:
#   - Amazon Linux 2 or Ubuntu 22.04 LTS
#   - IAM role with S3, Secrets Manager, and EC2 permissions
#   - RDS PostgreSQL database
#   - Application Load Balancer (optional but recommended)
#
# Usage:
#   1. Launch EC2 instance with IAM role
#   2. SSH into instance
#   3. Run: curl -sSL <this-script-url> | bash
#   Or clone repo and run: ./deploy/ec2_setup.sh
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}QB MIGRATION SERVER - EC2 DEPLOYMENT${NC}"
echo -e "${GREEN}============================================================================${NC}"

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo -e "${RED}Cannot detect OS. Please use Amazon Linux 2 or Ubuntu 22.04${NC}"
    exit 1
fi

echo -e "${YELLOW}Detected OS: $OS${NC}"

# ============================================================================
# STEP 1: Install System Dependencies
# ============================================================================
echo -e "\n${GREEN}[1/7] Installing system dependencies...${NC}"

if [ "$OS" = "amzn" ]; then
    # Amazon Linux 2
    sudo yum update -y
    sudo yum install -y python3.9 python3.9-pip python3.9-devel gcc postgresql-devel git
    sudo alternatives --set python3 /usr/bin/python3.9
elif [ "$OS" = "ubuntu" ]; then
    # Ubuntu
    sudo apt-get update
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip gcc libpq-dev git
fi

# ============================================================================
# STEP 2: Create Application User and Directory
# ============================================================================
echo -e "\n${GREEN}[2/7] Creating application directory...${NC}"

APP_DIR="/opt/qbmigration"
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# ============================================================================
# STEP 3: Clone or Copy Application
# ============================================================================
echo -e "\n${GREEN}[3/7] Setting up application...${NC}"

if [ -d ".git" ]; then
    # We're in the repo already
    cp -r . $APP_DIR/
else
    echo -e "${YELLOW}Please copy the application to $APP_DIR${NC}"
    echo "Example: scp -r ./QBMigrationServer ec2-user@your-ec2:$APP_DIR"
    exit 1
fi

cd $APP_DIR

# ============================================================================
# STEP 4: Create Virtual Environment
# ============================================================================
echo -e "\n${GREEN}[4/7] Creating Python virtual environment...${NC}"

python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip wheel setuptools

# Install dependencies
pip install -r requirements.txt

# ============================================================================
# STEP 5: Configure Environment
# ============================================================================
echo -e "\n${GREEN}[5/7] Configuring environment...${NC}"

if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}IMPORTANT: Edit .env file with your production values!${NC}"
    echo -e "${YELLOW}Required settings:${NC}"
    echo "  - SECRET_KEY (generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))')"
    echo "  - DATABASE_URL (your RDS PostgreSQL URL)"
    echo "  - AWS_S3_BUCKET (your S3 bucket name)"
    echo "  - AWS_EC2_AMI_ID (your region's AMI ID)"
    echo "  - WEBHOOK_SECRET (generate unique secret)"
    echo "  - BACKUP_ENCRYPTION_KEY (generate Fernet key)"
    echo ""
    read -p "Press Enter after editing .env file..."
fi

# ============================================================================
# STEP 6: Initialize Database
# ============================================================================
echo -e "\n${GREEN}[6/7] Initializing database...${NC}"

export FLASK_ENV=production
source .env 2>/dev/null || true

# Run migrations
flask db upgrade || echo -e "${YELLOW}Migration may have failed - check DATABASE_URL${NC}"

# ============================================================================
# STEP 7: Create Systemd Service
# ============================================================================
echo -e "\n${GREEN}[7/7] Creating systemd service...${NC}"

sudo tee /etc/systemd/system/qbmigration.service > /dev/null <<EOF
[Unit]
Description=QB Migration Server
After=network.target

[Service]
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn wsgi:application -c gunicorn.conf.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable qbmigration

echo -e "\n${GREEN}============================================================================${NC}"
echo -e "${GREEN}DEPLOYMENT COMPLETE!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env file: nano $APP_DIR/.env"
echo "  2. Start service: sudo systemctl start qbmigration"
echo "  3. Check status: sudo systemctl status qbmigration"
echo "  4. View logs: sudo journalctl -u qbmigration -f"
echo ""
echo "Health check endpoint: http://localhost:5000/api/health"
echo ""
echo -e "${YELLOW}For production, configure an Application Load Balancer with:${NC}"
echo "  - Target group pointing to port 5000"
echo "  - Health check path: /api/health"
echo "  - HTTPS listener with ACM certificate"
echo ""

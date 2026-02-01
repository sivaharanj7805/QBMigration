#!/bin/bash
# =============================================================================
# EC2 User Data Script for QBMigration Server
# =============================================================================
# This script bootstraps an EC2 instance with all required services:
# - Flask API (Gunicorn)
# - Celery Worker & Beat
# - Next.js Frontend
# - Nginx Reverse Proxy
# - PostgreSQL (or RDS connection)
# - Redis
#
# Usage: Paste this into EC2 User Data or run on a fresh Ubuntu 22.04 instance
# =============================================================================

set -e
exec > >(tee /var/log/qbmigration-setup.log) 2>&1

echo "=========================================="
echo "QBMigration EC2 Setup - $(date)"
echo "=========================================="

# Configuration
APP_USER="qbmigration"
APP_DIR="/opt/qbmigration"
REPO_URL="https://github.com/sivaharanj7805/QBMigration.git"
BRANCH="main"

# =============================================================================
# 1. System Updates and Dependencies
# =============================================================================
echo "[1/10] Installing system dependencies..."

apt-get update -y
apt-get upgrade -y

# Install required packages
apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    postgresql-client \
    redis-server \
    nginx \
    git \
    curl \
    wget \
    unzip \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    supervisor \
    certbot \
    python3-certbot-nginx \
    jq \
    awscli

# Install Node.js 20.x for Next.js frontend
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

echo "Node.js version: $(node --version)"
echo "npm version: $(npm --version)"
echo "Python version: $(python3.11 --version)"

# =============================================================================
# 2. Create Application User
# =============================================================================
echo "[2/10] Creating application user..."

if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
    echo "Created user: $APP_USER"
else
    echo "User $APP_USER already exists"
fi

# =============================================================================
# 3. Clone Application Repository
# =============================================================================
echo "[3/10] Cloning application repository..."

if [ -d "$APP_DIR" ]; then
    echo "Updating existing repository..."
    cd "$APP_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# =============================================================================
# 4. Setup Python Virtual Environment
# =============================================================================
echo "[4/10] Setting up Python virtual environment..."

cd "$APP_DIR"
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip wheel setuptools

# Install Python dependencies
pip install -r requirements.txt
pip install -r QBMigrationServer/requirements.txt 2>/dev/null || true
pip install gunicorn gevent

# =============================================================================
# 5. Setup Next.js Frontend
# =============================================================================
echo "[5/10] Building Next.js frontend..."

cd "$APP_DIR/forensicbridge-dashboard"
npm ci --production=false
npm run build

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# =============================================================================
# 6. Configure Redis
# =============================================================================
echo "[6/10] Configuring Redis..."

# Update Redis configuration for production
cat > /etc/redis/redis.conf.d/qbmigration.conf << 'EOF'
# QBMigration Redis Configuration
maxmemory 512mb
maxmemory-policy allkeys-lru
appendonly yes
# Require password (set via environment variable during service start)
# requirepass will be set dynamically
EOF

systemctl enable redis-server
systemctl restart redis-server

# =============================================================================
# 7. Create Systemd Services
# =============================================================================
echo "[7/10] Creating systemd services..."

# Flask API Service (Gunicorn)
cat > /etc/systemd/system/qbmigration-api.service << EOF
[Unit]
Description=QBMigration Flask API (Gunicorn)
After=network.target redis-server.service
Wants=redis-server.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR/QBMigrationServer
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=/etc/qbmigration/environment
ExecStart=$APP_DIR/venv/bin/gunicorn \
    --config $APP_DIR/QBMigrationServer/gunicorn.conf.py \
    --bind 127.0.0.1:5000 \
    --workers 4 \
    --worker-class gevent \
    --timeout 120 \
    --keep-alive 5 \
    --access-logfile /var/log/qbmigration/gunicorn-access.log \
    --error-logfile /var/log/qbmigration/gunicorn-error.log \
    app:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Celery Worker Service
cat > /etc/systemd/system/qbmigration-celery-worker.service << EOF
[Unit]
Description=QBMigration Celery Worker
After=network.target redis-server.service qbmigration-api.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR/QBMigrationServer
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=/etc/qbmigration/environment
ExecStart=$APP_DIR/venv/bin/celery -A celery_worker worker \
    --loglevel=info \
    --concurrency=4 \
    --logfile=/var/log/qbmigration/celery-worker.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Celery Beat Service
cat > /etc/systemd/system/qbmigration-celery-beat.service << EOF
[Unit]
Description=QBMigration Celery Beat Scheduler
After=network.target redis-server.service qbmigration-api.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR/QBMigrationServer
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=/etc/qbmigration/environment
ExecStart=$APP_DIR/venv/bin/celery -A celery_worker beat \
    --loglevel=info \
    --logfile=/var/log/qbmigration/celery-beat.log \
    --schedule=/var/lib/qbmigration/celerybeat-schedule
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Next.js Frontend Service
cat > /etc/systemd/system/qbmigration-frontend.service << EOF
[Unit]
Description=QBMigration Next.js Frontend
After=network.target qbmigration-api.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR/forensicbridge-dashboard
Environment="PATH=/usr/bin"
Environment="NODE_ENV=production"
EnvironmentFile=/etc/qbmigration/environment
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create required directories
mkdir -p /var/log/qbmigration
mkdir -p /var/lib/qbmigration
mkdir -p /etc/qbmigration
chown -R "$APP_USER:$APP_USER" /var/log/qbmigration
chown -R "$APP_USER:$APP_USER" /var/lib/qbmigration

# =============================================================================
# 8. Configure Nginx
# =============================================================================
echo "[8/10] Configuring Nginx..."

cat > /etc/nginx/sites-available/qbmigration << 'NGINX_EOF'
# QBMigration Nginx Configuration

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
limit_req_zone $binary_remote_addr zone=upload:10m rate=10r/m;

# Upstream servers
upstream flask_api {
    server 127.0.0.1:5000 fail_timeout=0;
    keepalive 32;
}

upstream nextjs_frontend {
    server 127.0.0.1:3000 fail_timeout=0;
    keepalive 32;
}

server {
    listen 80;
    server_name _;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml;

    # Client body size (for file uploads)
    client_max_body_size 50M;

    # Health check endpoint (no auth, no rate limit)
    location /health {
        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        access_log off;
    }

    location /api/health {
        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        access_log off;
    }

    # Authentication endpoints (strict rate limiting)
    location /api/auth {
        limit_req zone=auth burst=5 nodelay;

        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Upload endpoint (rate limited, larger timeout)
    location /api/upload {
        limit_req zone=upload burst=3 nodelay;

        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Larger timeouts for file uploads
        proxy_connect_timeout 300s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;

        # Disable buffering for uploads
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # All other API endpoints
    location /api {
        limit_req zone=api burst=50 nodelay;

        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # Legal pages served by Flask
    location /legal {
        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # QuickBooks OAuth callback
    location /api/qbo/callback {
        proxy_pass http://flask_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Next.js frontend (all other routes)
    location / {
        proxy_pass http://nextjs_frontend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support for HMR (dev) and real-time updates
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Next.js static files
    location /_next/static {
        proxy_pass http://nextjs_frontend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;

        # Cache static assets
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
NGINX_EOF

# Enable the site
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/qbmigration /etc/nginx/sites-enabled/

# Test nginx configuration
nginx -t

# =============================================================================
# 9. Create Environment File Template
# =============================================================================
echo "[9/10] Creating environment file template..."

if [ ! -f /etc/qbmigration/environment ]; then
    cat > /etc/qbmigration/environment << 'ENV_EOF'
# =============================================================================
# QBMigration Environment Configuration
# =============================================================================
# IMPORTANT: Update these values before starting services!
# Generate secrets with: openssl rand -base64 32
# Generate Fernet key: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
# =============================================================================

# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
FLASK_DEBUG=0

# Security Keys (REQUIRED - generate unique values!)
SECRET_KEY=CHANGE_ME_generate_with_openssl_rand_base64_32
BACKUP_ENCRYPTION_KEY=CHANGE_ME_generate_fernet_key

# Database Configuration
# For local PostgreSQL:
# DATABASE_URL=postgresql://qbmigration:your_password@localhost:5432/qbmigration
# For AWS RDS:
DATABASE_URL=postgresql://qbmigration:your_password@your-rds-endpoint.region.rds.amazonaws.com:5432/qbmigration

# PostgreSQL credentials (for local DB)
POSTGRES_USER=qbmigration
POSTGRES_PASSWORD=CHANGE_ME_strong_password
POSTGRES_DB=qbmigration

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=

# AWS Configuration
AWS_REGION=ca-central-1
AWS_S3_BUCKET=your-bucket-name
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# For EC2 instance roles (recommended), leave AWS keys empty and use IAM role

# QuickBooks Online OAuth
QBO_CLIENT_ID=
QBO_CLIENT_SECRET=
QBO_ENVIRONMENT=production
QBO_REDIRECT_URI=https://your-domain.com/api/qbo/callback

# CORS Configuration
ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com

# Rate Limiting
RATELIMIT_ENABLED=true
RATELIMIT_STORAGE_URL=redis://localhost:6379/1

# Sentry Error Tracking (optional)
SENTRY_DSN=
SENTRY_ENVIRONMENT=production

# Email Configuration (optional)
MAIL_SERVER=
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=

# Next.js Frontend
NEXT_PUBLIC_API_URL=https://your-domain.com
NEXT_PUBLIC_APP_URL=https://your-domain.com
ENV_EOF

    chmod 600 /etc/qbmigration/environment
    chown root:$APP_USER /etc/qbmigration/environment

    echo ""
    echo "=========================================="
    echo "IMPORTANT: Environment file created at:"
    echo "/etc/qbmigration/environment"
    echo ""
    echo "You MUST edit this file and set:"
    echo "  - SECRET_KEY"
    echo "  - BACKUP_ENCRYPTION_KEY"
    echo "  - DATABASE_URL"
    echo "  - AWS credentials or configure IAM role"
    echo "  - ALLOWED_ORIGINS"
    echo "=========================================="
fi

# =============================================================================
# 10. Enable and Start Services
# =============================================================================
echo "[10/10] Enabling services (not starting yet - configure environment first)..."

systemctl daemon-reload
systemctl enable nginx
systemctl enable redis-server
systemctl enable qbmigration-api
systemctl enable qbmigration-celery-worker
systemctl enable qbmigration-celery-beat
systemctl enable qbmigration-frontend

# Start nginx and redis immediately
systemctl start nginx
systemctl start redis-server

echo ""
echo "=========================================="
echo "EC2 Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit /etc/qbmigration/environment with your configuration"
echo "2. If using local PostgreSQL, install and configure it"
echo "3. Start services:"
echo "   sudo systemctl start qbmigration-api"
echo "   sudo systemctl start qbmigration-celery-worker"
echo "   sudo systemctl start qbmigration-celery-beat"
echo "   sudo systemctl start qbmigration-frontend"
echo ""
echo "4. For SSL/HTTPS, run:"
echo "   sudo certbot --nginx -d your-domain.com"
echo ""
echo "View logs:"
echo "   journalctl -u qbmigration-api -f"
echo "   journalctl -u qbmigration-frontend -f"
echo "   tail -f /var/log/qbmigration/*.log"
echo ""
echo "=========================================="

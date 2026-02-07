#!/bin/bash
# =============================================================================
# QBMigration Deployment Script
# =============================================================================
# Use this script to deploy updates to an existing EC2 instance.
# Run as: sudo ./deploy.sh [--branch main] [--restart-services]
# =============================================================================

set -e

# Configuration
APP_USER="qbmigration"
APP_DIR="/opt/qbmigration"
BRANCH="${BRANCH:-main}"
RESTART_SERVICES=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --restart-services)
            RESTART_SERVICES=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--branch BRANCH] [--restart-services]"
            echo ""
            echo "Options:"
            echo "  --branch BRANCH      Git branch to deploy (default: main)"
            echo "  --restart-services   Restart all services after deployment"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "QBMigration Deployment - $(date)"
echo "Branch: $BRANCH"
echo "=========================================="

# =============================================================================
# Pre-deployment checks
# =============================================================================
echo "[1/6] Running pre-deployment checks..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (sudo)"
    exit 1
fi

# Check if app directory exists
if [ ! -d "$APP_DIR" ]; then
    echo "Error: Application directory $APP_DIR does not exist"
    echo "Run user-data.sh first for initial setup"
    exit 1
fi

# Check if environment file exists
if [ ! -f /etc/qbmigration/environment ]; then
    echo "Error: Environment file /etc/qbmigration/environment does not exist"
    exit 1
fi

# =============================================================================
# Create backup
# =============================================================================
echo "[2/6] Creating backup..."

BACKUP_DIR="/opt/qbmigration-backups"
BACKUP_NAME="backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup current code (excluding venv and node_modules)
tar --exclude='venv' --exclude='node_modules' --exclude='.next' \
    -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" \
    -C /opt qbmigration

echo "Backup created: $BACKUP_DIR/$BACKUP_NAME.tar.gz"

# Keep only last 5 backups
ls -t "$BACKUP_DIR"/*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm

# =============================================================================
# Pull latest code
# =============================================================================
echo "[3/6] Pulling latest code..."

cd "$APP_DIR"

# AUDIT FIX P1-03: Validate branch name to prevent shell injection
if ! echo "$BRANCH" | grep -qE '^[a-zA-Z0-9/_.-]+$'; then
    echo "Error: Invalid branch name '$BRANCH'. Only alphanumeric, /, _, ., - allowed."
    exit 1
fi

# AUDIT FIX P2-10: Save stash reference for recovery instead of silent discard
STASH_REF=$(git stash create 2>/dev/null)
if [ -n "$STASH_REF" ]; then
    echo "Stashed local changes: $STASH_REF"
    echo "$(date): $STASH_REF" >> "$BACKUP_DIR/stash-refs.log"
    git stash store -m "pre-deploy-$(date +%s)" "$STASH_REF"
fi

# Fetch and checkout
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"

# Fix permissions
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# =============================================================================
# Update Python dependencies
# =============================================================================
echo "[4/6] Updating Python dependencies..."

source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip wheel
# AUDIT FIX P2-13: Verify dependency integrity with hash checking if available
if [ -f requirements-locked.txt ]; then
    pip install --require-hashes -r requirements-locked.txt
else
    pip install -r requirements.txt
fi
pip install -r QBMigrationServer/requirements.txt 2>/dev/null || true

# =============================================================================
# Update Frontend
# =============================================================================
echo "[5/6] Rebuilding Next.js frontend..."

cd "$APP_DIR/forensicbridge-dashboard"
npm ci --production=false
npm run build

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# =============================================================================
# Restart services (if requested)
# =============================================================================
echo "[6/6] Finalizing deployment..."

if [ "$RESTART_SERVICES" = true ]; then
    echo "Restarting services..."

    systemctl restart qbmigration-api
    systemctl restart qbmigration-celery-worker
    systemctl restart qbmigration-celery-beat
    systemctl restart qbmigration-frontend

    # Wait for services to start
    sleep 5

    # Check service status
    echo ""
    echo "Service Status:"
    echo "---------------"
    systemctl is-active qbmigration-api && echo "API: Running" || echo "API: NOT RUNNING"
    systemctl is-active qbmigration-celery-worker && echo "Celery Worker: Running" || echo "Celery Worker: NOT RUNNING"
    systemctl is-active qbmigration-celery-beat && echo "Celery Beat: Running" || echo "Celery Beat: NOT RUNNING"
    systemctl is-active qbmigration-frontend && echo "Frontend: Running" || echo "Frontend: NOT RUNNING"
else
    echo ""
    echo "Services NOT restarted. To restart, run:"
    echo "  sudo systemctl restart qbmigration-api"
    echo "  sudo systemctl restart qbmigration-celery-worker"
    echo "  sudo systemctl restart qbmigration-celery-beat"
    echo "  sudo systemctl restart qbmigration-frontend"
fi

# =============================================================================
# Health check
# =============================================================================
echo ""
echo "Running health check..."

sleep 3

if curl -sf http://localhost:5000/health > /dev/null 2>&1; then
    echo "API health check: PASSED"
else
    echo "API health check: FAILED"
    echo "Check logs: journalctl -u qbmigration-api -n 50"
fi

if curl -sf http://localhost:3000 > /dev/null 2>&1; then
    echo "Frontend health check: PASSED"
else
    echo "Frontend health check: FAILED (may still be starting)"
fi

echo ""
echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
echo ""
echo "Rollback command (if needed):"
echo "  tar -xzf $BACKUP_DIR/$BACKUP_NAME.tar.gz -C /opt"
echo "  sudo systemctl restart qbmigration-api qbmigration-frontend"
echo "=========================================="

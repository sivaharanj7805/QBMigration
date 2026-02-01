# EC2 Deployment Troubleshooting Guide

## Common Issues and Solutions

### 502 Bad Gateway Error

**Symptom:** Browser shows "502 Bad Gateway" or returns HTML instead of JSON:
```
Unexpected token '<', "<html> <h"... is not valid JSON
```

**Cause:** Nginx cannot connect to the backend Flask API.

**Diagnosis:**
```bash
# Check if Flask API is running
sudo systemctl status qbmigration-api

# Check API logs
sudo journalctl -u qbmigration-api -n 100 --no-pager

# Test if Flask is responding locally
curl http://localhost:5000/health

# Check nginx error logs
sudo tail -f /var/log/nginx/error.log
```

**Solutions:**

1. **Flask not running:**
   ```bash
   sudo systemctl start qbmigration-api
   sudo systemctl status qbmigration-api
   ```

2. **Flask crashing on startup** (check logs for error):
   ```bash
   # View full startup logs
   sudo journalctl -u qbmigration-api -n 200

   # Common causes:
   # - Missing environment variables (SECRET_KEY, BACKUP_ENCRYPTION_KEY)
   # - Invalid database connection
   # - Missing Python dependencies
   ```

3. **Environment file not configured:**
   ```bash
   # Edit environment file
   sudo nano /etc/qbmigration/environment

   # Ensure all required variables are set:
   # - SECRET_KEY
   # - BACKUP_ENCRYPTION_KEY
   # - DATABASE_URL
   # - ALLOWED_ORIGINS
   ```

4. **Database connection failed:**
   ```bash
   # Test database connection
   source /opt/qbmigration/venv/bin/activate
   python3 -c "
   import os
   os.chdir('/opt/qbmigration/QBMigrationServer')
   from dotenv import load_dotenv
   load_dotenv('/etc/qbmigration/environment')
   from sqlalchemy import create_engine
   engine = create_engine(os.environ['DATABASE_URL'])
   conn = engine.connect()
   print('Database connection successful!')
   conn.close()
   "
   ```

---

### Services Won't Start

**Diagnosis:**
```bash
# Check all service statuses
sudo systemctl status qbmigration-api
sudo systemctl status qbmigration-celery-worker
sudo systemctl status qbmigration-celery-beat
sudo systemctl status qbmigration-frontend

# View logs for specific service
sudo journalctl -u qbmigration-api -f
```

**Common Issues:**

1. **Permission denied errors:**
   ```bash
   sudo chown -R qbmigration:qbmigration /opt/qbmigration
   sudo chown -R qbmigration:qbmigration /var/log/qbmigration
   sudo chown -R qbmigration:qbmigration /var/lib/qbmigration
   ```

2. **Missing virtual environment:**
   ```bash
   cd /opt/qbmigration
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install gunicorn gevent
   ```

3. **Environment file permissions:**
   ```bash
   sudo chmod 640 /etc/qbmigration/environment
   sudo chown root:qbmigration /etc/qbmigration/environment
   ```

---

### CORS Errors

**Symptom:** Browser console shows:
```
Access to fetch at 'https://api.example.com' from origin 'https://app.example.com'
has been blocked by CORS policy
```

**Solution:**
```bash
# Edit environment file
sudo nano /etc/qbmigration/environment

# Add all your frontend origins:
ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com,https://app.your-domain.com

# Restart API
sudo systemctl restart qbmigration-api
```

---

### Frontend Not Loading (Next.js)

**Diagnosis:**
```bash
# Check if Next.js is running
sudo systemctl status qbmigration-frontend
curl http://localhost:3000

# Check logs
sudo journalctl -u qbmigration-frontend -n 100
```

**Common Issues:**

1. **Build failed:**
   ```bash
   cd /opt/qbmigration/forensicbridge-dashboard
   source /etc/qbmigration/environment
   npm run build
   ```

2. **Missing node_modules:**
   ```bash
   cd /opt/qbmigration/forensicbridge-dashboard
   rm -rf node_modules
   npm ci
   npm run build
   ```

3. **Environment variables not set:**
   ```bash
   # Ensure these are in /etc/qbmigration/environment:
   NEXT_PUBLIC_API_URL=https://your-domain.com
   NEXT_PUBLIC_APP_URL=https://your-domain.com
   ```

---

### Database Connection Issues

**Symptom:** API logs show database connection errors.

**Diagnosis:**
```bash
# Test PostgreSQL connection
psql -h your-rds-endpoint -U qbmigration -d qbmigration

# For local PostgreSQL
sudo -u postgres psql -c "SELECT 1"
```

**Solutions:**

1. **RDS Security Group:** Ensure EC2 security group can access RDS on port 5432

2. **Wrong credentials:** Verify DATABASE_URL in environment file

3. **Database doesn't exist:**
   ```bash
   # Create database (local PostgreSQL)
   sudo -u postgres createdb qbmigration
   sudo -u postgres createuser qbmigration
   sudo -u postgres psql -c "ALTER USER qbmigration PASSWORD 'your_password';"
   sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE qbmigration TO qbmigration;"
   ```

---

### Redis Connection Issues

**Diagnosis:**
```bash
# Check if Redis is running
sudo systemctl status redis-server

# Test Redis connection
redis-cli ping
# Should return: PONG

# With password
redis-cli -a YOUR_PASSWORD ping
```

**Solutions:**

1. **Redis not running:**
   ```bash
   sudo systemctl start redis-server
   sudo systemctl enable redis-server
   ```

2. **Memory issues:**
   ```bash
   # Check Redis memory
   redis-cli info memory

   # Clear cache if needed
   redis-cli FLUSHALL
   ```

---

### SSL/HTTPS Issues

**Setup Let's Encrypt:**
```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal (certbot sets this up automatically)
sudo certbot renew --dry-run
```

**Certificate Renewal Failed:**
```bash
# Check certbot logs
sudo cat /var/log/letsencrypt/letsencrypt.log

# Manual renewal
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

---

### High Memory/CPU Usage

**Diagnosis:**
```bash
# Check system resources
htop

# Check specific process
ps aux | grep gunicorn
ps aux | grep celery
ps aux | grep node

# Check memory usage
free -h
```

**Solutions:**

1. **Reduce Gunicorn workers:**
   ```bash
   # Edit service file
   sudo nano /etc/systemd/system/qbmigration-api.service
   # Change --workers 4 to --workers 2
   sudo systemctl daemon-reload
   sudo systemctl restart qbmigration-api
   ```

2. **Reduce Celery concurrency:**
   ```bash
   # Edit service file
   sudo nano /etc/systemd/system/qbmigration-celery-worker.service
   # Change --concurrency=4 to --concurrency=2
   sudo systemctl daemon-reload
   sudo systemctl restart qbmigration-celery-worker
   ```

---

## Quick Health Check Script

Save this as `/opt/qbmigration/health-check.sh`:

```bash
#!/bin/bash
echo "=== QBMigration Health Check ==="
echo ""

# Services
echo "Services:"
for svc in qbmigration-api qbmigration-celery-worker qbmigration-celery-beat qbmigration-frontend nginx redis-server; do
    status=$(systemctl is-active $svc 2>/dev/null || echo "not-found")
    printf "  %-30s %s\n" "$svc:" "$status"
done
echo ""

# Endpoints
echo "Endpoints:"
api_health=$(curl -sf http://localhost:5000/health && echo "OK" || echo "FAILED")
frontend=$(curl -sf http://localhost:3000 > /dev/null && echo "OK" || echo "FAILED")
nginx=$(curl -sf http://localhost/health && echo "OK" || echo "FAILED")
printf "  %-30s %s\n" "Flask API (5000):" "$api_health"
printf "  %-30s %s\n" "Next.js (3000):" "$frontend"
printf "  %-30s %s\n" "Nginx (80):" "$nginx"
echo ""

# Resources
echo "Resources:"
echo "  Memory: $(free -h | awk '/^Mem:/ {print $3 "/" $2}')"
echo "  Disk: $(df -h / | awk 'NR==2 {print $3 "/" $2 " (" $5 " used)"}')"
echo ""
```

Run with: `bash /opt/qbmigration/health-check.sh`

---

## Log Locations

| Service | Log Location |
|---------|-------------|
| Flask API | `/var/log/qbmigration/gunicorn-*.log`, `journalctl -u qbmigration-api` |
| Celery Worker | `/var/log/qbmigration/celery-worker.log` |
| Celery Beat | `/var/log/qbmigration/celery-beat.log` |
| Nginx | `/var/log/nginx/access.log`, `/var/log/nginx/error.log` |
| Setup Script | `/var/log/qbmigration-setup.log` |

---

## Getting Help

1. Check logs first: `sudo journalctl -u qbmigration-api -n 100`
2. Review environment file: `sudo cat /etc/qbmigration/environment`
3. Test services locally: `curl http://localhost:5000/health`
4. Report issues: https://github.com/sivaharanj7805/QBMigration/issues

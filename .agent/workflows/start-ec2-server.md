---
description: How to start all ForensicBridge services on EC2 server
---

# Starting ForensicBridge on EC2

Quick commands to start all services on your AWS EC2 server.

## Quick Start (All Services)

```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-elastic-ip

# Start all services in order
cd /home/ubuntu/QBMigration

# 1. Activate virtual environment
source QBMigrationServer/venv/bin/activate

# 2. Initialize database (first time only)
cd QBMigrationServer
python init_database.py

# 3. Start Flask Backend (in screen session)
screen -S flask
python run.py
# Press Ctrl+A, then D to detach

# 4. Start Frontend (in another screen)
screen -S frontend
cd ../forensicbridge-dashboard
npm run start
# Press Ctrl+A, then D to detach

# 5. (Optional) Start Celery workers for background tasks
screen -S celery
cd ../QBMigrationServer
celery -A workers.migration_worker worker --loglevel=info
# Press Ctrl+A, then D to detach
```

## Using systemd (Recommended for Production)

### Create Service Files

**Flask Backend** (`/etc/systemd/system/forensicbridge-api.service`):
```ini
[Unit]
Description=ForensicBridge Flask API
After=network.target postgresql.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/QBMigration/QBMigrationServer
Environment="PATH=/home/ubuntu/QBMigration/QBMigrationServer/venv/bin"
ExecStart=/home/ubuntu/QBMigration/QBMigrationServer/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 'app:create_app()'
Restart=always

[Install]
WantedBy=multi-user.target
```

**Next.js Frontend** (`/etc/systemd/system/forensicbridge-web.service`):
```ini
[Unit]
Description=ForensicBridge Dashboard
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/QBMigration/forensicbridge-dashboard
ExecStart=/usr/bin/npm run start
Restart=always
Environment=PORT=3000

[Install]
WantedBy=multi-user.target
```

### Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services to start on boot
sudo systemctl enable forensicbridge-api
sudo systemctl enable forensicbridge-web

# Start services
sudo systemctl start forensicbridge-api
sudo systemctl start forensicbridge-web

# Check status
sudo systemctl status forensicbridge-api
sudo systemctl status forensicbridge-web
```

## Verify Everything is Running

```bash
# Check Flask API
curl http://localhost:5000/health

# Check Frontend (from your browser)
# Go to: https://app.forensicbridge.ca or http://your-server-ip:3000

# View logs
sudo journalctl -u forensicbridge-api -f
sudo journalctl -u forensicbridge-web -f
```

## Ports Used

| Service | Port | URL |
|---------|------|-----|
| Flask API | 5000 | http://localhost:5000 |
| Next.js Frontend | 3000 | http://localhost:3000 |
| PostgreSQL | 5432 | localhost:5432 |
| Redis (if used) | 6379 | localhost:6379 |

## Troubleshooting

```bash
# If a service fails, check logs
sudo journalctl -u forensicbridge-api --no-pager -n 50

# Restart services
sudo systemctl restart forensicbridge-api
sudo systemctl restart forensicbridge-web

# Re-attach to screen sessions
screen -r flask    # Flask session
screen -r frontend # Frontend session
```

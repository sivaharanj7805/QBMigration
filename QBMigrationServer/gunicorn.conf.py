"""
Gunicorn Configuration for Production Deployment

EC2 Deployment:
    gunicorn wsgi:application --config gunicorn.conf.py

With systemd:
    Create /etc/systemd/system/qbmigration.service with:

    [Unit]
    Description=QB Migration Server
    After=network.target

    [Service]
    User=ubuntu
    Group=ubuntu
    WorkingDirectory=/opt/qbmigration
    Environment="PATH=/opt/qbmigration/venv/bin"
    EnvironmentFile=/opt/qbmigration/.env
    ExecStart=/opt/qbmigration/venv/bin/gunicorn wsgi:application -c gunicorn.conf.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
"""

import os
import multiprocessing

# =============================================================================
# SERVER SOCKET
# =============================================================================

# Bind to all interfaces for EC2 (load balancer will connect)
# In production, this should be behind an ALB/NLB or nginx
bind = os.getenv('GUNICORN_BIND', '0.0.0.0:5000')

# Backlog - number of pending connections
backlog = 2048

# =============================================================================
# WORKER PROCESSES
# =============================================================================

# Number of worker processes
# Rule of thumb: 2-4 x $(NUM_CORES)
# For t3.micro (2 vCPU): 4 workers
# For t3.small (2 vCPU): 4 workers
# For t3.medium (2 vCPU): 4-6 workers
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))

# Worker class - use gthread for thread-based concurrency
# PRODUCTION FIX: Standardized on gthread to avoid gevent monkey-patching issues
# with threading.Lock used in chunked uploads and other modules
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'gthread')

# Threads per worker (only used with sync/gthread workers)
threads = int(os.getenv('GUNICORN_THREADS', 4))

# Max requests before worker restart (prevents memory leaks)
max_requests = int(os.getenv('GUNICORN_MAX_REQUESTS', 1000))
max_requests_jitter = int(os.getenv('GUNICORN_MAX_REQUESTS_JITTER', 100))

# =============================================================================
# TIMEOUTS
# =============================================================================

# Worker timeout (seconds) - important for long-running migrations
# Set high enough for file uploads but not infinite
timeout = int(os.getenv('GUNICORN_TIMEOUT', 120))

# Graceful timeout for worker shutdown
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', 30))

# Keep-alive timeout
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', 5))

# =============================================================================
# SECURITY
# =============================================================================

# Limit request line size (default: 4094)
limit_request_line = 4094

# Limit number of headers
limit_request_fields = 100

# Limit header field size
limit_request_field_size = 8190

# =============================================================================
# LOGGING
# =============================================================================

# Access log - set to '-' for stdout (captured by CloudWatch/journald)
accesslog = os.getenv('GUNICORN_ACCESS_LOG', '-')

# Error log - set to '-' for stderr
errorlog = os.getenv('GUNICORN_ERROR_LOG', '-')

# Log level
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')

# Access log format (combined format for ALB parsing)
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# =============================================================================
# PROCESS NAMING
# =============================================================================

# Process name
proc_name = 'qbmigration-server'

# =============================================================================
# SERVER MECHANICS
# =============================================================================

# Daemon mode (set to False for systemd/supervisor management)
daemon = False

# PID file
pidfile = os.getenv('GUNICORN_PID_FILE', '/tmp/gunicorn.pid')

# User/Group (uncomment for production with dedicated user)
# user = 'ubuntu'
# group = 'ubuntu'

# Working directory
chdir = os.path.dirname(os.path.abspath(__file__))

# Temp directory for worker heartbeat
worker_tmp_dir = '/dev/shm'

# =============================================================================
# HOOKS
# =============================================================================

def on_starting(server):
    """Called just before the master process is initialized."""
    pass


def on_reload(server):
    """Called before the master process reloads."""
    pass


def when_ready(server):
    """Called just after the server is started."""
    import logging
    logging.info("QB Migration Server is ready. Listening on %s", bind)


def worker_int(worker):
    """Called when a worker receives SIGINT or SIGQUIT."""
    import logging
    logging.info("Worker %s received INT/QUIT signal", worker.pid)


def worker_abort(worker):
    """Called when a worker receives SIGABRT."""
    import logging
    logging.warning("Worker %s aborted!", worker.pid)


def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    import logging
    logging.info("Worker %s spawned (pid: %s)", worker.age, worker.pid)


def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    pass


def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    import logging
    logging.info("Worker %s exited (pid: %s)", worker.age, worker.pid)


def nworkers_changed(server, new_value, old_value):
    """Called when number of workers changes."""
    import logging
    logging.info("Number of workers changed from %d to %d", old_value, new_value)


def on_exit(server):
    """Called just before exiting gunicorn."""
    import logging
    logging.info("QB Migration Server shutting down")

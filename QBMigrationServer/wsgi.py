"""
WSGI Entry Point for Production Deployment

This file is the entry point for Gunicorn and other WSGI servers.
Usage:
    gunicorn wsgi:application --config gunicorn.conf.py

For EC2 deployment:
    1. Set FLASK_ENV=production
    2. Set all required environment variables (see .env.example)
    3. Run: gunicorn wsgi:application --config gunicorn.conf.py
"""

import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# Load environment variables before importing app
load_dotenv()

# CRITICAL SECURITY FIX: Require explicit FLASK_ENV configuration
# Auto-setting to production is dangerous - could cause unexpected behavior
if not os.getenv('FLASK_ENV'):
    raise RuntimeError(
        "FLASK_ENV must be explicitly set. "
        "For production: export FLASK_ENV=production "
        "For development: export FLASK_ENV=development "
        "For testing: export FLASK_ENV=testing"
    )

# Import the Flask application
from app import app as application

# Validate configuration at startup
from config import validate_config

if os.getenv('FLASK_ENV') == 'production':
    try:
        validate_config()
    except RuntimeError as e:
        import logging
        logging.error(f"Configuration validation failed: {e}")
        raise

# For compatibility with some WSGI servers
app = application

if __name__ == '__main__':
    # This block only runs if you execute wsgi.py directly (not recommended)
    logger.info("WARNING: Running wsgi.py directly is for testing only.")
    logger.info("Use 'gunicorn wsgi:application' for production.")
    # HIGH FIX: Bind to localhost only to prevent accidental exposure
    # In production, use a proper WSGI server (gunicorn/uWSGI) with a reverse proxy
    application.run(host='127.0.0.1', port=5000)

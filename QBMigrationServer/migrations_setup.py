"""
Database migration script for ForensicBridge
Run with: flask db upgrade
"""

from flask import Flask
from flask_migrate import Migrate
from models.database import db

# This file sets up Flask-Migrate
# To initialize migrations:
#   flask db init
#   flask db migrate -m "Initial migration"
#   flask db upgrade


def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///forensicbridge.db"  # Dev default
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize database
    db.init_app(app)

    # Initialize migrations
    Migrate(app, db)

    return app


# Migration commands:
#
# 1. Initialize (first time only):
#    flask db init
#
# 2. Create migration after model changes:
#    flask db migrate -m "Description of changes"
#
# 3. Apply migrations:
#    flask db upgrade
#
# 4. Rollback:
#    flask db downgrade

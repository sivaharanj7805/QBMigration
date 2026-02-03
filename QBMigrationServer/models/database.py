from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

def init_db(app):
    """Initialize database"""
    db.init_app(app)

    with app.app_context():
        db.create_all()

    return db


def is_postgresql():
    """Check if current database is PostgreSQL.

    Returns True for PostgreSQL, False for SQLite and other databases.
    Used to conditionally apply PostgreSQL-specific features like FOR UPDATE.
    """
    try:
        dialect = db.session.bind.dialect.name if db.session.bind else 'sqlite'
        return dialect == 'postgresql'
    except Exception:
        return False


def execute_with_row_lock(query_with_lock, query_without_lock, params):
    """Execute a query with row-level locking on PostgreSQL, or without locking on SQLite.

    Args:
        query_with_lock: SQL query string with FOR UPDATE clause (for PostgreSQL)
        query_without_lock: SQL query string without FOR UPDATE (for SQLite)
        params: Dictionary of query parameters

    Returns:
        Query result
    """
    from sqlalchemy import text

    if is_postgresql():
        return db.session.execute(text(query_with_lock), params)
    else:
        return db.session.execute(text(query_without_lock), params)
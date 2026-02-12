import logging
import time

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Session
from utils.env_helper import is_testing

db = SQLAlchemy()

logger = logging.getLogger(__name__)

DB_CONNECT_MAX_RETRIES = 5
DB_CONNECT_BASE_DELAY = 2  # seconds


def init_db(app):
    """Initialize database with retry logic for transient connection failures.

    Retries db.create_all() up to DB_CONNECT_MAX_RETRIES times with exponential
    backoff (2s, 4s, 8s, 16s, 32s) to handle cases where PostgreSQL is still
    starting or temporarily unreachable.
    """
    db.init_app(app)

    with app.app_context():
        # Prevent DetachedInstanceError in testing by keeping instances usable after commits
        # This avoids Flask-Login's current_user becoming detached when endpoints
        # access user attributes after session operations
        if app.config.get("TESTING") or is_testing():
            from sqlalchemy import event

            @event.listens_for(Session, "after_begin")
            def set_expire_on_commit(session, transaction, connection):
                session.expire_on_commit = False

        _create_tables_with_retry(app)

    return db


def _create_tables_with_retry(app):
    """Attempt db.create_all() with exponential backoff retries."""
    last_exc = None
    for attempt in range(1, DB_CONNECT_MAX_RETRIES + 1):
        try:
            db.create_all()
            if attempt > 1:
                app.logger.info(
                    f"Database connection succeeded on attempt {attempt}"
                )
            return
        except Exception as exc:
            last_exc = exc
            if attempt < DB_CONNECT_MAX_RETRIES:
                delay = DB_CONNECT_BASE_DELAY * (2 ** (attempt - 1))
                app.logger.warning(
                    f"Database connection attempt {attempt}/{DB_CONNECT_MAX_RETRIES} "
                    f"failed: {exc}. Retrying in {delay}s..."
                )
                time.sleep(delay)
                # Dispose stale connections so the next attempt gets a fresh socket
                db.engine.dispose()
            else:
                app.logger.error(
                    f"Database connection failed after {DB_CONNECT_MAX_RETRIES} "
                    f"attempts: {exc}"
                )
    raise last_exc


def is_postgresql():
    """Check if current database is PostgreSQL.

    Returns True for PostgreSQL, False for SQLite and other databases.
    Used to conditionally apply PostgreSQL-specific features like FOR UPDATE.
    """
    try:
        dialect = db.session.bind.dialect.name if db.session.bind else "sqlite"
        return dialect == "postgresql"
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

"""
Environment Helper
==================
Centralized environment detection to replace deprecated FLASK_ENV usage.

Flask 3.0 deprecated FLASK_ENV. This module provides a single source of truth
for environment detection, checking APP_ENV first, then falling back to
FLASK_ENV for backward compatibility.

Usage:
    from utils.env_helper import get_env, is_production, is_testing

    if is_production():
        ...
"""

import os


def get_env() -> str:
    """
    Get the current application environment.

    Checks APP_ENV first (preferred), then FLASK_ENV (backward compat).
    Defaults to 'development' if neither is set.
    """
    return os.getenv("APP_ENV") or os.getenv("FLASK_ENV", "development")


def is_production() -> bool:
    """Check if running in production environment."""
    env = get_env().lower()
    debug = os.getenv("FLASK_DEBUG", os.getenv("DEBUG", "0"))
    return env == "production" and debug not in ("1", "true", "True", "TRUE")


def is_testing() -> bool:
    """Check if running in testing environment."""
    return get_env().lower() in ("testing", "test")


def is_development() -> bool:
    """Check if running in development environment."""
    return get_env().lower() in ("development", "dev")

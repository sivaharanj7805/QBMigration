"""
FIX XC-02: Centralized Logging Configuration

This module provides consistent logging configuration across all
Python components of the QBMigration platform.

Usage:
    from shared.logging_config import configure_logging, get_logger

    configure_logging()  # Call once at startup
    logger = get_logger(__name__)

Components:
    - QBMigrationServer (Flask backend)
    - QBMigrationService (Python transformation service)
"""

import logging
import logging.handlers
import os
import sys
from typing import Optional


def _get_env():
    return os.getenv("APP_ENV") or os.getenv("FLASK_ENV", "development")

# ============================================================================
# LOGGING LEVELS BY ENVIRONMENT
# ============================================================================
LOGGING_LEVELS = {
    "production": logging.WARNING,
    "staging": logging.INFO,
    "development": logging.DEBUG,
    "test": logging.DEBUG,
}

# ============================================================================
# LOG FORMAT TEMPLATES
# ============================================================================
CONSOLE_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
FILE_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
)
JSON_FORMAT = '{"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "message": "%(message)s", "function": "%(funcName)s", "line": %(lineno)d}'


def configure_logging(
    environment: Optional[str] = None,
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    json_format: bool = False,
) -> None:
    """
    Configure logging for the application.

    Args:
        environment: Environment name (production, staging, development)
        log_file: Path to log file (optional)
        max_bytes: Max size of log file before rotation
        backup_count: Number of backup files to keep
        json_format: Use JSON format for logs (for log aggregation)
    """
    env = environment or _get_env()
    level = LOGGING_LEVELS.get(env, logging.INFO)

    # Choose format based on environment
    if json_format or env == "production":
        log_format = JSON_FORMAT
    else:
        log_format = CONSOLE_FORMAT

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # File handler (if log file specified)
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
        root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    for noisy_logger in ["urllib3", "botocore", "boto3", "werkzeug"]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)

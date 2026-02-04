"""
Shared pytest configuration and fixtures for QBMigration test suite.

Centralises sys.path setup so individual test files don't need to
duplicate it, and provides commonly-used mock fixtures.
"""

import sys
import os

# Ensure the QBMigrationService package is importable from tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

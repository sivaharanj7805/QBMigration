"""
FIX XC-03: API Version Configuration

This module provides consistent API versioning across all components.

Usage:
    from shared.api_version import API_VERSION, check_version_compatibility

    # In Flask
    @app.after_request
    def add_version_header(response):
        response.headers['X-API-Version'] = API_VERSION
        return response

    # In client
    if not check_version_compatibility(server_version, client_version):
        raise IncompatibleVersionError()
"""

from typing import Tuple

# Current API version
API_VERSION = "4.3.0"

# Minimum supported client versions by component
MIN_CLIENT_VERSIONS = {
    "desktop_reader": "4.0.0",
    "dashboard": "4.0.0",
    "launcher": "4.0.0",
}

# Version where breaking changes occurred
BREAKING_CHANGES = {
    "4.0.0": [
        "Changed encryption from AES-256-CBC to AES-256-GCM",
        "Added mandatory schema version field",
        "Changed upload endpoint format",
    ],
    "3.0.0": [
        "Changed authentication from session to JWT",
        "Changed migration status enum values",
    ],
}


def parse_version(version: str) -> Tuple[int, int, int]:
    """Parse a semantic version string into a tuple."""
    try:
        parts = version.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2] if len(parts) > 2 else 0))
    except (ValueError, IndexError):
        return (0, 0, 0)


def check_version_compatibility(
    server_version: str, client_version: str, component: str = "desktop_reader"
) -> bool:
    """
    Check if client version is compatible with server.

    Args:
        server_version: Server API version
        client_version: Client version
        component: Client component name

    Returns:
        True if compatible, False otherwise
    """
    min_version = MIN_CLIENT_VERSIONS.get(component, "1.0.0")

    client_tuple = parse_version(client_version)
    min_tuple = parse_version(min_version)

    # Client must be at least minimum version
    if client_tuple < min_tuple:
        return False

    # Major version must match for compatibility
    server_tuple = parse_version(server_version)
    if client_tuple[0] != server_tuple[0]:
        return False

    return True


def get_deprecation_warnings(client_version: str) -> list:
    """
    Get deprecation warnings for a client version.

    Args:
        client_version: Client version string

    Returns:
        List of deprecation warning messages
    """
    warnings = []
    client_tuple = parse_version(client_version)
    server_tuple = parse_version(API_VERSION)

    # Warn if client is more than one minor version behind
    if client_tuple[0] == server_tuple[0] and server_tuple[1] - client_tuple[1] >= 2:
        warnings.append(
            f"Client version {client_version} is outdated. "
            f"Please upgrade to {API_VERSION} for best compatibility."
        )

    return warnings


# Version header names
VERSION_HEADER = "X-API-Version"
CLIENT_VERSION_HEADER = "X-Client-Version"
MIN_VERSION_HEADER = "X-Min-Client-Version"

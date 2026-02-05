"""
Tier Configuration - Centralized tier definitions for the entire application.

FIX LOW-03: Single source of truth for tier configuration.
All modules should import from here to prevent configuration drift.
"""

# Tier configuration - transaction limits and prices
TIER_CONFIG = {
    "starter": {
        "name": "Starter",
        "price_cents": 49700,  # $497
        "transaction_limit": 5000,
        "description": "Up to 5,000 transactions",
    },
    "business": {
        "name": "Business",
        "price_cents": 99700,  # $997
        "transaction_limit": 25000,
        "description": "Up to 25,000 transactions",
    },
    "professional": {
        "name": "Professional",
        "price_cents": 199700,  # $1,997
        "transaction_limit": 100000,
        "description": "Up to 100,000 transactions",
    },
    "enterprise": {
        "name": "Enterprise",
        "price_cents": 399700,  # $3,997
        "transaction_limit": 500000,
        "description": "Up to 500,000 transactions",
    },
    "forensic": {
        "name": "Forensic",
        "price_cents": 799700,  # $7,997
        "transaction_limit": -1,  # Unlimited
        "description": "Unlimited transactions",
    },
}


def get_tier_config(tier_type: str) -> dict:
    """Get configuration for a tier type"""
    return TIER_CONFIG.get(tier_type)


def get_tier_name(tier_type: str) -> str:
    """Get display name for a tier type"""
    config = TIER_CONFIG.get(tier_type, {})
    return config.get("name", "Unknown")


def get_transaction_limit(tier_type: str) -> int:
    """Get transaction limit for a tier type (-1 = unlimited)"""
    config = TIER_CONFIG.get(tier_type, {})
    return config.get("transaction_limit", 5000)


def get_price_cents(tier_type: str) -> int:
    """Get price in cents for a tier type"""
    config = TIER_CONFIG.get(tier_type, {})
    return config.get("price_cents", 0)


def is_valid_tier(tier_type: str) -> bool:
    """Check if tier type is valid"""
    return tier_type in TIER_CONFIG


def get_all_tier_types() -> list:
    """Get list of all valid tier types"""
    return list(TIER_CONFIG.keys())

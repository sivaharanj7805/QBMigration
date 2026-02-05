"""
ForensicBridge Whitelabel System
================================
Allows CPA firms to rebrand the migration tool with:
- Custom company name and logo
- Custom color scheme
- Custom email templates
- License key management
"""

import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class WhitelabelConfig:
    """
    Configuration class for whitelabel branding.
    Loaded from JSON config file or database.
    """

    DEFAULT_BRANDING = {
        "company_name": "ForensicBridge",
        "product_name": "ForensicBridge Migration Suite",
        "logo_path": None,
        "favicon_path": None,
        "primary_color": "#3B82F6",  # Bridge Blue
        "secondary_color": "#F59E0B",  # Forensic Gold
        "accent_color": "#10B981",  # Success Green
        "background_dark": "#0F172A",  # Navy 900
        "text_primary": "#F8FAFC",
        "text_secondary": "#94A3B8",
        "support_email": "support@forensicbridge.com",
        "support_phone": "",
        "website_url": "https://forensicbridge.com",
        "terms_url": "",
        "privacy_url": "",
        "custom_css": "",
        "hide_powered_by": False,
    }

    def __init__(self, config_path: Optional[str] = None):
        self.config = self.DEFAULT_BRANDING.copy()

        if config_path and os.path.exists(config_path):
            self.load_from_file(config_path)

    def load_from_file(self, path: str):
        """Load branding config from JSON file"""
        with open(path, "r") as f:
            custom = json.load(f)
            self.config.update(custom)

    def load_from_dict(self, config: Dict):
        """Load branding from dictionary"""
        self.config.update(config)

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def to_css_variables(self) -> str:
        """Generate CSS variables for theming"""
        return f"""
:root {{
    --primary-color: {self.config['primary_color']};
    --secondary-color: {self.config['secondary_color']};
    --accent-color: {self.config['accent_color']};
    --bg-dark: {self.config['background_dark']};
    --text-primary: {self.config['text_primary']};
    --text-secondary: {self.config['text_secondary']};
}}
{self.config.get('custom_css', '')}
"""

    def to_json(self) -> str:
        return json.dumps(self.config, indent=2)


class LicenseManager:
    """
    Manages whitelabel licenses for reseller partners.

    License Types:
    - STARTER: 10 migrations/year
    - PROFESSIONAL: 100 migrations/year
    - ENTERPRISE: Unlimited migrations
    - RESELLER: Unlimited + whitelabel + sub-licensing
    """

    LICENSE_TIERS = {
        "STARTER": {"migrations": 10, "whitelabel": False, "price": 2500},
        "PROFESSIONAL": {"migrations": 100, "whitelabel": False, "price": 10000},
        "ENTERPRISE": {"migrations": -1, "whitelabel": True, "price": 25000},
        "RESELLER": {
            "migrations": -1,
            "whitelabel": True,
            "sublicense": True,
            "price": 50000,
        },
    }

    def __init__(self, secret_key: str = "forensicbridge-license-key"):
        self.secret_key = secret_key

    def generate_license_key(
        self, company_name: str, tier: str, valid_days: int = 365
    ) -> Dict:
        """Generate a signed license key"""

        if tier not in self.LICENSE_TIERS:
            raise ValueError(f"Invalid tier: {tier}")

        license_data = {
            "company": company_name,
            "tier": tier,
            "issued": datetime.now(timezone.utc).isoformat(),
            "expires": (
                datetime.now(timezone.utc) + timedelta(days=valid_days)
            ).isoformat(),
            "features": self.LICENSE_TIERS[tier],
        }

        # Create signature
        data_str = json.dumps(license_data, sort_keys=True)
        signature = hashlib.sha256((data_str + self.secret_key).encode()).hexdigest()[
            :16
        ]

        license_data["signature"] = signature

        # Encode as base64 for easy distribution
        license_key = base64.b64encode(json.dumps(license_data).encode()).decode()

        return {"license_key": license_key, "details": license_data}

    def validate_license(self, license_key: str) -> Dict:
        """Validate a license key and return its details
        AUDIT FIX: Added format validation before decode
        """
        try:
            # Validate format first
            if not license_key or not isinstance(license_key, str):
                return {"valid": False, "error": "Invalid license key format"}

            # Check if it looks like valid base64
            import re

            if not re.match(r"^[A-Za-z0-9+/=]+$", license_key):
                return {
                    "valid": False,
                    "error": "Invalid license key format (not base64)",
                }

            # Decode
            license_json = base64.b64decode(license_key).decode()
            license_data = json.loads(license_json)

            # Verify signature
            stored_sig = license_data.pop("signature")
            data_str = json.dumps(license_data, sort_keys=True)
            expected_sig = hashlib.sha256(
                (data_str + self.secret_key).encode()
            ).hexdigest()[:16]

            if stored_sig != expected_sig:
                return {"valid": False, "error": "Invalid signature"}

            license_data["signature"] = stored_sig

            # Check expiration
            expires = datetime.fromisoformat(license_data["expires"])
            if datetime.now(timezone.utc) > expires:
                return {
                    "valid": False,
                    "error": "License expired",
                    "details": license_data,
                }

            return {"valid": True, "details": license_data}

        except Exception as e:
            return {"valid": False, "error": str(e)}

    def get_remaining_migrations(self, license_key: str, used_count: int) -> int:
        """Get remaining migrations for a license"""
        validation = self.validate_license(license_key)
        if not validation["valid"]:
            return 0

        limit = validation["details"]["features"]["migrations"]
        if limit == -1:  # Unlimited
            return -1

        return max(0, limit - used_count)


class WhitelabelPortal:
    """
    Reseller portal for managing sub-clients and licenses.
    """

    def __init__(self, reseller_license: str):
        self.license_manager = LicenseManager()
        self.validation = self.license_manager.validate_license(reseller_license)

        if not self.validation["valid"]:
            raise ValueError("Invalid reseller license")

        if not self.validation["details"]["features"].get("sublicense"):
            raise ValueError("License does not include sublicensing")

    def create_client_license(
        self, client_company: str, tier: str = "PROFESSIONAL", valid_days: int = 365
    ) -> Dict:
        """Create a license for a sub-client"""
        # Resellers can only grant up to ENTERPRISE tier
        if tier == "RESELLER":
            tier = "ENTERPRISE"

        return self.license_manager.generate_license_key(
            company_name=client_company, tier=tier, valid_days=valid_days
        )

    def generate_branded_config(
        self, company_name: str, primary_color: str, logo_base64: Optional[str] = None
    ) -> WhitelabelConfig:
        """Generate a branded configuration for a client"""
        config = WhitelabelConfig()
        config.load_from_dict(
            {
                "company_name": company_name,
                "product_name": f"{company_name} Migration Suite",
                "primary_color": primary_color,
                "hide_powered_by": True,
            }
        )
        return config


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Create a reseller license
    lm = LicenseManager()
    reseller = lm.generate_license_key("Big CPA Firm", "RESELLER", 365)
    # AUDIT FIX: Removed debug print of license key
    logger.info("Reseller License: [generated]")

    # Validate it
    validation = lm.validate_license(reseller["license_key"])
    logger.info("Valid:", validation["valid"])
    logger.info("Company:", validation["details"]["company"])
    logger.info("Tier:", validation["details"]["tier"])

    # Create whitelabel config
    config = WhitelabelConfig()
    config.load_from_dict(
        {
            "company_name": "Deloitte",
            "primary_color": "#86BC25",  # Deloitte green
            "product_name": "Deloitte Migration Accelerator",
        }
    )
    logger.info("\nCSS Variables:")
    logger.info(config.to_css_variables())

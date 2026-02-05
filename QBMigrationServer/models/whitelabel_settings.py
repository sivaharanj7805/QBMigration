"""
WhitelabelSettings Model
Stores per-user branding configuration for the ForensicBridge dashboard.
"""

from models.database import db
from datetime import datetime, timezone
import re


class WhitelabelSettings(db.Model):
    """Per-user whitelabel branding settings."""

    __tablename__ = "whitelabel_settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False, index=True
    )

    # Branding
    company_name = db.Column(db.String(255), default="ForensicBridge")
    logo_url = db.Column(db.Text, nullable=True)  # Base64 data URL or path
    primary_color = db.Column(db.String(7), default="#3B82F6")
    secondary_color = db.Column(db.String(7), default="#0F172A")
    accent_color = db.Column(db.String(7), default="#B8860B")

    # Contact
    support_email = db.Column(db.String(255), default="")
    support_phone = db.Column(db.String(50), default="")
    website_url = db.Column(db.String(500), default="")

    # Timestamps
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = db.relationship(
        "User", backref=db.backref("whitelabel_settings", uselist=False)
    )

    # Validation constants
    HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
    MAX_LOGO_SIZE = 500_000  # ~500KB base64 limit

    def to_dict(self):
        return {
            "company_name": self.company_name or "",
            "logo_url": self.logo_url,
            "primary_color": self.primary_color or "#3B82F6",
            "secondary_color": self.secondary_color or "#0F172A",
            "accent_color": self.accent_color or "#B8860B",
            "support_email": self.support_email or "",
            "support_phone": self.support_phone or "",
            "website_url": self.website_url or "",
        }

    @classmethod
    def validate_config(cls, data):
        """Validate whitelabel config data. Returns (cleaned_data, error_message)."""
        errors = []

        # Validate company name
        company_name = (data.get("company_name") or "").strip()
        if company_name and len(company_name) > 255:
            errors.append("Company name must be 255 characters or less")

        # Validate colors
        for field in ("primary_color", "secondary_color", "accent_color"):
            value = data.get(field)
            if value and not cls.HEX_COLOR_RE.match(value):
                errors.append(f"{field} must be a valid hex color (e.g. #3B82F6)")

        # Validate logo size
        logo_url = data.get("logo_url")
        if logo_url and len(logo_url) > cls.MAX_LOGO_SIZE:
            errors.append("Logo data too large. Please use an image under 500KB.")

        # Validate email
        support_email = (data.get("support_email") or "").strip()
        if support_email and len(support_email) > 255:
            errors.append("Support email must be 255 characters or less")

        # Validate URL
        website_url = (data.get("website_url") or "").strip()
        if website_url and len(website_url) > 500:
            errors.append("Website URL must be 500 characters or less")

        if errors:
            return None, "; ".join(errors)

        cleaned = {
            "company_name": company_name or "ForensicBridge",
            "logo_url": logo_url,
            "primary_color": data.get("primary_color", "#3B82F6"),
            "secondary_color": data.get("secondary_color", "#0F172A"),
            "accent_color": data.get("accent_color", "#B8860B"),
            "support_email": support_email,
            "support_phone": (data.get("support_phone") or "").strip()[:50],
            "website_url": website_url,
        }
        return cleaned, None

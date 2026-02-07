import logging
from datetime import datetime, timezone

from flask import current_app
from flask_mail import Mail, Message
from markupsafe import escape as html_escape

logger = logging.getLogger(__name__)

mail = Mail()


def init_mail(app):
    """Initialize Flask-Mail"""
    try:
        mail.init_app(app)
        logger.info("Email notifications initialized")
    except Exception as e:
        logger.error(f"Failed to initialize email: {str(e)}")


def send_email(to, subject, body, html=None):
    """
    Send email

    Args:
        to: Recipient email or list of emails
        subject: Email subject
        body: Plain text body
        html: HTML body (optional)

    Returns:
        bool: True if sent successfully
    """
    try:
        if not current_app.config.get("MAIL_USERNAME"):
            logger.warning("Email not configured, skipping notification")
            return False

        msg = Message(
            subject=subject,
            recipients=[to] if isinstance(to, str) else to,
            body=body,
            html=html,
            sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
        )

        mail.send(msg)

        logger.info(f"Email sent to {to}: {subject}")
        return True

    except Exception as e:
        logger.exception(f"Failed to send email: {str(e)}")
        return False


def send_verification_email(email, token):
    """Send email verification"""
    try:
        server_url = current_app.config.get("SERVER_URL")
        verify_url = f"{server_url}/api/auth/verify/{token}"
        # AUDIT FIX: HTML-escape URL to prevent XSS in email templates
        safe_verify_url = str(html_escape(verify_url))

        subject = "Verify your QB Migration account"

        body = f"""
Welcome to QB Migration!

Please verify your email address by clicking the link below:

{verify_url}

This link will expire in 24 hours.

If you didn't create this account, please ignore this email.

Best regards,
QB Migration Team
"""

        html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #2563eb;">Welcome to QB Migration!</h2>
    <p>Please verify your email address by clicking the button below:</p>
    <p style="margin: 30px 0;">
        <a href="{safe_verify_url}" style="background-color: #2563eb; color: white;
 padding: 12px 24px; text-decoration: none; border-radius: 4px;
 display: inline-block;">
            Verify Email Address
        </a>
    </p>
    <p style="color: #666; font-size: 14px;">
        Or copy and paste this link into your browser:<br>
        <a href="{safe_verify_url}">{safe_verify_url}</a>
    </p>
    <p style="color: #666; font-size: 14px;">
        This link will expire in 24 hours.
    </p>
    <p style="color: #666; font-size: 14px;">
        If you didn't create this account, please ignore this email.
    </p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    <p style="color: #999; font-size: 12px;">
        QB Migration Team<br>
        © {datetime.now(timezone.utc).year} All rights reserved.
    </p>
</body>
</html>
"""

        return send_email(email, subject, body, html)

    except Exception as e:
        logger.exception(f"Failed to send verification email: {str(e)}")
        return False


def send_new_device_alert(email, ip_address):
    """Send new device login alert"""
    try:
        subject = "New device detected on your QB Migration account"

        # FIX MED-05: Escape user-controllable data in HTML
        safe_ip = str(html_escape(ip_address or "Unknown"))

        body = f"""
Security Alert: New Device Login

We detected a login to your QB Migration account from a new device.

IP Address: {safe_ip}
Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC

If this was you, you can safely ignore this email.

If this wasn't you, please:
1. Change your password immediately
2. Enable two-factor authentication
3. Contact our support team

Best regards,
QB Migration Security Team
"""

        html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #dc2626;">Security Alert: New Device Login</h2>
    <p>We detected a login to your QB Migration account from a new device.</p>
    <div style="background-color: #f3f4f6; padding: 15px; border-radius: 4px; margin: 20px 0;">
        <p style="margin: 5px 0;"><strong>IP Address:</strong> {safe_ip}</p>
        <p style="margin: 5px 0;"><strong>Time:</strong>\
 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
    </div>
    <p><strong>If this was you,</strong> you can safely ignore this email.</p>
    <p><strong>If this wasn't you,</strong> please take immediate action:</p>
    <ol>
        <li>Change your password immediately</li>
        <li>Enable two-factor authentication</li>
        <li>Contact our support team</li>
    </ol>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    <p style="color: #999; font-size: 12px;">
        QB Migration Security Team<br>
        © {datetime.now(timezone.utc).year} All rights reserved.
    </p>
</body>
</html>
"""

        return send_email(email, subject, body, html)

    except Exception as e:
        logger.exception(f"Failed to send new device alert: {str(e)}")
        return False


def send_migration_failure_alert(migration):
    """Send alert for migration failure"""
    try:
        admin_email = current_app.config.get("ALERT_EMAIL")

        if not admin_email:
            logger.warning("Admin alert email not configured")
            return False

        subject = f"Migration Failed: {migration.migration_id}"

        body = f"""
Migration Failure Alert

Migration ID: {migration.migration_id}
User: {migration.user.email}
Company: {migration.company_name or 'N/A'}
Status: {migration.status}
Error: {migration.get_error_message() or 'Unknown error'}
Retry Count: {migration.retry_count}/{migration.max_retries}
Created: {migration.created_at}
Failed: {migration.completed_at}

AWS Instance: {migration.aws_instance_id or 'N/A'}
S3 URI: {migration.s3_uri or 'N/A'}

Action Required: {"Maximum retries reached" if not migration.can_retry() else "Available for retry"}
"""

        return send_email(admin_email, subject, body)

    except Exception as e:
        logger.exception(f"Failed to send failure alert: {str(e)}")
        return False


def send_migration_complete_notification(user_email, migration):
    """Send migration completion notification to user"""
    try:
        subject = "Your QuickBooks migration is complete!"

        body = f"""
Great news! Your QuickBooks migration has completed successfully.

Migration Details:
- Company: {migration.company_name or 'N/A'}
- Records Migrated: {migration.total_records_migrated}
  - Customers: {migration.customers_migrated}
  - Vendors: {migration.vendors_migrated}
  - Invoices: {migration.invoices_migrated}
- Duration: {migration.get_duration_minutes()} minutes
- Cost: ${migration.actual_cost_usd or migration.estimated_cost_usd or 0:.2f}

You can now log in to QuickBooks Online to access your migrated data.

Best regards,
QB Migration Team
"""

        html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #10b981;">Migration Complete! 🎉</h2>
    <p>Great news! Your QuickBooks migration has completed successfully.</p>
    <div style="background-color: #f3f4f6; padding: 20px; border-radius: 4px; margin: 20px 0;">
        <h3 style="margin-top: 0;">Migration Details</h3>
        <p><strong>Company:</strong> {migration.company_name or 'N/A'}</p>
        <p><strong>Records Migrated:</strong> {migration.total_records_migrated}</p>
        <ul style="margin: 10px 0;">
            <li>Customers: {migration.customers_migrated}</li>
            <li>Vendors: {migration.vendors_migrated}</li>
            <li>Invoices: {migration.invoices_migrated}</li>
        </ul>
        <p><strong>Duration:</strong> {migration.get_duration_minutes()} minutes</p>
        <p><strong>Cost:</strong> ${migration.actual_cost_usd or migration.estimated_cost_usd or 0:.2f}</p>
    </div>
    <p>You can now log in to QuickBooks Online to access your migrated data.</p>
    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
    <p style="color: #999; font-size: 12px;">
        QB Migration Team<br>
        © {datetime.now(timezone.utc).year} All rights reserved.
    </p>
</body>
</html>
"""

        return send_email(user_email, subject, body, html)

    except Exception as e:
        logger.exception(f"Failed to send completion notification: {str(e)}")
        return False

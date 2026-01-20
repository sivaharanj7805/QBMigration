"""
Legal Pages API - Serves EULA, Privacy Policy, and other legal documents
Required for Intuit App Registration
"""

from flask import Blueprint, render_template, redirect, url_for

legal_bp = Blueprint('legal', __name__, url_prefix='/legal')


@legal_bp.route('/eula')
def eula():
    """End User License Agreement page"""
    return render_template('legal/eula.html')


@legal_bp.route('/privacy')
def privacy_policy():
    """Privacy Policy page"""
    return render_template('legal/privacy.html')


@legal_bp.route('/terms')
def terms_of_service():
    """Terms of Service page (redirect to EULA)"""
    return redirect(url_for('legal.eula'))


@legal_bp.route('/cookies')
def cookie_policy():
    """Cookie Policy page"""
    return render_template('legal/cookies.html')


@legal_bp.route('/security')
def security():
    """Security practices page"""
    return render_template('legal/security.html')


@legal_bp.route('/data-processing')
def data_processing():
    """Data Processing Agreement page"""
    return render_template('legal/data-processing.html')

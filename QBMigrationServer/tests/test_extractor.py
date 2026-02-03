"""
Test Suite for Extractor API Endpoints
Tests /api/extractor/* endpoints from api/extractor.py

All endpoints are public (no authentication required).
These endpoints serve extractor download information, version details,
security instructions, and health status.
"""

import pytest
import json
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExtractorInfo:
    """Tests for GET /api/extractor/info"""

    def test_info_returns_200(self, client):
        """Info endpoint should return 200 with availability information."""
        response = client.get('/api/extractor/info')
        assert response.status_code == 200

    def test_info_returns_json(self, client):
        """Info endpoint should return valid JSON."""
        response = client.get('/api/extractor/info')
        data = response.get_json()
        assert data is not None

    def test_info_has_available_field(self, client):
        """Info endpoint must include an 'available' boolean field."""
        response = client.get('/api/extractor/info')
        data = response.get_json()
        assert 'available' in data
        assert isinstance(data['available'], bool)

    def test_info_has_source_field(self, client):
        """Info endpoint must include a 'source' field indicating download source."""
        response = client.get('/api/extractor/info')
        data = response.get_json()
        assert 'source' in data
        valid_sources = ['zip_package', 'local', 'cached', 'github', 'bootstrap']
        assert data['source'] in valid_sources

    def test_info_has_download_url(self, client):
        """Info endpoint must include a download URL."""
        response = client.get('/api/extractor/info')
        data = response.get_json()
        # Every source variant returns a download_url or bootstrap_url
        has_url = 'download_url' in data or 'bootstrap_url' in data
        assert has_url, f"Expected a download URL in response: {data}"


class TestExtractorStatus:
    """Tests for GET /api/extractor/status"""

    def test_status_returns_200(self, client):
        """Status endpoint should return 200."""
        response = client.get('/api/extractor/status')
        assert response.status_code == 200

    def test_status_returns_all_sources(self, client):
        """Status endpoint must report on all download sources."""
        response = client.get('/api/extractor/status')
        data = response.get_json()

        expected_sources = [
            'local_installer',
            'cached_installer',
            'zip_package',
            'bootstrap_bat',
            'bootstrap_ps1',
            'github_release',
            'fallback_generator',
        ]
        for source in expected_sources:
            assert source in data, f"Missing source '{source}' in status response"

    def test_status_sources_have_available_field(self, client):
        """Each source in status should have an 'available' boolean."""
        response = client.get('/api/extractor/status')
        data = response.get_json()

        sources_with_available = [
            'local_installer',
            'cached_installer',
            'zip_package',
            'bootstrap_bat',
            'bootstrap_ps1',
            'github_release',
            'fallback_generator',
        ]
        for source in sources_with_available:
            assert 'available' in data[source], (
                f"Source '{source}' missing 'available' field"
            )

    def test_status_has_recommended_download(self, client):
        """Status endpoint should include a recommended download URL."""
        response = client.get('/api/extractor/status')
        data = response.get_json()
        assert 'recommended_download' in data

    def test_status_fallback_always_available(self, client):
        """Fallback generator should always be available."""
        response = client.get('/api/extractor/status')
        data = response.get_json()
        assert data['fallback_generator']['available'] is True


class TestExtractorVersion:
    """Tests for GET /api/extractor/version"""

    def test_version_returns_200(self, client):
        """Version endpoint should return 200."""
        response = client.get('/api/extractor/version')
        assert response.status_code == 200

    def test_version_has_version_string(self, client):
        """Version endpoint must include a version string."""
        response = client.get('/api/extractor/version')
        data = response.get_json()
        assert 'version' in data
        assert isinstance(data['version'], str)
        # Version should look like a semver (e.g., "4.4.0")
        parts = data['version'].split('.')
        assert len(parts) >= 2, f"Version '{data['version']}' does not look like semver"

    def test_version_has_minimum_qb_version(self, client):
        """Version endpoint must specify minimum QuickBooks version."""
        response = client.get('/api/extractor/version')
        data = response.get_json()
        assert 'minimum_qb_version' in data
        assert 'QuickBooks' in data['minimum_qb_version']

    def test_version_has_supported_backends(self, client):
        """Version endpoint must list supported backends."""
        response = client.get('/api/extractor/version')
        data = response.get_json()
        assert 'supported_backends' in data
        assert isinstance(data['supported_backends'], list)
        assert len(data['supported_backends']) > 0

        # Each backend should have name and type
        for backend in data['supported_backends']:
            assert 'name' in backend
            assert 'type' in backend

    def test_version_has_features_list(self, client):
        """Version endpoint must list features."""
        response = client.get('/api/extractor/version')
        data = response.get_json()
        assert 'features' in data
        assert isinstance(data['features'], list)
        assert len(data['features']) > 0

    def test_version_has_documentation_link(self, client):
        """Version endpoint should include a link to documentation."""
        response = client.get('/api/extractor/version')
        data = response.get_json()
        assert 'documentation' in data
        assert data['documentation'] == '/api/extractor/docs'


class TestExtractorDocs:
    """Tests for GET /api/extractor/docs"""

    def test_docs_returns_200(self, client):
        """Docs endpoint should return 200."""
        response = client.get('/api/extractor/docs')
        assert response.status_code == 200

    def test_docs_has_title(self, client):
        """Docs endpoint must include a title."""
        response = client.get('/api/extractor/docs')
        data = response.get_json()
        assert 'title' in data
        assert 'ForensicBridge' in data['title']

    def test_docs_has_version(self, client):
        """Docs endpoint must include version info."""
        response = client.get('/api/extractor/docs')
        data = response.get_json()
        assert 'version' in data

    def test_docs_has_endpoints(self, client):
        """Docs endpoint must list available API endpoints."""
        response = client.get('/api/extractor/docs')
        data = response.get_json()
        assert 'endpoints' in data
        assert isinstance(data['endpoints'], dict)
        assert len(data['endpoints']) > 0

    def test_docs_has_installation_steps(self, client):
        """Docs endpoint must include installation steps."""
        response = client.get('/api/extractor/docs')
        data = response.get_json()
        assert 'installation_steps' in data
        assert isinstance(data['installation_steps'], list)
        assert len(data['installation_steps']) > 0

    def test_docs_has_troubleshooting(self, client):
        """Docs endpoint must include troubleshooting info."""
        response = client.get('/api/extractor/docs')
        data = response.get_json()
        assert 'troubleshooting' in data
        assert isinstance(data['troubleshooting'], dict)


class TestExtractorSecurityInfo:
    """Tests for GET /api/extractor/security-info"""

    def test_security_info_returns_200(self, client):
        """Security info endpoint should return 200."""
        response = client.get('/api/extractor/security-info')
        assert response.status_code == 200

    def test_security_info_has_instructions(self, client):
        """Security info must include security instructions."""
        response = client.get('/api/extractor/security-info')
        data = response.get_json()
        assert 'security_instructions' in data
        assert isinstance(data['security_instructions'], dict)

    def test_security_info_has_success_flag(self, client):
        """Security info must include success flag."""
        response = client.get('/api/extractor/security-info')
        data = response.get_json()
        assert data.get('success') is True

    def test_security_info_has_version(self, client):
        """Security info must include version."""
        response = client.get('/api/extractor/security-info')
        data = response.get_json()
        assert 'version' in data

    def test_security_info_covers_smartscreen(self, client):
        """Security instructions must cover Windows SmartScreen warnings."""
        response = client.get('/api/extractor/security-info')
        data = response.get_json()
        instructions = data['security_instructions']
        assert 'smartscreen_warning' in instructions
        assert 'steps' in instructions['smartscreen_warning']

    def test_security_info_covers_browser_warning(self, client):
        """Security instructions must cover browser download warnings."""
        response = client.get('/api/extractor/security-info')
        data = response.get_json()
        instructions = data['security_instructions']
        assert 'browser_warning' in instructions
        assert 'steps' in instructions['browser_warning']

    def test_security_info_explains_why(self, client):
        """Security instructions should explain why warnings appear."""
        response = client.get('/api/extractor/security-info')
        data = response.get_json()
        instructions = data['security_instructions']
        assert 'why_warning' in instructions
        assert len(instructions['why_warning']) > 0


class TestExtractorHealth:
    """Tests for GET /api/extractor/health"""

    def test_health_returns_valid_status_code(self, client):
        """Health endpoint should return 200 (healthy) or 503 (unhealthy)."""
        response = client.get('/api/extractor/health')
        assert response.status_code in (200, 503)

    def test_health_has_healthy_field(self, client):
        """Health response must include 'healthy' boolean."""
        response = client.get('/api/extractor/health')
        data = response.get_json()
        assert 'healthy' in data
        assert isinstance(data['healthy'], bool)

    def test_health_has_version(self, client):
        """Health response must include version."""
        response = client.get('/api/extractor/health')
        data = response.get_json()
        assert 'version' in data

    def test_health_has_sources(self, client):
        """Health response must include source availability."""
        response = client.get('/api/extractor/health')
        data = response.get_json()
        assert 'sources' in data
        expected_keys = ['local', 'cache', 'github', 'bootstrap', 'zip_package']
        for key in expected_keys:
            assert key in data['sources'], f"Missing source '{key}' in health response"

    def test_health_status_code_matches_healthy_field(self, client):
        """Status code 200 should correspond to healthy=True, 503 to healthy=False."""
        response = client.get('/api/extractor/health')
        data = response.get_json()
        if data['healthy']:
            assert response.status_code == 200
        else:
            assert response.status_code == 503


class TestExtractorDownload:
    """Tests for GET /api/extractor/download"""

    def test_download_returns_response(self, client):
        """Download endpoint should return a file, redirect, or fallback script.
        In test environments without the actual exe/zip files, a fallback
        response (bootstrap or generated script) is expected."""
        response = client.get('/api/extractor/download')
        # Should be 200 (file/script) or 302 (redirect), never 500
        assert response.status_code in (200, 302), (
            f"Unexpected status {response.status_code}"
        )

    def test_download_format_bat(self, client):
        """Requesting format=bat should return a batch file or generated script."""
        response = client.get('/api/extractor/download?format=bat')
        assert response.status_code in (200, 302)

    def test_download_format_exe_without_file(self, client):
        """Requesting format=exe when no exe exists may redirect to GitHub
        or return a 404/fallback."""
        response = client.get('/api/extractor/download?format=exe')
        # 200 (file), 302 (redirect to GitHub), or 404 (not available)
        assert response.status_code in (200, 302, 404)


class TestExtractorZipInfo:
    """Tests for GET /api/extractor/zip/info"""

    def test_zip_info_returns_200(self, client):
        """Zip info endpoint should return 200."""
        response = client.get('/api/extractor/zip/info')
        assert response.status_code == 200

    def test_zip_info_has_available_field(self, client):
        """Zip info must indicate whether zip is available."""
        response = client.get('/api/extractor/zip/info')
        data = response.get_json()
        assert 'available' in data
        assert isinstance(data['available'], bool)

    def test_zip_info_structure_when_available(self, client):
        """If zip is available, response should include hash and size."""
        response = client.get('/api/extractor/zip/info')
        data = response.get_json()
        if data.get('available'):
            assert 'sha256' in data
            assert 'size' in data
            assert 'filename' in data
            assert 'download_url' in data
        else:
            # When not available, should have a message
            assert 'message' in data


class TestExtractorZipVerify:
    """Tests for POST /api/extractor/zip/verify"""

    def test_verify_missing_hash_returns_error(self, client):
        """Submitting an empty body should return 400 or 404."""
        response = client.post(
            '/api/extractor/zip/verify',
            json={},
            content_type='application/json'
        )
        # 400 if missing hash, 404 if zip not available
        assert response.status_code in (400, 404)

    def test_verify_no_sha256_field_returns_400(self, client):
        """Submitting body without sha256 should return 400 (if zip exists)
        or 404 (if zip not available)."""
        response = client.post(
            '/api/extractor/zip/verify',
            json={'wrong_field': 'abc'},
            content_type='application/json'
        )
        assert response.status_code in (400, 404)
        data = response.get_json()
        assert 'error' in data

    def test_verify_wrong_hash_returns_invalid(self, client):
        """Submitting a wrong hash should return valid=False (if zip exists)
        or 404 (if zip not available)."""
        response = client.post(
            '/api/extractor/zip/verify',
            json={'sha256': 'deadbeef' * 8},
            content_type='application/json'
        )
        data = response.get_json()
        if response.status_code == 200:
            assert data['valid'] is False
            assert 'mismatch' in data.get('message', '').lower() or not data['valid']
        elif response.status_code == 404:
            # Zip not available on this server
            assert 'error' in data
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")


class TestExtractorReleases:
    """Tests for GET /api/extractor/releases"""

    def test_releases_redirects_to_github(self, client):
        """Releases endpoint should redirect to GitHub releases page."""
        response = client.get('/api/extractor/releases')
        assert response.status_code == 302
        location = response.headers.get('Location', '')
        assert 'github.com' in location
        assert 'releases' in location

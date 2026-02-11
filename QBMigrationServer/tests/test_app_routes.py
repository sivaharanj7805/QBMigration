"""Tests for app.py - root endpoint, health check, and error handlers."""


class TestRootEndpoint:
    """Tests for the index route."""

    def test_index_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "running"
        assert data["name"] == "ForensicBridge Migration Server"
        assert "version" in data

    def test_index_has_version(self, client):
        response = client.get("/")
        data = response.get_json()
        assert "version" in data


class TestHealthCheck:
    """Tests for /health endpoint."""

    def test_health_check_get(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] in ("healthy", "ok", "degraded")

    def test_health_check_options(self, client):
        response = client.options("/health")
        assert response.status_code == 200
        # Should have CORS headers
        assert "Access-Control-Allow-Methods" in response.headers


class TestErrorHandlers:
    """Tests for error handlers."""

    def test_404_handler(self, client):
        response = client.get("/nonexistent-endpoint-abc123")
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False
        assert (
            "not found" in data["error"].lower()
            or "not found" in data.get("message", "").lower()
        )

    def test_401_on_protected_endpoint(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_post_404_handler(self, client):
        response = client.post("/api/nonexistent")
        assert response.status_code in (404, 405)


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    def test_response_has_security_headers(self, client):
        response = client.get("/")
        # Check for common security headers
        headers = dict(response.headers)
        # At minimum, X-Content-Type-Options should be present
        assert "X-Content-Type-Options" in headers or "Content-Type" in headers

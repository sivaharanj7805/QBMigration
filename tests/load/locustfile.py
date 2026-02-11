"""
QBMigration Load Testing with Locust
=====================================

Simulates realistic user traffic patterns against the QBMigration API.

Usage:
    pip install locust
    locust -f tests/load/locustfile.py --host=http://localhost:5000

    # Headless mode (CI):
    locust -f tests/load/locustfile.py --host=http://localhost:5000 \
        --headless -u 50 -r 5 --run-time 2m

Environment variables:
    LOAD_TEST_EMAIL     Test user email (default: loadtest@example.com)
    LOAD_TEST_PASSWORD  Test user password (default: LoadTest123!@#)
"""

import os
import random
import string

from locust import HttpUser, between, task


class QBMigrationUser(HttpUser):
    """Simulates a typical QBMigration user session."""

    wait_time = between(1, 5)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = None
        self.email = os.getenv("LOAD_TEST_EMAIL", "loadtest@example.com")
        self.password = os.getenv("LOAD_TEST_PASSWORD", "LoadTest123!@#")

    def on_start(self):
        """Login and obtain JWT token at the start of each user session."""
        response = self.client.post(
            "/api/auth/login",
            json={"email": self.email, "password": self.password},
            name="/api/auth/login",
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("token") or data.get("access_token")
        else:
            # Try registering if login fails (first run)
            reg_response = self.client.post(
                "/api/auth/register",
                json={
                    "email": self.email,
                    "password": self.password,
                    "first_name": "Load",
                    "last_name": "Tester",
                    "company_name": "Load Test Corp",
                },
                name="/api/auth/register",
            )
            if reg_response.status_code in (200, 201):
                data = reg_response.json()
                self.token = data.get("token") or data.get("access_token")

    @property
    def auth_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # -----------------------------------------------------------------------
    # Health checks (high frequency — simulates monitoring)
    # -----------------------------------------------------------------------
    @task(10)
    def health_check(self):
        self.client.get("/health", name="/health")

    @task(3)
    def api_health(self):
        self.client.get("/api/health", name="/api/health")

    # -----------------------------------------------------------------------
    # Auth endpoints
    # -----------------------------------------------------------------------
    @task(5)
    def get_current_user(self):
        self.client.get(
            "/api/auth/me",
            headers=self.auth_headers,
            name="/api/auth/me",
        )

    @task(2)
    def get_team(self):
        self.client.get(
            "/api/auth/team",
            headers=self.auth_headers,
            name="/api/auth/team",
        )

    # -----------------------------------------------------------------------
    # Dashboard / project endpoints
    # -----------------------------------------------------------------------
    @task(5)
    def list_migrations(self):
        self.client.get(
            "/api/migrations",
            headers=self.auth_headers,
            name="/api/migrations",
        )

    @task(3)
    def list_projects(self):
        self.client.get(
            "/api/projects",
            headers=self.auth_headers,
            name="/api/projects",
        )

    @task(2)
    def dashboard_stats(self):
        self.client.get(
            "/api/dashboard/stats",
            headers=self.auth_headers,
            name="/api/dashboard/stats",
        )

    # -----------------------------------------------------------------------
    # Webhook health (public endpoint)
    # -----------------------------------------------------------------------
    @task(1)
    def webhook_health(self):
        self.client.get("/api/webhooks/health", name="/api/webhooks/health")


class AnonymousUser(HttpUser):
    """Simulates unauthenticated traffic (bots, crawlers, health checks)."""

    wait_time = between(2, 10)
    weight = 2  # Lower proportion than authenticated users

    @task(10)
    def health_check(self):
        self.client.get("/health", name="/health [anon]")

    @task(5)
    def root_endpoint(self):
        self.client.get("/", name="/ [anon]")

    @task(2)
    def login_attempt(self):
        """Simulate failed login attempts (rate limit testing)."""
        self.client.post(
            "/api/auth/login",
            json={
                "email": f"random_{random.randint(1, 9999)}@example.com",
                "password": "wrong_password",
            },
            name="/api/auth/login [bad]",
        )

    @task(1)
    def not_found(self):
        """Simulate 404 traffic."""
        rand_path = "".join(random.choices(string.ascii_lowercase, k=8))
        self.client.get(f"/api/{rand_path}", name="/api/[random-404]")

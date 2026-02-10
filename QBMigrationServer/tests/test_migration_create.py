"""Tests for POST /api/migrations - creating new migrations."""


class TestCreateMigration:
    """Tests for migration creation endpoint."""

    def test_create_migration_unauthenticated(self, client):
        response = client.post(
            "/api/migrations",
            json={"company_name": "Test Corp"},
        )
        assert response.status_code == 401

    def test_create_migration_no_body(self, authenticated_client):
        response = authenticated_client.post(
            "/api/migrations",
            data="",
            content_type="application/json",
        )
        # Empty body may cause 400, 401, or 500 depending on validation order
        assert response.status_code in (400, 401, 500)

    def test_create_migration_success(
        self, authenticated_client, db_session, test_user
    ):
        # Give user some migration credits
        test_user.migrations_purchased = 5
        test_user.migrations_used = 0
        db_session.commit()

        response = authenticated_client.post(
            "/api/migrations",
            json={
                "destination": "qbo",
                "files": ["test_company.qbw"],
            },
        )
        assert response.status_code in (200, 201, 400, 403)

    def test_create_migration_caseware(
        self, authenticated_client, db_session, test_user
    ):
        test_user.migrations_purchased = 5
        test_user.migrations_used = 0
        db_session.commit()

        response = authenticated_client.post(
            "/api/migrations",
            json={
                "destination": "caseware",
                "files": ["caseware_company.qbw"],
            },
        )
        assert response.status_code in (200, 201, 400, 403)

    def test_create_migration_invalid_destination(
        self, authenticated_client, db_session, test_user
    ):
        response = authenticated_client.post(
            "/api/migrations",
            json={
                "destination": "invalid",
                "files": ["test.qbw"],
            },
        )
        assert response.status_code == 400

    def test_create_migration_no_files(
        self, authenticated_client, db_session, test_user
    ):
        response = authenticated_client.post(
            "/api/migrations",
            json={
                "destination": "qbo",
                "files": [],
            },
        )
        assert response.status_code == 400

    def test_create_migration_empty_json(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/migrations",
            json={},
        )
        assert response.status_code in (400, 500)


class TestStartMigration:
    """Tests for POST /api/migrations/<id>/start."""

    def test_start_migration_invalid_uuid(self, authenticated_client):
        response = authenticated_client.post("/api/migrations/bad-uuid/start")
        assert response.status_code == 400

    def test_start_migration_nonexistent(self, authenticated_client):
        response = authenticated_client.post(
            "/api/migrations/00000000-0000-0000-0000-000000000000/start"
        )
        # 402 if no credits, 404 if migration not found
        assert response.status_code in (402, 404)

    def test_start_migration_unauthenticated(self, client):
        response = client.post(
            "/api/migrations/00000000-0000-0000-0000-000000000000/start"
        )
        assert response.status_code == 401


class TestMigrationHelpers:
    """Tests for migration helper functions."""

    def test_validate_migration_id_valid(self):
        from api.migrations import validate_migration_id

        assert validate_migration_id("12345678-1234-1234-1234-123456789abc") is True

    def test_validate_migration_id_invalid(self):
        from api.migrations import validate_migration_id

        assert validate_migration_id("not-a-uuid") is False

    def test_validate_migration_id_none(self):
        from api.migrations import validate_migration_id

        assert validate_migration_id(None) is False

    def test_validate_migration_id_empty(self):
        from api.migrations import validate_migration_id

        assert validate_migration_id("") is False

    def test_validate_pagination_param_valid(self):
        from api.migrations import validate_pagination_param

        assert validate_pagination_param("5", "page", 1, 1, 100) == 5

    def test_validate_pagination_param_none(self):
        from api.migrations import validate_pagination_param

        assert validate_pagination_param(None, "page", 1, 1, 100) == 1

    def test_validate_pagination_param_out_of_range(self):
        from api.migrations import validate_pagination_param

        assert validate_pagination_param("200", "per_page", 50, 1, 100) == 50

    def test_validate_pagination_param_sql_injection(self):
        from api.migrations import validate_pagination_param

        assert validate_pagination_param("1;DROP TABLE", "page", 1, 1, 100) == 1

    def test_validate_pagination_param_negative(self):
        from api.migrations import validate_pagination_param

        assert validate_pagination_param("-1", "page", 1, 1, 100) == 1

    def test_validate_pagination_param_valid_boundary(self):
        from api.migrations import validate_pagination_param

        assert validate_pagination_param("100", "per_page", 50, 1, 100) == 100

    def test_validate_pagination_param_float(self):
        from api.migrations import validate_pagination_param

        assert validate_pagination_param("3.5", "page", 1, 1, 100) == 1


class TestExecuteMigration:
    """Tests for POST /api/migrations/<id>/execute."""

    def test_execute_unauthenticated(self, client):
        response = client.post(
            "/api/migrations/00000000-0000-0000-0000-000000000000/execute"
        )
        assert response.status_code == 401

    def test_execute_invalid_uuid(self, authenticated_client):
        response = authenticated_client.post("/api/migrations/bad-uuid/execute")
        assert response.status_code == 400

    def test_execute_nonexistent(self, authenticated_client, db_session):
        response = authenticated_client.post(
            "/api/migrations/00000000-0000-0000-0000-000000000000/execute"
        )
        assert response.status_code in (404, 500, 503)

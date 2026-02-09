"""
Projects API Test Suite
Tests for project CRUD endpoints.

Endpoints tested:
- GET    /api/projects          - List user projects
- POST   /api/projects          - Create project (requires paid credit)
- GET    /api/projects/<id>     - Get project details
- PUT    /api/projects/<id>     - Update project
- DELETE /api/projects/<id>     - Delete project
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.migration import Migration  # noqa: E402
from models.migration_credit import MigrationCredit  # noqa: E402
from models.project import Project  # noqa: E402
from models.user import User  # noqa: E402

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def paid_credit(db_session, test_user):
    """Create a paid, available MigrationCredit for the test user."""
    credit = MigrationCredit(
        user_id=test_user.id,
        tier_type="starter",
        transaction_limit=5000,
        price_cents=49700,
        status="available",
        payment_status="paid",
        stripe_checkout_session_id="test_session_123",
    )
    credit.paid_at = datetime.now(timezone.utc)
    db_session.add(credit)
    db_session.commit()
    db_session.refresh(credit)
    return credit


@pytest.fixture
def sample_project(db_session, test_user, paid_credit):
    """Create a sample project linked to a paid credit."""
    project = Project(
        user_id=test_user.id,
        name="Test Project",
        client_name="Test Client",
        client_email="client@example.com",
        notes="Test notes",
        migration_credit_id=paid_credit.id,
        tier_type=paid_credit.tier_type,
        transaction_limit=paid_credit.transaction_limit,
        transactions_used=0,
        status="active",
    )
    db_session.add(project)

    # Mark credit as used
    paid_credit.status = "used"
    paid_credit.used_at = datetime.now(timezone.utc)

    db_session.commit()
    db_session.refresh(project)
    return project


# ============================================================================
# List Projects - GET /api/projects
# ============================================================================


class TestListProjects:
    """Tests for GET /api/projects"""

    def test_list_projects_requires_auth(self, client, app):
        """Listing projects requires authentication."""
        response = client.get("/api/projects")
        assert response.status_code == 401

    def test_list_projects_empty(self, authenticated_client, db_session, test_user):
        """Authenticated user with no projects gets an empty list."""
        response = authenticated_client.get("/api/projects")
        assert response.status_code == 200
        data = response.get_json()
        assert "projects" in data
        assert isinstance(data["projects"], list)
        assert len(data["projects"]) == 0

    def test_list_projects_returns_user_projects(self, authenticated_client, db_session, test_user, sample_project):
        """Authenticated user sees their own projects."""
        response = authenticated_client.get("/api/projects")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["projects"]) == 1
        project = data["projects"][0]
        assert project["name"] == "Test Project"
        assert project["client_name"] == "Test Client"
        assert project["status"] == "active"

    def test_list_projects_has_required_fields(self, authenticated_client, db_session, test_user, sample_project):
        """Each project in the list has all required fields."""
        response = authenticated_client.get("/api/projects")
        data = response.get_json()
        project = data["projects"][0]
        for field in [
            "id",
            "name",
            "client_name",
            "status",
            "session_id",
            "tier_type",
            "tier_name",
            "transaction_limit",
            "transactions_used",
            "created_at",
        ]:
            assert field in project, f"Missing field: {field}"

    def test_list_projects_does_not_show_other_users(self, authenticated_client, db_session, test_user, sample_project):
        """User cannot see projects belonging to another user."""
        # Create another user and project
        other_user = User(
            email="other@example.com",
            first_name="Other",
            last_name="User",
            company_name="Other Co",
        )
        other_user.set_password("OtherPassword1234!")
        db_session.add(other_user)
        db_session.commit()

        other_credit = MigrationCredit(
            user_id=other_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            status="used",
            payment_status="paid",
            stripe_checkout_session_id="other_session_456",
        )
        db_session.add(other_credit)
        db_session.commit()

        other_project = Project(
            user_id=other_user.id,
            name="Other Project",
            client_name="Other Client",
            migration_credit_id=other_credit.id,
            tier_type="starter",
            transaction_limit=5000,
            status="active",
        )
        db_session.add(other_project)
        db_session.commit()

        # Authenticated user should only see their own project
        response = authenticated_client.get("/api/projects")
        data = response.get_json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "Test Project"


# ============================================================================
# Create Project - POST /api/projects
# ============================================================================


class TestCreateProject:
    """Tests for POST /api/projects"""

    def test_create_project_requires_auth(self, client, app):
        """Creating a project requires authentication."""
        response = client.post("/api/projects", json={"name": "New Project", "client_name": "New Client"})
        assert response.status_code == 401

    def test_create_project_success(self, authenticated_client, db_session, test_user, paid_credit):
        """Creating a project with a valid credit succeeds."""
        response = authenticated_client.post(
            "/api/projects", json={"name": "My New Project", "client_name": "My Client"}
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["success"] is True
        assert "project" in data
        assert data["project"]["name"] == "My New Project"
        assert data["project"]["client_name"] == "My Client"
        assert data["project"]["status"] == "active"
        assert "session_id" in data["project"]

    def test_create_project_consumes_credit(self, authenticated_client, db_session, test_user, paid_credit):
        """Creating a project marks the credit as used."""
        credit_id = paid_credit.id
        authenticated_client.post("/api/projects", json={"name": "Credit Test", "client_name": "Client"})
        db_session.expire_all()
        credit = db_session.get(MigrationCredit, credit_id)
        assert credit.status == "used"

    def test_create_project_no_credit_available(self, authenticated_client, db_session, test_user):
        """Creating a project without available credits returns 403."""
        response = authenticated_client.post(
            "/api/projects", json={"name": "No Credit Project", "client_name": "Client"}
        )
        assert response.status_code == 403
        data = response.get_json()
        assert "error" in data
        assert data.get("purchase_required") is True

    def test_create_project_missing_name(self, authenticated_client, db_session, test_user, paid_credit):
        """Creating a project without a name returns 400."""
        response = authenticated_client.post("/api/projects", json={"client_name": "Client"})
        assert response.status_code == 400

    def test_create_project_missing_client_name(self, authenticated_client, db_session, test_user, paid_credit):
        """Creating a project without a client name returns 400."""
        response = authenticated_client.post("/api/projects", json={"name": "Project"})
        assert response.status_code == 400

    def test_create_project_no_body(self, authenticated_client, db_session, test_user):
        """Creating a project with no body returns error."""
        response = authenticated_client.post("/api/projects", data="", content_type="application/json")
        # Empty body causes BadRequest during auth token parsing, resulting in 401
        assert response.status_code in (400, 401)

    def test_create_project_with_specific_credit(self, authenticated_client, db_session, test_user, paid_credit):
        """Creating a project with a specific credit_id uses that credit."""
        response = authenticated_client.post(
            "/api/projects",
            json={
                "name": "Specific Credit Project",
                "client_name": "Client",
                "credit_id": paid_credit.id,
            },
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["project"]["tier_type"] == "starter"

    def test_create_project_with_optional_fields(self, authenticated_client, db_session, test_user, paid_credit):
        """Creating a project with optional fields stores them."""
        response = authenticated_client.post(
            "/api/projects",
            json={
                "name": "Full Project",
                "client_name": "Full Client",
                "client_email": "fullclient@example.com",
                "notes": "Some notes here",
            },
        )
        assert response.status_code == 201

        # Verify the project was stored
        project = Project.query.filter_by(name="Full Project").first()
        assert project is not None
        assert project.client_email == "fullclient@example.com"
        assert project.notes == "Some notes here"

    def test_create_project_inherits_tier_from_credit(self, authenticated_client, db_session, test_user):
        """Project tier matches the credit's tier type."""
        business_credit = MigrationCredit(
            user_id=test_user.id,
            tier_type="business",
            transaction_limit=25000,
            price_cents=99700,
            status="available",
            payment_status="paid",
            stripe_checkout_session_id="biz_session_789",
        )
        business_credit.paid_at = datetime.now(timezone.utc)
        db_session.add(business_credit)
        db_session.commit()

        response = authenticated_client.post(
            "/api/projects",
            json={"name": "Business Project", "client_name": "Biz Client"},
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["project"]["tier_type"] == "business"
        assert data["project"]["transaction_limit"] == 25000


# ============================================================================
# Get Project - GET /api/projects/<id>
# ============================================================================


class TestGetProject:
    """Tests for GET /api/projects/<id>"""

    def test_get_project_requires_auth(self, client, app):
        """Getting a project requires authentication."""
        response = client.get("/api/projects/1")
        assert response.status_code == 401

    def test_get_project_success(self, authenticated_client, db_session, test_user, sample_project):
        """Getting an existing project returns its details."""
        response = authenticated_client.get(f"/api/projects/{sample_project.id}")
        assert response.status_code == 200
        data = response.get_json()
        assert "project" in data
        project = data["project"]
        assert project["id"] == sample_project.id
        assert project["name"] == "Test Project"
        assert project["client_name"] == "Test Client"
        assert project["client_email"] == "client@example.com"
        assert project["notes"] == "Test notes"

    def test_get_project_includes_tier_info(self, authenticated_client, db_session, test_user, sample_project):
        """Project details include tier and transaction info."""
        response = authenticated_client.get(f"/api/projects/{sample_project.id}")
        data = response.get_json()
        project = data["project"]
        assert "tier_type" in project
        assert "tier_name" in project
        assert "transaction_limit" in project
        assert "transactions_used" in project
        assert "transactions_remaining" in project

    def test_get_project_not_found(self, authenticated_client, db_session, test_user):
        """Getting a nonexistent project returns 404."""
        response = authenticated_client.get("/api/projects/99999")
        assert response.status_code == 404

    def test_get_project_other_user(self, authenticated_client, db_session, test_user):
        """Cannot get another user's project (returns 404)."""
        other_user = User(
            email="other2@example.com",
            first_name="Other",
            last_name="Person",
            company_name="Other Co",
        )
        other_user.set_password("OtherPassword1234!")
        db_session.add(other_user)
        db_session.commit()

        other_credit = MigrationCredit(
            user_id=other_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            status="used",
            payment_status="paid",
            stripe_checkout_session_id="other2_session",
        )
        db_session.add(other_credit)
        db_session.commit()

        other_project = Project(
            user_id=other_user.id,
            name="Secret Project",
            client_name="Secret Client",
            migration_credit_id=other_credit.id,
            tier_type="starter",
            transaction_limit=5000,
            status="active",
        )
        db_session.add(other_project)
        db_session.commit()

        response = authenticated_client.get(f"/api/projects/{other_project.id}")
        assert response.status_code == 404

    def test_get_project_includes_migrations(self, authenticated_client, db_session, test_user, sample_project):
        """Project details include a migrations list."""
        response = authenticated_client.get(f"/api/projects/{sample_project.id}")
        data = response.get_json()
        assert "migrations" in data
        assert isinstance(data["migrations"], list)

    def test_get_project_shows_linked_migrations(self, authenticated_client, db_session, test_user, sample_project):
        """Migrations linked by session_id appear in project details."""
        migration = Migration(
            migration_id="linked-migration-001",
            user_id=test_user.id,
            session_id=sample_project.session_id,
            company_name="Linked Company",
            status="completed",
            progress_percent=100,
        )
        db_session.add(migration)
        db_session.commit()

        response = authenticated_client.get(f"/api/projects/{sample_project.id}")
        data = response.get_json()
        assert len(data["migrations"]) == 1
        assert data["migrations"][0]["id"] is not None
        assert data["migrations"][0]["status"] == "completed"


# ============================================================================
# Update Project - PUT /api/projects/<id>
# ============================================================================


class TestUpdateProject:
    """Tests for PUT /api/projects/<id>"""

    def test_update_project_requires_auth(self, client, app):
        """Updating a project requires authentication."""
        response = client.put("/api/projects/1", json={"name": "Updated"})
        assert response.status_code == 401

    def test_update_project_name(self, authenticated_client, db_session, test_user, sample_project):
        """Updating the project name succeeds."""
        response = authenticated_client.put(f"/api/projects/{sample_project.id}", json={"name": "Updated Name"})
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        db_session.refresh(sample_project)
        assert sample_project.name == "Updated Name"

    def test_update_project_client_name(self, authenticated_client, db_session, test_user, sample_project):
        """Updating the client name succeeds."""
        response = authenticated_client.put(
            f"/api/projects/{sample_project.id}",
            json={"client_name": "New Client Name"},
        )
        assert response.status_code == 200

        db_session.refresh(sample_project)
        assert sample_project.client_name == "New Client Name"

    def test_update_project_multiple_fields(self, authenticated_client, db_session, test_user, sample_project):
        """Updating multiple fields at once succeeds."""
        response = authenticated_client.put(
            f"/api/projects/{sample_project.id}",
            json={
                "name": "Multi Update",
                "client_name": "Multi Client",
                "client_email": "multi@example.com",
                "notes": "Updated notes",
            },
        )
        assert response.status_code == 200

        db_session.refresh(sample_project)
        assert sample_project.name == "Multi Update"
        assert sample_project.client_name == "Multi Client"
        assert sample_project.client_email == "multi@example.com"
        assert sample_project.notes == "Updated notes"

    def test_update_project_not_found(self, authenticated_client, db_session, test_user):
        """Updating a nonexistent project returns 404."""
        response = authenticated_client.put("/api/projects/99999", json={"name": "Nope"})
        assert response.status_code == 404

    def test_update_project_other_user(self, authenticated_client, db_session, test_user):
        """Cannot update another user's project."""
        other_user = User(
            email="other3@example.com",
            first_name="Other",
            last_name="Three",
            company_name="Other Co",
        )
        other_user.set_password("OtherPassword1234!")
        db_session.add(other_user)
        db_session.commit()

        other_credit = MigrationCredit(
            user_id=other_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            status="used",
            payment_status="paid",
            stripe_checkout_session_id="other3_session",
        )
        db_session.add(other_credit)
        db_session.commit()

        other_project = Project(
            user_id=other_user.id,
            name="Other Project",
            client_name="Other Client",
            migration_credit_id=other_credit.id,
            tier_type="starter",
            transaction_limit=5000,
            status="active",
        )
        db_session.add(other_project)
        db_session.commit()

        response = authenticated_client.put(f"/api/projects/{other_project.id}", json={"name": "Hacked Name"})
        assert response.status_code == 404


# ============================================================================
# Delete Project - DELETE /api/projects/<id>
# ============================================================================


class TestDeleteProject:
    """Tests for DELETE /api/projects/<id>"""

    def test_delete_project_requires_auth(self, client, app):
        """Deleting a project requires authentication."""
        response = client.delete("/api/projects/1")
        assert response.status_code == 401

    def test_delete_project_success(self, authenticated_client, db_session, test_user, sample_project):
        """Deleting an existing project succeeds."""
        project_id = sample_project.id
        response = authenticated_client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Verify it was deleted
        project = db_session.get(Project, project_id)
        assert project is None

    def test_delete_project_not_found(self, authenticated_client, db_session, test_user):
        """Deleting a nonexistent project returns 404."""
        response = authenticated_client.delete("/api/projects/99999")
        assert response.status_code == 404

    def test_delete_project_other_user(self, authenticated_client, db_session, test_user):
        """Cannot delete another user's project."""
        other_user = User(
            email="other4@example.com",
            first_name="Other",
            last_name="Four",
            company_name="Other Co",
        )
        other_user.set_password("OtherPassword1234!")
        db_session.add(other_user)
        db_session.commit()

        other_credit = MigrationCredit(
            user_id=other_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            status="used",
            payment_status="paid",
            stripe_checkout_session_id="other4_session",
        )
        db_session.add(other_credit)
        db_session.commit()

        other_project = Project(
            user_id=other_user.id,
            name="Protected Project",
            client_name="Protected Client",
            migration_credit_id=other_credit.id,
            tier_type="starter",
            transaction_limit=5000,
            status="active",
        )
        db_session.add(other_project)
        db_session.commit()

        response = authenticated_client.delete(f"/api/projects/{other_project.id}")
        assert response.status_code == 404

    def test_delete_project_blocked_by_active_migration(
        self, authenticated_client, db_session, test_user, sample_project
    ):
        """Cannot delete a project with active migrations."""
        # Create an active migration linked to the project
        migration = Migration(
            migration_id="active-migration-001",
            user_id=test_user.id,
            session_id=sample_project.session_id,
            company_name="Active Company",
            status="processing",
            progress_percent=50,
        )
        db_session.add(migration)
        db_session.commit()

        response = authenticated_client.delete(f"/api/projects/{sample_project.id}")
        assert response.status_code == 400
        data = response.get_json()
        assert "active migrations" in data["error"].lower()

    def test_delete_project_allowed_with_completed_migration(
        self, authenticated_client, db_session, test_user, sample_project
    ):
        """Deleting is allowed if all migrations are completed (not active)."""
        migration = Migration(
            migration_id="done-migration-001",
            user_id=test_user.id,
            session_id=sample_project.session_id,
            company_name="Done Company",
            status="completed",
            progress_percent=100,
        )
        db_session.add(migration)
        db_session.commit()

        response = authenticated_client.delete(f"/api/projects/{sample_project.id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_delete_project_blocked_by_uploading_migration(
        self, authenticated_client, db_session, test_user, sample_project
    ):
        """Cannot delete a project with an uploading migration."""
        migration = Migration(
            migration_id="uploading-migration-001",
            user_id=test_user.id,
            session_id=sample_project.session_id,
            company_name="Uploading Company",
            status="uploading",
            progress_percent=10,
        )
        db_session.add(migration)
        db_session.commit()

        response = authenticated_client.delete(f"/api/projects/{sample_project.id}")
        assert response.status_code == 400

    def test_delete_project_blocked_by_migrating_migration(
        self, authenticated_client, db_session, test_user, sample_project
    ):
        """Cannot delete a project with a migrating migration."""
        migration = Migration(
            migration_id="migrating-migration-001",
            user_id=test_user.id,
            session_id=sample_project.session_id,
            company_name="Migrating Company",
            status="migrating",
            progress_percent=75,
        )
        db_session.add(migration)
        db_session.commit()

        response = authenticated_client.delete(f"/api/projects/{sample_project.id}")
        assert response.status_code == 400


# ============================================================================
# Download Extractor - GET /api/projects/<id>/download-extractor
# ============================================================================


class TestDownloadExtractor:
    """Tests for GET /api/projects/<id>/download-extractor"""

    def test_download_extractor_requires_auth(self, client, app):
        """Downloading extractor requires authentication."""
        response = client.get("/api/projects/1/download-extractor")
        assert response.status_code == 401

    def test_download_extractor_success(self, authenticated_client, db_session, test_user, sample_project):
        """Getting extractor download info for owned project succeeds."""
        response = authenticated_client.get(f"/api/projects/{sample_project.id}/download-extractor")
        assert response.status_code == 200
        data = response.get_json()
        assert "download_url" in data
        assert "session_id" in data
        assert data["session_id"] == sample_project.session_id
        assert "instructions" in data
        assert "security_note" in data
        assert "security_info_url" in data

    def test_download_extractor_not_found(self, authenticated_client, db_session, test_user):
        """Getting extractor for nonexistent project returns 404."""
        response = authenticated_client.get("/api/projects/99999/download-extractor")
        assert response.status_code == 404

    def test_download_extractor_other_user(self, authenticated_client, db_session, test_user):
        """Cannot get extractor for another user's project."""
        other_user = User(
            email="other5@example.com",
            first_name="Other",
            last_name="Five",
            company_name="Other Co",
        )
        other_user.set_password("OtherPassword1234!")
        db_session.add(other_user)
        db_session.commit()

        other_credit = MigrationCredit(
            user_id=other_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            status="used",
            payment_status="paid",
            stripe_checkout_session_id="other5_session",
        )
        db_session.add(other_credit)
        db_session.commit()

        other_project = Project(
            user_id=other_user.id,
            name="Other Extractor Project",
            client_name="Other Client",
            migration_credit_id=other_credit.id,
            tier_type="starter",
            transaction_limit=5000,
            status="active",
        )
        db_session.add(other_project)
        db_session.commit()

        response = authenticated_client.get(f"/api/projects/{other_project.id}/download-extractor")
        assert response.status_code == 404

    def test_download_extractor_instructions_contain_session_id(
        self, authenticated_client, db_session, test_user, sample_project
    ):
        """Instructions include the project's session ID."""
        response = authenticated_client.get(f"/api/projects/{sample_project.id}/download-extractor")
        data = response.get_json()
        assert sample_project.session_id in data["instructions"]


# ============================================================================
# Edge Cases - Additional coverage tests
# ============================================================================


class TestProjectEdgeCases:
    """Edge case tests for improved coverage."""

    def test_update_sets_updated_at(self, authenticated_client, db_session, test_user, sample_project):
        """Updating a project updates the updated_at timestamp."""
        original_updated_at = sample_project.updated_at
        authenticated_client.put(f"/api/projects/{sample_project.id}", json={"name": "Timestamped"})
        db_session.refresh(sample_project)
        assert sample_project.updated_at is not None
        if original_updated_at is not None:
            assert sample_project.updated_at >= original_updated_at

    def test_get_project_updated_at_in_response(self, authenticated_client, db_session, test_user, sample_project):
        """GET project includes updated_at (null if never updated)."""
        response = authenticated_client.get(f"/api/projects/{sample_project.id}")
        data = response.get_json()
        project = data["project"]
        assert "updated_at" in project

    def test_create_project_empty_strings(self, authenticated_client, db_session, test_user, paid_credit):
        """Creating a project with empty-string name/client_name returns 400."""
        response = authenticated_client.post("/api/projects", json={"name": "  ", "client_name": "  "})
        assert response.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

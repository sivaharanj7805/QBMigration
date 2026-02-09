"""Tests for models/project.py - Project model methods."""

from models.project import Project


class TestProjectTransactions:
    """Tests for Project transaction tracking methods."""

    def test_can_extract_positive(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
            tier_type="starter",
            transaction_limit=5000,
            transactions_used=0,
        )
        db_session.add(project)
        db_session.commit()
        assert project.can_extract_transactions(100) is True

    def test_can_extract_exceeds_limit(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
            transaction_limit=5000,
            transactions_used=4900,
        )
        db_session.add(project)
        db_session.commit()
        assert project.can_extract_transactions(200) is False

    def test_can_extract_unlimited(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
            tier_type="forensic",
            transaction_limit=-1,
        )
        db_session.add(project)
        db_session.commit()
        assert project.can_extract_transactions(999999) is True

    def test_can_extract_negative_count(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
        )
        db_session.add(project)
        db_session.commit()
        assert project.can_extract_transactions(-1) is False

    def test_get_remaining_transactions(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
            transaction_limit=5000,
            transactions_used=1500,
        )
        db_session.add(project)
        db_session.commit()
        assert project.get_remaining_transactions() == 3500

    def test_get_remaining_unlimited(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
            transaction_limit=-1,
        )
        db_session.add(project)
        db_session.commit()
        assert project.get_remaining_transactions() == -1

    def test_record_transactions_success(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
            transaction_limit=5000,
        )
        db_session.add(project)
        db_session.commit()
        assert project.record_transactions(100) is True
        assert project.transactions_used == 100

    def test_record_transactions_exceeds(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
            transaction_limit=100,
            transactions_used=90,
        )
        db_session.add(project)
        db_session.commit()
        assert project.record_transactions(50) is False

    def test_get_tier_name(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test",
            client_name="Client",
            tier_type="enterprise",
        )
        db_session.add(project)
        db_session.commit()
        assert project.get_tier_name() == "Enterprise"

    def test_to_dict(self, db_session, test_user):
        project = Project(
            user_id=test_user.id,
            name="Test Project",
            client_name="Test Client",
        )
        db_session.add(project)
        db_session.commit()
        d = project.to_dict()
        assert d["name"] == "Test Project"
        assert d["client_name"] == "Test Client"
        assert "session_id" in d
        assert "tier_name" in d

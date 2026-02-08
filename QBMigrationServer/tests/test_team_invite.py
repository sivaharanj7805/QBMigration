"""Tests for models/team_invite.py - TeamInvite model."""

from datetime import datetime, timedelta, timezone

from models.team_invite import TeamInvite


class TestTeamInviteCreate:
    """Tests for TeamInvite.create_invite class method."""

    def test_create_invite(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="team@example.com",
            role="member",
        )
        assert invite.id is not None
        assert invite.email == "team@example.com"
        assert invite.role == "member"
        assert invite.status == "pending"
        assert invite.invite_token is not None
        assert len(invite.invite_token) > 20

    def test_create_invite_admin_role(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="admin@example.com",
            role="admin",
        )
        assert invite.role == "admin"

    def test_create_invite_email_normalized(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="  Team@Example.COM  ",
        )
        assert invite.email == "team@example.com"

    def test_create_invite_with_expiry(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="test@example.com",
            expiry_days=14,
        )
        expected_expiry = datetime.now(timezone.utc) + timedelta(days=14)
        assert abs((invite.expires_at - expected_expiry).total_seconds()) < 5

    def test_create_invite_unique_tokens(self, db_session, test_user):
        invite1 = TeamInvite.create_invite(
            owner_user_id=test_user.id, email="a@test.com"
        )
        invite2 = TeamInvite.create_invite(
            owner_user_id=test_user.id, email="b@test.com"
        )
        assert invite1.invite_token != invite2.invite_token


class TestTeamInviteAccept:
    """Tests for TeamInvite accept/cancel methods."""

    def test_accept_invite(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="joiner@example.com",
        )
        success, msg = invite.accept(test_user.id)
        assert success is True
        assert invite.status == "accepted"
        assert invite.accepted_user_id == test_user.id

    def test_accept_already_accepted(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="joiner@example.com",
        )
        invite.accept(test_user.id)
        success, msg = invite.accept(test_user.id)
        assert success is False
        assert "no longer valid" in msg.lower()

    def test_accept_expired_invite(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="joiner@example.com",
            expiry_days=0,
        )
        # Set expires_at in the past
        invite.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        success, msg = invite.accept(test_user.id)
        assert success is False
        assert "expired" in msg.lower()

    def test_cancel_invite(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="joiner@example.com",
        )
        invite.cancel()
        assert invite.status == "cancelled"


class TestTeamInviteQueries:
    """Tests for TeamInvite query class methods."""

    def test_find_by_token(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="find@example.com",
        )
        found = TeamInvite.find_by_token(invite.invite_token)
        assert found is not None
        assert found.id == invite.id

    def test_find_by_token_not_found(self, db_session):
        found = TeamInvite.find_by_token("nonexistent_token")
        assert found is None

    def test_get_pending_for_owner(self, db_session, test_user):
        TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="pending@example.com",
        )
        pending = TeamInvite.get_pending_for_owner(test_user.id)
        assert len(pending) >= 1

    def test_cleanup_expired(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="expired@example.com",
        )
        invite.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.commit()

        count = TeamInvite.cleanup_expired()
        assert count >= 1

        db_session.refresh(invite)
        assert invite.status == "expired"


class TestTeamInviteToDict:
    """Tests for TeamInvite.to_dict method."""

    def test_to_dict(self, db_session, test_user):
        invite = TeamInvite.create_invite(
            owner_user_id=test_user.id,
            email="dict@example.com",
        )
        d = invite.to_dict()
        assert d["email"] == "dict@example.com"
        assert d["role"] == "member"
        assert d["status"] == "pending"
        assert "created_at" in d
        assert "expires_at" in d

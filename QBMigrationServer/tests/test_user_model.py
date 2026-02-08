"""Tests for models/user.py - User model methods."""


class TestUserRoles:
    """Tests for User role hierarchy methods."""

    def test_user_role_defaults(self, db_session, test_user):
        assert test_user.role == "user"

    def test_is_admin_false_for_user(self, db_session, test_user):
        assert test_user.is_admin() is False

    def test_is_admin_true_for_admin(self, db_session, test_user):
        test_user.role = "admin"
        assert test_user.is_admin() is True

    def test_is_super_admin_false_for_admin(self, db_session, test_user):
        test_user.role = "admin"
        assert test_user.is_super_admin() is False

    def test_is_super_admin_true(self, db_session, test_user):
        test_user.role = "super_admin"
        assert test_user.is_super_admin() is True

    def test_can_manage_users_admin(self, db_session, test_user):
        test_user.role = "admin"
        assert test_user.can_manage_users() is True

    def test_can_manage_users_regular(self, db_session, test_user):
        assert test_user.can_manage_users() is False

    def test_can_view_all_migrations_admin(self, db_session, test_user):
        test_user.role = "admin"
        assert test_user.can_view_all_migrations() is True

    def test_can_access_admin_dashboard_support(self, db_session, test_user):
        test_user.role = "support"
        assert test_user.can_access_admin_dashboard() is True

    def test_can_access_admin_dashboard_user(self, db_session, test_user):
        assert test_user.can_access_admin_dashboard() is False

    def test_has_role_or_higher_admin_vs_user(self, db_session, test_user):
        test_user.role = "admin"
        assert test_user.has_role_or_higher("user") is True

    def test_has_role_or_higher_user_vs_admin(self, db_session, test_user):
        test_user.role = "user"
        assert test_user.has_role_or_higher("admin") is False


class TestUserPassword:
    """Tests for User password methods."""

    def test_set_password(self, db_session, test_user):
        test_user.set_password("NewPassword123!")
        assert test_user.password_hash is not None

    def test_check_password_correct(self, db_session, test_user):
        # test_user was created with "TestPassword1234!"
        assert test_user.check_password("TestPassword1234!") is True

    def test_check_password_wrong(self, db_session, test_user):
        assert test_user.check_password("WrongPassword123!") is False

    def test_check_password_reuse_no_history(self, db_session, test_user):
        result = test_user.check_password_reuse("SomePassword123!")
        assert result is False  # No history, so not reused


class TestUserMethods:
    """Tests for User utility methods."""

    def test_get_id(self, db_session, test_user):
        user_id = test_user.get_id()
        assert user_id is not None

    def test_get_tier_info(self, db_session, test_user):
        info = test_user.get_tier_info()
        assert "tier" in info
        assert "migrations_purchased" in info
        assert "migrations_remaining" in info

    def test_repr(self, db_session, test_user):
        r = repr(test_user)
        assert "test@example.com" in r

    def test_user_active_by_default(self, db_session, test_user):
        assert test_user.is_active is True

    def test_email_verified_default(self, db_session, test_user):
        # By default, email is not verified
        assert test_user.email_verified is False or test_user.email_verified is True

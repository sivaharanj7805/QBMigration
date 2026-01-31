-- =============================================================================
-- QBMigration Performance Indexes
-- =============================================================================
-- This migration adds database indexes for common query patterns to improve
-- performance. Run this migration after initial schema creation.
--
-- Run with: psql -d qbmigration -f add_performance_indexes.sql
-- =============================================================================

-- Safety check: Only run on PostgreSQL
DO $$
BEGIN
    IF current_setting('server_version_num')::int < 100000 THEN
        RAISE EXCEPTION 'PostgreSQL 10+ required for these indexes';
    END IF;
END $$;

-- =============================================================================
-- USERS TABLE INDEXES
-- =============================================================================

-- Email lookup (login, registration check)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email
    ON users (email);

-- Email lookup with case-insensitive matching
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email_lower
    ON users (LOWER(email));

-- Active users by created date (admin dashboard)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_created_at
    ON users (created_at DESC);

-- Subscription tier lookup (billing queries)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_subscription_tier
    ON users (subscription_tier) WHERE subscription_tier IS NOT NULL;

-- Failed login tracking (security)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_failed_logins
    ON users (failed_login_attempts, locked_until)
    WHERE failed_login_attempts > 0;

-- =============================================================================
-- MIGRATIONS TABLE INDEXES
-- =============================================================================

-- User's migrations (dashboard listing)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_user_id
    ON migrations (user_id);

-- User's migrations sorted by date (most common query)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_user_id_created
    ON migrations (user_id, created_at DESC);

-- Status-based queries (admin monitoring)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_status
    ON migrations (status);

-- Active migrations (for cleanup and monitoring)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_active
    ON migrations (status, started_at)
    WHERE status IN ('pending', 'in_progress', 'uploading', 'validating');

-- Completed migrations by date (reporting)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_completed
    ON migrations (completed_at DESC)
    WHERE status = 'completed';

-- Failed migrations (troubleshooting)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_failed
    ON migrations (failed_at DESC, error_message)
    WHERE status = 'failed';

-- QBO Realm ID lookup (multi-tenant)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_realm_id
    ON migrations (qbo_realm_id)
    WHERE qbo_realm_id IS NOT NULL;

-- =============================================================================
-- MIGRATION CREDITS TABLE INDEXES
-- =============================================================================

-- User's available credits (purchase/usage flow)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_credits_user_available
    ON migration_credits (user_id, status)
    WHERE status = 'available' AND payment_status = 'paid';

-- Payment status tracking
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_credits_payment_status
    ON migration_credits (payment_status, created_at);

-- Stripe session lookup (webhook handling)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_credits_stripe_session
    ON migration_credits (stripe_checkout_session_id)
    WHERE stripe_checkout_session_id IS NOT NULL;

-- Used credits by migration (audit trail)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_credits_migration_id
    ON migration_credits (migration_id)
    WHERE migration_id IS NOT NULL;

-- =============================================================================
-- AUDIT LOG TABLE INDEXES
-- =============================================================================

-- User audit history
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_user_id
    ON audit_logs (user_id, created_at DESC);

-- Action type queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_action
    ON audit_logs (action, created_at DESC);

-- IP address lookup (security investigation)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_ip_address
    ON audit_logs (ip_address)
    WHERE ip_address IS NOT NULL;

-- Entity-based audit trail
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_entity
    ON audit_logs (entity_type, entity_id, created_at DESC);

-- Recent audit entries (dashboard)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_created_at
    ON audit_logs (created_at DESC);

-- =============================================================================
-- WEBHOOK DELIVERY LOG TABLE INDEXES
-- =============================================================================

-- Webhook by migration
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_webhook_log_migration
    ON webhook_delivery_logs (migration_id, created_at DESC);

-- Status tracking (retry logic)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_webhook_log_status
    ON webhook_delivery_logs (status, next_retry_at)
    WHERE status != 'delivered';

-- Pending retries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_webhook_log_pending_retry
    ON webhook_delivery_logs (next_retry_at)
    WHERE status = 'pending' AND next_retry_at IS NOT NULL;

-- =============================================================================
-- FILE UPLOADS TABLE INDEXES
-- =============================================================================

-- User's uploads
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_uploads_user_id
    ON file_uploads (user_id, created_at DESC);

-- S3 key lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_uploads_s3_key
    ON file_uploads (s3_key)
    WHERE s3_key IS NOT NULL;

-- Expiring uploads (cleanup job)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_uploads_expires_at
    ON file_uploads (expires_at)
    WHERE expires_at IS NOT NULL;

-- =============================================================================
-- SESSION TABLE INDEXES (if using database sessions)
-- =============================================================================

-- Session expiry (cleanup)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_expires_at
    ON sessions (expires_at);

-- User sessions
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_user_id
    ON sessions (user_id)
    WHERE user_id IS NOT NULL;

-- =============================================================================
-- TEAM INVITES TABLE INDEXES
-- =============================================================================

-- Pending invites by email
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_invites_email
    ON team_invites (invited_email, status)
    WHERE status = 'pending';

-- Owner's invites
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_invites_owner
    ON team_invites (owner_id, created_at DESC);

-- Token lookup (accept invite)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_invites_token
    ON team_invites (invite_token)
    WHERE status = 'pending';

-- =============================================================================
-- COMPOSITE INDEXES FOR COMMON JOINS
-- =============================================================================

-- Migration with user (common join)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_user_status
    ON migrations (user_id, status, created_at DESC);

-- Credits with user for billing
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_credits_user_tier
    ON migration_credits (user_id, tier_type, status);

-- =============================================================================
-- PARTIAL INDEXES FOR BOOLEAN FLAGS
-- =============================================================================

-- Active subscriptions only
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_active_subscription
    ON users (id)
    WHERE subscription_active = true;

-- Verified emails only
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_verified
    ON users (id, email)
    WHERE email_verified = true;

-- =============================================================================
-- TEXT SEARCH INDEXES (if full-text search is needed)
-- =============================================================================

-- Migration name/description search (if applicable)
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_migrations_search
--     ON migrations USING gin(to_tsvector('english', COALESCE(name, '') || ' ' || COALESCE(description, '')));

-- =============================================================================
-- ANALYZE TABLES AFTER INDEX CREATION
-- =============================================================================

ANALYZE users;
ANALYZE migrations;
ANALYZE migration_credits;
ANALYZE audit_logs;
ANALYZE webhook_delivery_logs;
ANALYZE file_uploads;

-- =============================================================================
-- NOTES
-- =============================================================================
--
-- 1. CONCURRENTLY allows index creation without blocking writes
-- 2. IF NOT EXISTS prevents errors if index already exists
-- 3. Partial indexes (WHERE clause) reduce index size and improve performance
-- 4. ANALYZE updates statistics for query planner
--
-- Monitor index usage with:
--   SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
--   FROM pg_stat_user_indexes
--   ORDER BY idx_scan DESC;
--
-- Remove unused indexes:
--   DROP INDEX CONCURRENTLY IF EXISTS index_name;
-- =============================================================================

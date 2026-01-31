-- ============================================================================
-- PRODUCTION READINESS INDEXES
-- Run this script on your PostgreSQL database to add indexes for improved query performance
-- ============================================================================

-- MED-10: Migration Credit composite indexes
CREATE INDEX IF NOT EXISTS idx_credit_user_status_payment
ON migration_credits (user_id, status, payment_status);

CREATE INDEX IF NOT EXISTS idx_credit_user_tier
ON migration_credits (user_id, tier_type);

-- CRIT-05: Unique constraints for idempotency
-- Note: These may fail if duplicates already exist - clean up duplicates first
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_stripe_checkout_session_id') THEN
        ALTER TABLE migration_credits
        ADD CONSTRAINT uq_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_stripe_payment_intent_id') THEN
        ALTER TABLE migration_credits
        ADD CONSTRAINT uq_stripe_payment_intent_id UNIQUE (stripe_payment_intent_id);
    END IF;
END $$;

-- MED-10: Team invite indexes
CREATE INDEX IF NOT EXISTS idx_team_invite_status_expires
ON team_invites (status, expires_at);

CREATE INDEX IF NOT EXISTS idx_team_invite_owner_status
ON team_invites (owner_user_id, status);

-- Verify indexes were created
SELECT indexname, tablename FROM pg_indexes
WHERE schemaname = 'public'
AND (indexname LIKE 'idx_credit%' OR indexname LIKE 'idx_team_invite%');

-- ============================================================================
-- CLEANUP: Remove expired data
-- ============================================================================

-- Mark expired team invites
UPDATE team_invites
SET status = 'expired'
WHERE status = 'pending' AND expires_at < NOW();

-- Mark expired migration credits
UPDATE migration_credits
SET status = 'expired'
WHERE status = 'available' AND expires_at IS NOT NULL AND expires_at < NOW();

-- Show cleanup results
SELECT
    'team_invites' as table_name,
    COUNT(*) FILTER (WHERE status = 'expired') as expired_count,
    COUNT(*) FILTER (WHERE status = 'pending') as pending_count
FROM team_invites
UNION ALL
SELECT
    'migration_credits' as table_name,
    COUNT(*) FILTER (WHERE status = 'expired') as expired_count,
    COUNT(*) FILTER (WHERE status = 'available') as pending_count
FROM migration_credits;

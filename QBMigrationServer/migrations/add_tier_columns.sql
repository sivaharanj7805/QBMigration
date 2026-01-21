-- Migration: Add subscription tier columns to users table
-- Run this script to add the new tier tracking columns

-- Add subscription_tier column
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(50) DEFAULT NULL;

-- Add migration tracking columns
ALTER TABLE users ADD COLUMN IF NOT EXISTS migrations_purchased INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS migrations_used INTEGER DEFAULT 0;

-- Add Stripe integration columns
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255) DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_payment_intent VARCHAR(255) DEFAULT NULL;

-- Add tier purchase timestamp
ALTER TABLE users ADD COLUMN IF NOT EXISTS tier_purchased_at TIMESTAMP DEFAULT NULL;

-- Verify columns were added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name IN ('subscription_tier', 'migrations_purchased', 'migrations_used', 'stripe_customer_id', 'tier_purchased_at');

-- =============================================================================
-- QBMigration Database Initialization
-- =============================================================================
-- Mounted into PostgreSQL container via docker-entrypoint-initdb.d.
-- Runs once on first container start (when data volume is empty).
-- =============================================================================

-- Enable uuid-ossp extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

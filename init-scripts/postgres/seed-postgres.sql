-- seed-postgres.sql
-- Runs against the default database (ebap_db) set via POSTGRES_DB.
-- Creates the users table, seeds data, and sets up CDC publication.
--
-- NOTE: The iceberg_catalog database is created by 00-create-databases.sh
--       which runs before this file (docker-entrypoint-initdb.d sorts by name).

-- =====================================================================
-- Application schema (runs in ebap_db)
-- =====================================================================

-- Create the users table (CDC source for Debezium)
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    user_id     VARCHAR(64)  NOT NULL UNIQUE,
    username    VARCHAR(128) NOT NULL,
    email       VARCHAR(256) NOT NULL,
    tier        VARCHAR(32)  NOT NULL DEFAULT 'free',
    region      VARCHAR(64)  NOT NULL DEFAULT 'us-east-1',
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Enable full row logging in WAL so Debezium populates the "before" field
-- on UPDATE and DELETE events (default REPLICA IDENTITY only includes PK).
ALTER TABLE users REPLICA IDENTITY FULL;

-- Insert seed data
INSERT INTO users (user_id, username, email, tier, region) VALUES
    ('usr_001', 'alice_wonder',   'alice@example.com',   'premium',    'us-east-1'),
    ('usr_002', 'bob_builder',    'bob@example.com',     'free',       'eu-west-1'),
    ('usr_003', 'charlie_choco',  'charlie@example.com', 'enterprise', 'ap-south-1'),
    ('usr_004', 'diana_prince',   'diana@example.com',   'premium',    'us-west-2'),
    ('usr_005', 'eve_hacker',     'eve@example.com',     'free',       'eu-central-1'),
    ('usr_006', 'frank_castle',   'frank@example.com',   'enterprise', 'us-east-1'),
    ('usr_007', 'grace_hopper',   'grace@example.com',   'premium',    'ap-northeast-1'),
    ('usr_008', 'henry_ford',     'henry@example.com',   'free',       'sa-east-1'),
    ('usr_009', 'iris_west',      'iris@example.com',    'premium',    'eu-west-1'),
    ('usr_010', 'jack_sparrow',   'jack@example.com',    'free',       'us-east-1')
ON CONFLICT (user_id) DO NOTHING;

-- Create publication for Debezium CDC
-- (Debezium reads from the WAL using this publication)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'ebap_publication') THEN
        CREATE PUBLICATION ebap_publication FOR TABLE users;
    END IF;
END
$$;

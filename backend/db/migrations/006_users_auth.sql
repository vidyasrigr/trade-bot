-- Migration 006: User accounts + portfolio privacy
-- Run after 005_agent_monitor.sql

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Scope portfolio holdings to a user
ALTER TABLE portfolio_holdings
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_holdings_user ON portfolio_holdings(user_id);

-- One-time setup: run POST /auth/setup to create V and N with real passwords.
-- This table starts empty — the setup endpoint seeds the two users.

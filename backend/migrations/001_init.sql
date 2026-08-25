-- MiSendero backend schema (PostgreSQL, per ADR-03 / ADR-04 of the PFI document).
-- Idempotent: safe to run on every boot and repeatedly in tests.

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  terms_version TEXT,
  terms_accepted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trails (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  location TEXT NOT NULL,
  difficulty TEXT NOT NULL,
  duration TEXT,
  distance_km REAL,
  description TEXT,
  image_url TEXT,
  center_lat REAL,
  center_lng REAL,
  map_zoom INTEGER,
  -- ADR-04: coordinates are stored as JSON, not PostGIS geometry - JSONB keeps that
  -- decision but gives real query/validation support instead of an opaque TEXT blob.
  route_coordinates JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS activities (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  trail_id INTEGER REFERENCES trails(id) ON DELETE SET NULL,
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  distance_km REAL,
  duration_minutes INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trail_reports (
  id SERIAL PRIMARY KEY,
  trail_id INTEGER NOT NULL REFERENCES trails(id) ON DELETE CASCADE,
  reporter_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  issue_summary TEXT NOT NULL,
  severity TEXT NOT NULL,
  trail_state TEXT NOT NULL,
  cause TEXT,
  blocks_path BOOLEAN NOT NULL DEFAULT false,
  details TEXT,
  reporter_name TEXT NOT NULL DEFAULT 'Senderista',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS emergency_alerts (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  trail_id INTEGER REFERENCES trails(id) ON DELETE SET NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'sent',
  device_battery_percent INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trail_reports_trail_created
  ON trail_reports (trail_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activities_user_created
  ON activities (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_emergency_alerts_user_created
  ON emergency_alerts (user_id, created_at DESC);

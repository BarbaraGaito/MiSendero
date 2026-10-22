CREATE TABLE IF NOT EXISTS environmental_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  trail_id INTEGER NOT NULL REFERENCES trails(id) ON DELETE CASCADE,
  model_type TEXT NOT NULL,
  issued_at TIMESTAMPTZ NOT NULL,
  valid_until TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS environmental_snapshots_route_time
  ON environmental_snapshots (trail_id, issued_at DESC);

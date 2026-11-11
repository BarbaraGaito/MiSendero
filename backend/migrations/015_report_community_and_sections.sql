ALTER TABLE trail_reports ADD COLUMN IF NOT EXISTS end_latitude REAL;
ALTER TABLE trail_reports ADD COLUMN IF NOT EXISTS end_longitude REAL;
ALTER TABLE trail_reports ADD COLUMN IF NOT EXISTS route_end_progress_meters REAL;

CREATE TABLE IF NOT EXISTS report_feedback (
  report_id INTEGER NOT NULL REFERENCES trail_reports(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  feedback TEXT NOT NULL CHECK (feedback IN ('still_there', 'not_there', 'unsure')),
  observed_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (report_id, user_id)
);
ALTER TABLE report_feedback ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
UPDATE report_feedback SET last_seen_at = observed_at WHERE feedback = 'still_there' AND last_seen_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_report_feedback_observed ON report_feedback (report_id, observed_at DESC);

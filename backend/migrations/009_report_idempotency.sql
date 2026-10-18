ALTER TABLE trail_reports ADD COLUMN IF NOT EXISTS client_event_id UUID;
ALTER TABLE trail_reports ADD COLUMN IF NOT EXISTS client_payload_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_report_author_event ON trail_reports (reporter_user_id, client_event_id);

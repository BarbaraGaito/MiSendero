ALTER TABLE emergency_alerts ALTER COLUMN latitude DROP NOT NULL;
ALTER TABLE emergency_alerts ALTER COLUMN longitude DROP NOT NULL;
ALTER TABLE emergency_alerts ALTER COLUMN status SET DEFAULT 'registered';
ALTER TABLE emergency_alerts ADD COLUMN IF NOT EXISTS client_event_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS emergency_alerts_client_event
ON emergency_alerts (user_id, client_event_id);
-- Historical rows have no transport/delivery evidence.
UPDATE emergency_alerts SET status = 'registered' WHERE status = 'sent';

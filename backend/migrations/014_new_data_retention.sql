-- No historical backfill: only INSERTs after this migration opt in.
ALTER TABLE emergency_alerts ADD COLUMN IF NOT EXISTS retention_eligible_at TIMESTAMPTZ;
ALTER TABLE emergency_alerts ALTER COLUMN retention_eligible_at SET DEFAULT now();
ALTER TABLE emergency_alerts ADD COLUMN IF NOT EXISTS retention_purged_at TIMESTAMPTZ;
ALTER TABLE emergency_alerts ALTER COLUMN latitude DROP NOT NULL;
ALTER TABLE emergency_alerts ALTER COLUMN longitude DROP NOT NULL;
ALTER TABLE trip_plans ADD COLUMN IF NOT EXISTS retention_eligible_at TIMESTAMPTZ;
ALTER TABLE trip_plans ALTER COLUMN retention_eligible_at SET DEFAULT now();
ALTER TABLE trip_plans ADD COLUMN IF NOT EXISTS retention_purged_at TIMESTAMPTZ;

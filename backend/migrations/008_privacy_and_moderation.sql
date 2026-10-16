CREATE TABLE IF NOT EXISTS privacy_decisions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_event_id TEXT NOT NULL,
  purpose TEXT NOT NULL,
  notice_version TEXT NOT NULL,
  notice_text TEXT NOT NULL,
  granted BOOLEAN NOT NULL,
  decided_at TIMESTAMPTZ NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, client_event_id)
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_text TEXT;
ALTER TABLE trail_reports ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ;
ALTER TABLE trail_reports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE trail_reports ADD COLUMN IF NOT EXISTS moderation_status TEXT NOT NULL DEFAULT 'visible';
UPDATE trail_reports SET reporter_name = 'Senderista'
  WHERE reporter_user_id IS NOT NULL AND reporter_name <> 'Senderista';
CREATE TABLE IF NOT EXISTS report_flags (
  id SERIAL PRIMARY KEY,
  report_id INTEGER NOT NULL REFERENCES trail_reports(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (report_id, user_id)
);
CREATE TABLE IF NOT EXISTS report_blocks (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  blocked_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, blocked_user_id)
);

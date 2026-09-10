CREATE TABLE IF NOT EXISTS trip_plans (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_plan_id TEXT NOT NULL,
  trail_id INTEGER REFERENCES trails(id),
  expected_return_at TIMESTAMPTZ NOT NULL,
  grace_minutes INTEGER NOT NULL,
  contact_name TEXT NOT NULL,
  contact_phone TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  closed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, client_plan_id)
);
CREATE TABLE IF NOT EXISTS trip_notifications (
  id SERIAL PRIMARY KEY,
  plan_id INTEGER NOT NULL UNIQUE REFERENCES trip_plans(id) ON DELETE CASCADE,
  due_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  lease_until TIMESTAMPTZ,
  next_attempt_at TIMESTAMPTZ NOT NULL,
  accepted_at TIMESTAMPTZ,
  last_error TEXT
);

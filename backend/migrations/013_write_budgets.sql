CREATE TABLE IF NOT EXISTS api_write_budgets (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resource TEXT NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, resource, window_start)
);

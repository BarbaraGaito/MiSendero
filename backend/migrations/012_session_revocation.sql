-- Hashes of revoked credentials, never raw bearer tokens. Old signed tokens are
-- covered too; expired entries can be purged without restoring their validity.
CREATE TABLE IF NOT EXISTS auth_revocations (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_revocations_expiry ON auth_revocations(expires_at);

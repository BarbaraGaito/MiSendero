const { createHash } = require("node:crypto");
const { query } = require("./db");
const tokenHash = (token) => createHash("sha256").update(token).digest("hex");
const isRevoked = async (token) => Boolean((await query("SELECT token_hash FROM auth_revocations WHERE token_hash = $1", [tokenHash(token)])).rows[0]);
const revokeToken = async (token, userId, expiresAt) => query(
  "INSERT INTO auth_revocations (token_hash, user_id, expires_at) VALUES ($1,$2,$3) ON CONFLICT (token_hash) DO NOTHING",
  [tokenHash(token), userId, new Date(expiresAt * 1000).toISOString()]
);
module.exports = { isRevoked, revokeToken };

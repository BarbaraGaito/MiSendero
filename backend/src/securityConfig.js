const fs = require("node:fs");
const validateServerSecrets = (env = process.env) => {
  if (!env.JWT_SECRET) throw new Error("JWT_SECRET no está configurado.");
  if (env.NODE_ENV !== "production") return;
  const value = env.JWT_SECRET;
  if (Buffer.byteLength(value, "utf8") < 32 || new Set(value).size < 10 || /change.?me|replace|example|password|secret/i.test(value)) {
    throw new Error("JWT_SECRET de producción no cumple la política de longitud/diversidad. Generá uno aleatorio fuera del código.");
  }
  if (!/^https:\/\//.test(env.PRIVACY_CONTACT_URL || "") && !/^mailto:/.test(env.PRIVACY_CONTACT_URL || "")) throw new Error("Configurá el canal de privacidad antes de iniciar producción.");
};
const databaseOptions = (env = process.env) => {
  const options = { connectionString: env.DATABASE_URL, max: Number(env.PG_POOL_MAX || 10), idleTimeoutMillis: 30000, connectionTimeoutMillis: 5000 };
  if (env.NODE_ENV !== "production") return options;
  if (!env.PGSSLROOTCERT) throw new Error("Producción requiere PGSSLROOTCERT y verificación TLS de PostgreSQL.");
  if (options.connectionString) {
    const url = new URL(options.connectionString);
    if (!['postgres:', 'postgresql:'].includes(url.protocol)) throw new Error("Configuración PostgreSQL no válida.");
    if (url.searchParams.has("sslmode") && !["verify-full", "verify-ca"].includes(url.searchParams.get("sslmode"))) throw new Error("No se permite un modo SSL permisivo en producción.");
    // pg's connection string SSL options replace the ssl object. One source of
    // truth prevents the DSN from disabling CA/hostname verification.
    for (const key of ['sslmode','sslcert','sslkey','sslrootcert','uselibpqcompat']) url.searchParams.delete(key);
    options.connectionString = url.toString();
  }
  options.ssl = { ca: fs.readFileSync(env.PGSSLROOTCERT, "utf8"), rejectUnauthorized: true };
  return options;
};
module.exports = { validateServerSecrets, databaseOptions };

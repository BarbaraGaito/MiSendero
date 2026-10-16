const pino = require("pino");

const logger = pino({
  level: process.env.LOG_LEVEL || (process.env.NODE_ENV === "test" ? "silent" : "info"),
  // Entire request bodies and database errors can contain personal data. Log only
  // HTTP metadata and error types; never SQL values, URLs, addresses or messages.
  redact: {
    paths: ["req.headers", "res.headers", "req.body", "body", "password", "password_hash", "token", "authorization", "cookie", "email", "contact_phone", "contact_name", "latitude", "longitude", "*.password", "*.password_hash", "*.token", "*.email", "*.contact_phone", "*.contact_name", "*.latitude", "*.longitude"],
    censor: "[REDACTED]",
  },
  serializers: {
    err: (error) => ({ type: error?.name || "Error" }),
  },
});

module.exports = logger;

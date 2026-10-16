const crypto = require("crypto");

process.env.NODE_ENV = "test";
process.env.JWT_SECRET = crypto.randomBytes(32).toString("hex");
process.env.TEST_USER_PASSWORD = `TestPass-${crypto.randomUUID()}`;
process.env.CORS_ORIGIN = "http://localhost:19006";
// Fixture registration must not consume a shared IP budget between test cases.
process.env.AUTH_RATE_LIMIT_MAX = "1000";

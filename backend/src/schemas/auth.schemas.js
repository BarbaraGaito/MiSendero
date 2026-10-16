const { z } = require("zod");

const registerSchema = z.object({
  name: z.string().trim().min(1).max(120),
  email: z.string().trim().email().max(200),
  password: z.string().min(8).max(200),
  accepted_terms_version: z.literal(require("../terms.json").version),
});

const loginSchema = z.object({
  email: z.string().trim().email().max(200),
  password: z.string().min(1).max(200),
});

module.exports = { registerSchema, loginSchema };

const { z } = require("zod");

const registerSchema = z.object({
  name: z.string().trim().min(1).max(120),
  email: z.string().trim().email().max(200),
  password: z.string().min(8).max(200).refine((value) => Buffer.byteLength(value, "utf8") <= 72, "La contraseña debe ocupar como máximo 72 bytes UTF-8; los caracteres acentuados pueden ocupar más de un byte."),
  accepted_terms_version: z.literal(require("../terms.json").version),
});

const loginSchema = z.object({
  email: z.string().trim().email().max(200),
  password: z.string().min(1).max(200).refine((value) => Buffer.byteLength(value, "utf8") <= 72, "La credencial supera el límite UTF-8. Las cuentas anteriores con claves más largas requieren una recuperación verificada; no se truncan contraseñas."),
});

module.exports = { registerSchema, loginSchema };

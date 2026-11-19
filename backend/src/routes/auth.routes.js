const express = require("express");
const bcrypt = require("bcrypt");
const jwt = require("jsonwebtoken");
const { randomUUID } = require("node:crypto");
const { revokeToken } = require("../sessionRevocation");
const { query } = require("../db");
const { requireAuth } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const { registerSchema, loginSchema } = require("../schemas/auth.schemas");

const router = express.Router();
const JWT_ALGORITHM = "HS256";

const signToken = (user) =>
  jwt.sign({ userId: user.id, role: user.role }, process.env.JWT_SECRET, {
    algorithm: JWT_ALGORITHM,
    expiresIn: "1d",
    jwtid: randomUUID(),
  });

const getUserStats = async (userId) => {
  const { rows } = await query(
    `
      SELECT
        COALESCE(SUM(CASE WHEN completion_status = 'completed' THEN 1 ELSE 0 END), 0)::int AS completed_routes,
        COALESCE(SUM(distance_km), 0) AS total_distance_km
      FROM activities
      WHERE user_id = $1
    `,
    [userId]
  );

  return {
    completed_routes: rows[0].completed_routes,
    total_distance_km: Number(Number(rows[0].total_distance_km).toFixed(1)),
  };
};

router.post("/logout", requireAuth, async (req, res, next) => {
  try {
    await revokeToken(req.authToken, req.userId, req.authExpiresAt);
    res.json({ revoked: true });
  } catch (error) { next(error); }
});

router.get("/me", requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      `SELECT id, name, email, role, plan, terms_version, terms_accepted_at, created_at
       FROM users WHERE id = $1`,
      [req.userId]
    );
    const user = rows[0];

    if (!user) {
      return res.status(404).json({ message: "Usuario no encontrado" });
    }

    res.json({ user, stats: await getUserStats(user.id) });
  } catch (error) {
    next(error);
  }
});

router.post("/register", validateBody(registerSchema), async (req, res, next) => {
  try {
    const { name, email, password, accepted_terms_version } = req.body;
    const normalizedEmail = email.toLowerCase();

    const { rows: existingRows } = await query("SELECT id FROM users WHERE email = $1", [
      normalizedEmail,
    ]);

    if (existingRows[0]) {
      return res.status(409).json({ message: "El email ya esta registrado" });
    }

    const passwordHash = await bcrypt.hash(password, 10);
    const role = "user";
    const termsAcceptedAt = new Date().toISOString();

    const { rows: insertedRows } = await query(
      `
        INSERT INTO users (name, email, password_hash, role, terms_version, terms_accepted_at, terms_text)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, name, email, role, plan, terms_version, terms_accepted_at
      `,
      [name, normalizedEmail, passwordHash, role, String(accepted_terms_version), termsAcceptedAt, JSON.stringify(require("../terms.json"))]
    );
    const user = insertedRows[0];

    res.status(201).json({ token: signToken(user), user });
  } catch (error) {
    next(error);
  }
});

router.post("/login", validateBody(loginSchema), async (req, res, next) => {
  try {
    const { email, password } = req.body;
    const normalizedEmail = email.toLowerCase();

    const { rows } = await query("SELECT * FROM users WHERE email = $1", [normalizedEmail]);
    const user = rows[0];

    if (!user) {
      return res.status(401).json({ message: "Credenciales invalidas" });
    }

    const isValidPassword = await bcrypt.compare(password, user.password_hash);

    if (!isValidPassword) {
      return res.status(401).json({ message: "Credenciales invalidas" });
    }

    res.json({
      token: signToken(user),
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        role: user.role,
        plan: user.plan,
        terms_version: user.terms_version,
        terms_accepted_at: user.terms_accepted_at,
        created_at: user.created_at,
      },
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;

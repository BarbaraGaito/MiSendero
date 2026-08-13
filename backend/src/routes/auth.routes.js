const express = require("express");
const bcrypt = require("bcrypt");
const jwt = require("jsonwebtoken");
const db = require("../db");

const router = express.Router();

const getUserStats = (userId) => {
  const stats = db
    .prepare(`
      SELECT
        COUNT(*) AS completed_routes,
        COALESCE(SUM(distance_km), 0) AS total_distance_km
      FROM activities
      WHERE user_id = ?
    `)
    .get(userId);

  return {
    completed_routes: stats.completed_routes,
    total_distance_km: Number(stats.total_distance_km.toFixed(1))
  };
};

const requireAuth = (req, res, next) => {
  const authHeader = req.headers.authorization || "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : null;

  if (!token) {
    return res.status(401).json({ message: "Sesion requerida" });
  }

  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET || "development-secret");
    req.userId = payload.userId;
    next();
  } catch (error) {
    return res.status(401).json({ message: "Sesion invalida" });
  }
};

router.get("/profile", (req, res) => {
  const user = db
    .prepare("SELECT id, name, email, role, created_at FROM users ORDER BY id DESC LIMIT 1")
    .get();

  if (!user) {
    return res.json({
      user: null,
      stats: {
        completed_routes: 0,
        total_distance_km: 0
      }
    });
  }

  res.json({
    user,
    stats: getUserStats(user.id)
  });
});

router.get("/me", requireAuth, (req, res) => {
  const user = db
    .prepare("SELECT id, name, email, role, created_at FROM users WHERE id = ?")
    .get(req.userId);

  if (!user) {
    return res.status(404).json({ message: "Usuario no encontrado" });
  }

  res.json({
    user,
    stats: getUserStats(user.id)
  });
});

router.post("/register", async (req, res, next) => {
  try {
    const { name, email, password } = req.body;

    if (!name || !email || !password) {
      return res.status(400).json({ message: "Faltan datos obligatorios" });
    }

    const normalizedEmail = String(email).trim().toLowerCase();
    const existingUser = db
      .prepare("SELECT id FROM users WHERE email = ?")
      .get(normalizedEmail);

    if (existingUser) {
      return res.status(409).json({ message: "El email ya esta registrado" });
    }

    const passwordHash = await bcrypt.hash(password, 10);
    const usersCount = db.prepare("SELECT COUNT(*) AS count FROM users").get().count;
    const role = usersCount === 0 ? "admin" : "user";
    const result = db
      .prepare("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)")
      .run(name.trim(), normalizedEmail, passwordHash, role);

    const user = {
      id: result.lastInsertRowid,
      name: name.trim(),
      email: normalizedEmail,
      role
    };
    const token = jwt.sign(
      { userId: user.id },
      process.env.JWT_SECRET || "development-secret",
      { expiresIn: "7d" }
    );

    res.status(201).json({
      token,
      user
    });
  } catch (error) {
    next(error);
  }
});

router.post("/login", async (req, res, next) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ message: "Faltan datos obligatorios" });
    }

    const normalizedEmail = String(email).trim().toLowerCase();
    const user = db
      .prepare("SELECT * FROM users WHERE email = ?")
      .get(normalizedEmail);

    if (!user) {
      return res.status(401).json({ message: "Credenciales invalidas" });
    }

    const isValidPassword = await bcrypt.compare(password, user.password_hash);

    if (!isValidPassword) {
      return res.status(401).json({ message: "Credenciales invalidas" });
    }

    const token = jwt.sign(
      { userId: user.id },
      process.env.JWT_SECRET || "development-secret",
      { expiresIn: "7d" }
    );

    res.json({
      token,
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        role: user.role,
        created_at: user.created_at
      }
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;

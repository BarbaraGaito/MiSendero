const express = require("express");
const db = require("../db");

const router = express.Router();

router.get("/", (req, res) => {
  const trails = db
    .prepare("SELECT * FROM trails ORDER BY created_at DESC")
    .all();

  res.json(trails);
});

router.get("/:id", (req, res) => {
  const trail = db
    .prepare("SELECT * FROM trails WHERE id = ?")
    .get(req.params.id);

  if (!trail) {
    return res.status(404).json({ message: "Sendero no encontrado" });
  }

  res.json(trail);
});

router.post("/", (req, res) => {
  const {
    name,
    location,
    difficulty,
    duration,
    distance_km,
    description,
    image_url
  } = req.body;

  if (!name || !location || !difficulty) {
    return res.status(400).json({ message: "Faltan datos obligatorios" });
  }

  const result = db
    .prepare(`
      INSERT INTO trails (
        name,
        location,
        difficulty,
        duration,
        distance_km,
        description,
        image_url
      )
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `)
    .run(
      name.trim(),
      location.trim(),
      difficulty.trim(),
      duration || null,
      distance_km || null,
      description || null,
      image_url || null
    );

  const trail = db
    .prepare("SELECT * FROM trails WHERE id = ?")
    .get(result.lastInsertRowid);

  res.status(201).json(trail);
});

module.exports = router;

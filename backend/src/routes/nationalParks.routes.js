const express = require("express");
const { query } = require("../db");
const router = express.Router();

// Institution pages and registration forms are reviewed content, not a live
// closure feed. An API response must never imply the trail is currently open.
const liveStatus = {
  closures: "not_integrated",
  weather_alerts: "not_integrated",
  weather_url: "https://www.smn.gob.ar/alertas",
};

const listParks = async () => {
  const { rows: parks } = await query("SELECT profile FROM national_parks ORDER BY slug");
  const { rows: trails } = await query(`SELECT id, name, location, difficulty, duration,
    distance_km, image_url, national_park_slug FROM trails WHERE national_park_slug IS NOT NULL ORDER BY name`);
  return parks.map(({ profile }) => ({
    ...profile, live_status: liveStatus,
    trails: trails.filter((trail) => trail.national_park_slug === profile.slug),
  })).filter((park) => park.trails.length > 0);
};

router.get("/", async (_req, res, next) => {
  try { res.json(await listParks()); } catch (error) { next(error); }
});
router.get("/:slug", async (req, res, next) => {
  try {
    const park = (await listParks()).find((item) => item.slug === req.params.slug);
    if (!park) return res.status(404).json({ message: "Parque sin ficha oficial verificada" });
    res.json(park);
  } catch (error) { next(error); }
});

module.exports = router;
module.exports.liveStatus = liveStatus;

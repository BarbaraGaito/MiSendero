const express = require("express");
const { query } = require("../db");
const { requireAuth, requireAdmin } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const { createTrailSchema, createReportSchema } = require("../schemas/trails.schemas");
const { REPORT_STALE_AFTER_DAYS } = require("../cleanupStaleReports");

const router = express.Router();

const weatherLabels = {
  0: "Despejado",
  1: "Mayormente despejado",
  2: "Parcialmente nublado",
  3: "Nublado",
  45: "Niebla",
  48: "Niebla",
  51: "Llovizna leve",
  53: "Llovizna",
  55: "Llovizna intensa",
  61: "Lluvia leve",
  63: "Lluvia",
  65: "Lluvia intensa",
  71: "Nieve leve",
  73: "Nieve",
  75: "Nieve intensa",
  80: "Chaparrones leves",
  81: "Chaparrones",
  82: "Chaparrones intensos",
  95: "Tormenta",
};

const getRiskLevel = (windKmh, rainProbability, condition) => {
  const normalizedCondition = condition.toLowerCase();

  if (
    windKmh >= 45 ||
    rainProbability >= 70 ||
    normalizedCondition.includes("tormenta") ||
    normalizedCondition.includes("intensa") ||
    normalizedCondition.includes("nieve")
  ) {
    return "alto";
  }

  if (windKmh >= 28 || rainProbability >= 40 || normalizedCondition.includes("lluvia")) {
    return "medio";
  }

  return "bajo";
};

const getWeatherRecommendation = (riskLevel) => {
  if (riskLevel === "alto") {
    return "Condiciones exigentes. Revisa el pronostico antes de salir y considera postergar si no tenes experiencia.";
  }

  if (riskLevel === "medio") {
    return "Salida posible con precaucion. Lleva abrigo impermeable y revisa cambios de clima durante el recorrido.";
  }

  return "Condiciones favorables para iniciar, manteniendo equipo basico, agua y seguimiento de la ruta.";
};

const getFallbackWeather = (trail) => {
  const latitude = Number(trail.center_lat || 0);
  const month = new Date().getMonth();
  const isSummer = month >= 9 || month <= 2;
  const isPatagonia = latitude < -40;
  const isNorth = latitude > -30;
  const baseTemperature = isNorth ? (isSummer ? 29 : 22) : isPatagonia ? (isSummer ? 14 : 6) : isSummer ? 24 : 15;
  const windKmh = isPatagonia ? 28 : 14;
  const rainProbability = isNorth ? 42 : isPatagonia ? 35 : 24;
  const condition = rainProbability >= 40 ? "Parcialmente nublado" : "Mayormente despejado";
  const riskLevel = getRiskLevel(windKmh, rainProbability, condition);

  return {
    trail_id: trail.id,
    date: new Date().toISOString().slice(0, 10),
    temperature_c: baseTemperature,
    min_temperature_c: baseTemperature - 4,
    max_temperature_c: baseTemperature + 5,
    condition,
    wind_kmh: windKmh,
    rain_probability: rainProbability,
    risk_level: riskLevel,
    recommendation: getWeatherRecommendation(riskLevel),
    source: "Estimacion local sin conexion al servicio meteorologico",
  };
};

const mapWeatherResponse = (trail, weatherData) => {
  const current = weatherData.current || {};
  const daily = weatherData.daily || {};
  const condition = weatherLabels[current.weather_code] || "Condicion a confirmar";
  const windKmh = Math.round(Number(current.wind_speed_10m || 0));
  const rainProbability = Math.round(Number((daily.precipitation_probability_max || [0])[0] || 0));
  const riskLevel = getRiskLevel(windKmh, rainProbability, condition);

  return {
    trail_id: trail.id,
    date: current.time ? String(current.time).slice(0, 10) : new Date().toISOString().slice(0, 10),
    temperature_c: Math.round(Number(current.temperature_2m || 0)),
    min_temperature_c: Math.round(Number((daily.temperature_2m_min || [0])[0] || 0)),
    max_temperature_c: Math.round(Number((daily.temperature_2m_max || [0])[0] || 0)),
    condition,
    wind_kmh: windKmh,
    rain_probability: rainProbability,
    risk_level: riskLevel,
    recommendation: getWeatherRecommendation(riskLevel),
    source: "Open-Meteo",
  };
};

// route_coordinates is JSONB in Postgres (pg decodes it to a JS array automatically),
// but the mobile client's parseRouteCoordinates() still expects the JSON-as-text
// contract from ADR-04, so it gets re-serialized here at the API boundary.
const serializeTrail = (trail) => ({
  ...trail,
  route_coordinates:
    trail.route_coordinates != null ? JSON.stringify(trail.route_coordinates) : null,
});

const getTrailOr404 = async (id, res) => {
  const { rows } = await query("SELECT * FROM trails WHERE id = $1", [id]);
  const trail = rows[0];

  if (!trail) {
    res.status(404).json({ message: "Sendero no encontrado" });
    return null;
  }

  return trail;
};

router.get("/", async (req, res, next) => {
  try {
    const { rows } = await query("SELECT * FROM trails ORDER BY created_at DESC");
    res.json(rows.map(serializeTrail));
  } catch (error) {
    next(error);
  }
});

router.get("/:id/weather", async (req, res, next) => {
  try {
    const trail = await getTrailOr404(req.params.id, res);
    if (!trail) return;

    if (trail.center_lat === null || trail.center_lng === null) {
      return res.json(getFallbackWeather(trail));
    }

    const params = new URLSearchParams({
      latitude: String(trail.center_lat),
      longitude: String(trail.center_lng),
      current: "temperature_2m,weather_code,wind_speed_10m",
      daily: "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
      forecast_days: "1",
      timezone: "auto",
    });

    try {
      const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);

      if (!response.ok) {
        return res.json(getFallbackWeather(trail));
      }

      const weatherData = await response.json();
      res.json(mapWeatherResponse(trail, weatherData));
    } catch (fetchError) {
      res.json(getFallbackWeather(trail));
    }
  } catch (error) {
    next(error);
  }
});

router.get("/:id/reports", async (req, res, next) => {
  try {
    const { rows } = await query(
      `
        SELECT * FROM trail_reports
        WHERE trail_id = $1
          AND created_at > now() - ($2 || ' days')::interval
        ORDER BY created_at DESC
        LIMIT 6
      `,
      [req.params.id, REPORT_STALE_AFTER_DAYS]
    );
    res.json(rows);
  } catch (error) {
    next(error);
  }
});

router.post(
  "/:id/reports",
  requireAuth,
  validateBody(createReportSchema),
  async (req, res, next) => {
    try {
      const trail = await getTrailOr404(req.params.id, res);
      if (!trail) return;

      const {
        issue_summary,
        severity,
        trail_state,
        cause,
        blocks_path,
        details,
        latitude,
        longitude,
        accuracy_meters,
        route_progress_meters,
      } = req.body;

      const { rows: userRows } = await query("SELECT name FROM users WHERE id = $1", [
        req.userId,
      ]);
      const reporterName = userRows[0]?.name || "Usuario MiSendero";

      const { rows } = await query(
        `
          INSERT INTO trail_reports (
            trail_id, reporter_user_id, issue_summary, severity, trail_state,
            cause, blocks_path, details, latitude, longitude, accuracy_meters,
            route_progress_meters, reporter_name
          )
          VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
          RETURNING *
        `,
        [
          trail.id,
          req.userId,
          issue_summary,
          severity,
          trail_state,
          cause ?? null,
          Boolean(blocks_path),
          details ?? null,
          latitude ?? null,
          longitude ?? null,
          accuracy_meters ?? null,
          route_progress_meters ?? null,
          reporterName,
        ]
      );

      res.status(201).json(rows[0]);
    } catch (error) {
      next(error);
    }
  }
);

router.get("/:id", async (req, res, next) => {
  try {
    const trail = await getTrailOr404(req.params.id, res);
    if (trail) res.json(serializeTrail(trail));
  } catch (error) {
    next(error);
  }
});

router.post("/", requireAuth, requireAdmin, validateBody(createTrailSchema), async (req, res, next) => {
  try {
    const {
      name,
      location,
      difficulty,
      duration,
      distance_km,
      description,
      image_url,
      center_lat,
      center_lng,
      map_zoom,
      route_coordinates,
    } = req.body;

    const { rows } = await query(
      `
        INSERT INTO trails (
          name, location, difficulty, duration, distance_km, description,
          image_url, center_lat, center_lng, map_zoom, route_coordinates
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING *
      `,
      [
        name,
        location,
        difficulty,
        duration ?? null,
        distance_km ?? null,
        description ?? null,
        image_url ?? null,
        center_lat ?? null,
        center_lng ?? null,
        map_zoom ?? null,
        route_coordinates ? JSON.stringify(route_coordinates) : null,
      ]
    );

    res.status(201).json(serializeTrail(rows[0]));
  } catch (error) {
    next(error);
  }
});

module.exports = router;

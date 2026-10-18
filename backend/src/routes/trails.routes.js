const express = require("express");
const { createHash } = require("node:crypto");
const { query } = require("../db");
const { requireAuth, requireAdmin } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const { createTrailSchema, createReportSchema } = require("../schemas/trails.schemas");
const { REPORT_STALE_AFTER_DAYS } = require("../cleanupStaleReports");
const { cachedElevation, ensureTrailElevation } = require("../trailElevation");
const { liveStatus } = require("./nationalParks.routes");

const router = express.Router();
const { publicReportColumns, publicReport } = require("../reportContract");
const { validateReportPosition } = require("../reportPrivacy");

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
  national_park: trail.national_park ? { ...trail.national_park, live_status: liveStatus } : null,
  elevation: cachedElevation(trail),
  route_coordinates:
    trail.route_coordinates != null ? JSON.stringify(trail.route_coordinates) : null,
});

const getTrailOr404 = async (id, res) => {
  const { rows } = await query(`SELECT t.*, p.profile AS national_park FROM trails t
    LEFT JOIN national_parks p ON p.slug = t.national_park_slug WHERE t.id = $1`, [id]);
  const trail = rows[0];

  if (!trail) {
    res.status(404).json({ message: "Sendero no encontrado" });
    return null;
  }

  return trail;
};

router.get("/", async (_req, res, next) => {
  try {
    const { rows } = await query(`SELECT t.*, p.profile AS national_park FROM trails t
      LEFT JOIN national_parks p ON p.slug = t.national_park_slug ORDER BY t.created_at DESC`);
    res.json(rows.map(serializeTrail));
  } catch (error) {
    next(error);
  }
});

router.get("/:id/weather", async (req, res, next) => {
  try {
    const trail = await getTrailOr404(req.params.id, res);
    if (!trail) return;

    // Never estimate a forecast locally: without real data the client shows it as unavailable.
    if (trail.center_lat === null || trail.center_lng === null) {
      return res.status(422).json({ message: "El sendero no tiene coordenadas para consultar el pronostico" });
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
        return res.status(503).json({ message: "Pronostico no disponible" });
      }

      const weatherData = await response.json();
      res.json(mapWeatherResponse(trail, weatherData));
    } catch {
      res.status(503).json({ message: "Pronostico no disponible" });
    }
  } catch (error) {
    next(error);
  }
});

router.get("/:id/reports", (req, res, next) => req.headers.authorization ? requireAuth(req, res, next) : next(), async (req, res, next) => {
  try {
    const { rows } = await query(
      `
        SELECT ${publicReportColumns}, reporter_user_id FROM trail_reports
        WHERE trail_id = $1
          AND moderation_status = 'visible'
          AND (reporter_user_id IS NULL OR reporter_user_id NOT IN
            (SELECT blocked_user_id FROM report_blocks WHERE user_id = $3))
          AND COALESCE(observed_at, created_at) > now() - ($2 || ' days')::interval
        ORDER BY created_at DESC
        LIMIT 6
      `,
      [req.params.id, REPORT_STALE_AFTER_DAYS, req.userId ?? null]
    );
    res.set("Cache-Control", "no-store").json(rows.map((row) => ({ ...publicReport(row, row.reporter_user_id === req.userId), is_mine: row.reporter_user_id === req.userId })));
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

      if (!validateReportPosition(trail, req.body)) return res.status(400).json({ message: "El punto debe pertenecer al sendero. No se publicó el reporte.", code: "REPORT_OUTSIDE_TRAIL" });

      const {
        client_event_id,
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
        observed_at,
      } = req.body;

      const payloadHash = createHash("sha256").update(JSON.stringify([
        trail.id, issue_summary, severity, trail_state, cause ?? null,
        Boolean(blocks_path), details ?? null, latitude ?? null, longitude ?? null,
        accuracy_meters ?? null, route_progress_meters ?? null, observed_at ?? null,
      ])).digest("hex");
      let { rows } = await query(
        `
          INSERT INTO trail_reports (
            trail_id, reporter_user_id, issue_summary, severity, trail_state,
            cause, blocks_path, details, latitude, longitude, accuracy_meters,
            route_progress_meters, observed_at, client_event_id, client_payload_hash
          )
          VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
          ON CONFLICT (reporter_user_id, client_event_id) DO NOTHING
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
          observed_at ?? new Date().toISOString(),
          client_event_id ?? null,
          payloadHash,
        ]
      );
      if (client_event_id) {
        rows = (await query(`SELECT * FROM trail_reports
          WHERE reporter_user_id = $1 AND client_event_id = $2`, [req.userId, client_event_id])).rows;
        if (!rows[0] || rows[0].client_payload_hash !== payloadHash) {
          return res.status(409).json({ code: "IDEMPOTENCY_CONFLICT", error: "La identidad del reporte ya fue usada con otros datos." });
        }
      }
      res.status(201).json(publicReport(rows[0], true));
    } catch (error) {
      next(error);
    }
  }
);

router.get("/:id", async (req, res, next) => {
  try {
    const trail = await getTrailOr404(req.params.id, res);
    if (!trail) return;
    trail.elevation = await ensureTrailElevation(trail).catch(() => null);
    res.json(serializeTrail(trail));
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

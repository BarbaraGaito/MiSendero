const express = require("express");
const db = require("../db");

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
  95: "Tormenta"
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

const getBaseTemperature = (isNorth, isPatagonia, isSummer) => {
  if (isNorth) return isSummer ? 29 : 22;
  if (isPatagonia) return isSummer ? 14 : 6;
  return isSummer ? 24 : 15;
};

const getFallbackWeather = (trail) => {
  const latitude = Number(trail.center_lat || 0);
  const month = new Date().getMonth();
  const isSummer = month >= 9 || month <= 2;
  const isPatagonia = latitude < -40;
  const isNorth = latitude > -30;
  const baseTemperature = getBaseTemperature(isNorth, isPatagonia, isSummer);
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
    source: "Estimacion local sin conexion al servicio meteorologico"
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
    source: "Open-Meteo"
  };
};

router.get("/", (req, res) => {
  const trails = db
    .prepare("SELECT * FROM trails ORDER BY created_at DESC")
    .all();

  res.json(trails);
});

router.get("/:id/weather", async (req, res) => {
  const trail = db
    .prepare("SELECT * FROM trails WHERE id = ?")
    .get(req.params.id);

  if (!trail) {
    return res.status(404).json({ message: "Sendero no encontrado" });
  }

  if (trail.center_lat === null || trail.center_lng === null) {
    return res.json(getFallbackWeather(trail));
  }

  try {
    const params = new URLSearchParams({
      latitude: String(trail.center_lat),
      longitude: String(trail.center_lng),
      current: "temperature_2m,weather_code,wind_speed_10m",
      daily: "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
      forecast_days: "1",
      timezone: "auto"
    });
    const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);

    if (!response.ok) {
      return res.json(getFallbackWeather(trail));
    }

    const weatherData = await response.json();
    res.json(mapWeatherResponse(trail, weatherData));
  } catch (error) {
    res.json(getFallbackWeather(trail));
  }
});

router.get("/:id/reports", (req, res) => {
  const reports = db
    .prepare(
      `
        SELECT *
        FROM trail_reports
        WHERE trail_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT 6
      `
    )
    .all(req.params.id);

  res.json(reports);
});

router.post("/:id/reports", (req, res) => {
  const trail = db
    .prepare("SELECT id FROM trails WHERE id = ?")
    .get(req.params.id);

  if (!trail) {
    return res.status(404).json({ message: "Sendero no encontrado" });
  }

  const {
    issue_summary,
    severity,
    trail_state,
    cause,
    blocks_path,
    details
  } = req.body;

  if (!issue_summary || !severity || !trail_state) {
    return res.status(400).json({ message: "Faltan datos obligatorios del reporte" });
  }

  const result = db
    .prepare(
      `
        INSERT INTO trail_reports (
          trail_id,
          issue_summary,
          severity,
          trail_state,
          cause,
          blocks_path,
          details,
          reporter_name
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `
    )
    .run(
      trail.id,
      String(issue_summary).trim(),
      String(severity).trim(),
      String(trail_state).trim(),
      cause ? String(cause).trim() : null,
      blocks_path ? 1 : 0,
      details ? String(details).trim() : null,
      "Usuario MiSendero"
    );

  const report = db
    .prepare("SELECT * FROM trail_reports WHERE id = ?")
    .get(result.lastInsertRowid);

  res.status(201).json(report);
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
    image_url,
    center_lat,
    center_lng,
    map_zoom,
    route_coordinates
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
        image_url,
        center_lat,
        center_lng,
        map_zoom,
        route_coordinates
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `)
    .run(
      name.trim(),
      location.trim(),
      difficulty.trim(),
      duration ?? null,
      distance_km ?? null,
      description ?? null,
      image_url ?? null,
      center_lat ?? null,
      center_lng ?? null,
      map_zoom ?? null,
      route_coordinates
        ? typeof route_coordinates === "string"
          ? route_coordinates
          : JSON.stringify(route_coordinates)
        : null
    );

  const trail = db
    .prepare("SELECT * FROM trails WHERE id = ?")
    .get(result.lastInsertRowid);

  res.status(201).json(trail);
});

module.exports = router;

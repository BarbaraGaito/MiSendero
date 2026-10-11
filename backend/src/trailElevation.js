const { createHash } = require("node:crypto");
const { query } = require("./db");

const VERSION = 1;
const RESOLUTION_M = 90;
const MAX_SAMPLES = 500;
const NOISE_THRESHOLD_M = 5;
const pending = new Map();
const retryAfter = new Map();

const coordinatesOf = (trail) => {
  const coordinates = typeof trail.route_coordinates === "string"
    ? JSON.parse(trail.route_coordinates) : trail.route_coordinates;
  if (!Array.isArray(coordinates) || coordinates.length < 2 || coordinates.some((point) =>
    !Array.isArray(point) || point.length < 2 ||
    !Number.isFinite(point[0]) || Math.abs(point[0]) > 90 ||
    !Number.isFinite(point[1]) || Math.abs(point[1]) > 180)) {
    throw new Error("elevation-no-geometry");
  }
  return coordinates.map(([lat, lng]) => [lat, lng]);
};

const geometryHash = (trail) => createHash("sha256")
  .update(JSON.stringify(coordinatesOf(trail))).digest("hex");

const cachedElevation = (trail) => {
  try {
    return trail.elevation?.version === VERSION &&
      trail.elevation.geometry_hash === geometryHash(trail) ? trail.elevation : null;
  } catch {
    return null;
  }
};

const distanceMeters = (a, b) => {
  const radians = (degrees) => degrees * Math.PI / 180;
  const latDelta = radians(b[0] - a[0]);
  const lngDelta = radians(b[1] - a[1]);
  const h = Math.sin(latDelta / 2) ** 2 + Math.cos(radians(a[0])) *
    Math.cos(radians(b[0])) * Math.sin(lngDelta / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
};

const sampleRoute = (coordinates) => {
  const cumulative = [0];
  for (let i = 1; i < coordinates.length; i++) {
    cumulative.push(cumulative[i - 1] + distanceMeters(coordinates[i - 1], coordinates[i]));
  }
  const length = cumulative.at(-1);
  if (length < 1) throw new Error("elevation-no-geometry");
  const segments = Math.min(MAX_SAMPLES - 1, Math.max(1, Math.ceil(length / RESOLUTION_M)));
  const spacing = length / segments;
  let segment = 1;
  const samples = [];
  for (let i = 0; i <= segments; i++) {
    const distance = i === segments ? length : i * spacing;
    while (segment < cumulative.length - 1 && cumulative[segment] < distance) segment++;
    const segmentLength = cumulative[segment] - cumulative[segment - 1];
    const ratio = segmentLength ? (distance - cumulative[segment - 1]) / segmentLength : 0;
    const start = coordinates[segment - 1];
    const end = coordinates[segment];
    samples.push({
      latitude: start[0] + (end[0] - start[0]) * ratio,
      longitude: start[1] + (end[1] - start[1]) * ratio,
      distance_m: distance,
    });
  }
  return { samples, spacing };
};

// A moving anchor preserves sustained climbs while ignoring small DEM fluctuations.
const accumulatedElevation = (heights) => {
  let anchor = heights[0];
  let ascent = 0;
  let descent = 0;
  heights.slice(1).forEach((height, index) => {
    const change = height - anchor;
    if (Math.abs(change) >= NOISE_THRESHOLD_M || index === heights.length - 2) {
      ascent += Math.max(0, change);
      descent += Math.max(0, -change);
      anchor = height;
    }
  });
  return { ascent_m: Math.round(ascent), descent_m: Math.round(descent) };
};

const fetchElevation = async (trail, { timeoutMs = 7000 } = {}) => {
  const { samples, spacing } = sampleRoute(coordinatesOf(trail));
  const endpoint = new URL(process.env.ELEVATION_API_URL || "https://api.open-meteo.com/v1/elevation");
  if (endpoint.protocol !== "https:") throw new Error("elevation-invalid-provider");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const heights = [];
  try {
    for (let offset = 0; offset < samples.length; offset += 100) {
      const batch = samples.slice(offset, offset + 100);
      const url = new URL(endpoint);
      url.searchParams.set("latitude", batch.map((point) => point.latitude.toFixed(7)).join(","));
      url.searchParams.set("longitude", batch.map((point) => point.longitude.toFixed(7)).join(","));
      if (process.env.ELEVATION_API_KEY) url.searchParams.set("apikey", process.env.ELEVATION_API_KEY);
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error("elevation-provider-unavailable");
      const data = await response.json();
      if (!Array.isArray(data.elevation) || data.elevation.length !== batch.length ||
        data.elevation.some((height) => !Number.isFinite(height) || height < -500 || height > 9000)) {
        throw new Error("elevation-incomplete-data");
      }
      heights.push(...data.elevation);
    }
  } finally {
    clearTimeout(timer);
  }
  return {
    version: VERSION,
    geometry_hash: geometryHash(trail),
    source: "Copernicus DEM GLO-90 / Open-Meteo",
    source_url: "https://open-meteo.com/en/docs/elevation-api",
    resolution_m: RESOLUTION_M,
    sample_spacing_m: Math.round(spacing * 10) / 10,
    noise_threshold_m: NOISE_THRESHOLD_M,
    fetched_at: new Date().toISOString(),
    ...accumulatedElevation(heights),
    min_m: Math.min(...heights),
    max_m: Math.max(...heights),
    distance_m: Math.round(samples.at(-1).distance_m),
    points: samples.map((point, index) => ({
      ...point,
      distance_m: Math.round(point.distance_m * 10) / 10,
      elevation_m: heights[index],
    })),
  };
};

const ensureTrailElevation = async (trail, options) => {
  const cached = cachedElevation(trail);
  if (cached) return cached;
  const key = `${trail.id}:${geometryHash(trail)}`;
  if (pending.has(key)) return pending.get(key);
  if ((retryAfter.get(key) || 0) > Date.now()) throw new Error("elevation-provider-unavailable");
  const work = (async () => {
    const elevation = await fetchElevation(trail, options);
    // Do not attach an old profile if an administrator changed the route meanwhile.
    const { rows } = await query(
      "UPDATE trails SET elevation = $2::jsonb WHERE id = $1 AND route_coordinates = $3::jsonb RETURNING id",
      [trail.id, JSON.stringify(elevation), JSON.stringify(
        typeof trail.route_coordinates === "string" ? JSON.parse(trail.route_coordinates) : trail.route_coordinates
      )]
    );
    if (!rows.length) throw new Error("elevation-route-changed");
    retryAfter.delete(key);
    return elevation;
  })();
  pending.set(key, work);
  try {
    return await work;
  } catch (error) {
    retryAfter.set(key, Date.now() + 60000);
    throw error;
  } finally {
    pending.delete(key);
  }
};

module.exports = { cachedElevation, ensureTrailElevation, fetchElevation, geometryHash, sampleRoute, accumulatedElevation };

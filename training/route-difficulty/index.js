const fs = require("fs");
const path = require("path");
const db = require("../../backend/src/db");

const projectDir = __dirname;
const datasetsDir = path.join(projectDir, "datasets");
const outputDir = path.join(projectDir, "output");
const dryRun = process.argv.includes("--dry-run");

const modelConfig = {
  id: "route_difficulty",
  version: 1,
  source: "OpenStreetMap sac_scale + NASA SRTM normalized export",
  input: "route_difficulty_training.csv",
  features: [
    "distance_km",
    "elevation_gain_m",
    "avg_slope_percent",
    "max_slope_percent",
    "technical_score",
  ],
};

const restrictedHeaderPatterns = [
  /^email$/i,
  /^mail$/i,
  /^phone$/i,
  /^telefono$/i,
  /^dni$/i,
  /document/i,
  /user.?id/i,
  /session.?id/i,
  /exact.?lat/i,
  /exact.?lng/i,
  /exact.?lon/i,
  /^address$/i,
  /^direccion$/i,
];

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function parseCsv(filePath) {
  const lines = fs
    .readFileSync(filePath, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const headers = lines[0].split(",").map((header) => header.trim());
  const restrictedHeaders = headers.filter((header) =>
    restrictedHeaderPatterns.some((pattern) => pattern.test(header))
  );

  if (restrictedHeaders.length > 0) {
    throw new Error(
      `${path.basename(filePath)} contains personal or exact-location fields: ${restrictedHeaders.join(", ")}`
    );
  }

  return lines.slice(1).map((line) => {
    const values = line.split(",").map((value) => value.trim());

    return headers.reduce((row, header, index) => {
      const value = values[index];
      const numeric = Number(value);
      row[header] = Number.isFinite(numeric) && value !== "" ? numeric : value;
      return row;
    }, {});
  });
}

function mean(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function standardDeviation(values, avg) {
  const variance =
    values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / values.length;
  return Math.sqrt(variance) || 1;
}

function trainNearestCentroid(config) {
  const rows = parseCsv(path.join(datasetsDir, config.input));
  const statistics = {};

  for (const feature of config.features) {
    const values = rows.map((row) => Number(row[feature]));
    const avg = mean(values);
    statistics[feature] = {
      mean: Number(avg.toFixed(6)),
      std: Number(standardDeviation(values, avg).toFixed(6)),
    };
  }

  const byLabel = rows.reduce((groups, row) => {
    const label = String(row.label);
    groups[label] = groups[label] || [];
    groups[label].push(row);
    return groups;
  }, {});

  const centroids = Object.entries(byLabel).reduce((result, [label, labelRows]) => {
    result[label] = config.features.reduce((centroid, feature) => {
      const values = labelRows.map((row) => {
        const stat = statistics[feature];
        return (Number(row[feature]) - stat.mean) / stat.std;
      });
      centroid[feature] = Number(mean(values).toFixed(6));
      return centroid;
    }, {});
    return result;
  }, {});

  return {
    id: config.id,
    version: config.version,
    trained_at: process.env.AI_TRAINED_AT || new Date().toISOString(),
    algorithm: "nearest_centroid_standardized",
    source: config.source,
    features: config.features,
    labels: Object.keys(centroids),
    statistics,
    centroids,
  };
}

function predictNearestCentroid(model, input) {
  const distances = model.labels.reduce((result, label) => {
    const centroid = model.centroids[label];
    const squaredDistance = model.features.reduce((sum, feature) => {
      const stat = model.statistics[feature];
      const rawValue = input[feature] ?? stat.mean;
      const normalizedValue = (rawValue - stat.mean) / stat.std;
      return sum + (normalizedValue - centroid[feature]) ** 2;
    }, 0);

    result[label] = Math.sqrt(squaredDistance);
    return result;
  }, {});

  const [label] = Object.entries(distances).sort((a, b) => a[1] - b[1])[0];
  return { label, distances };
}

function updateTrailDifficulties() {
  const model = trainNearestCentroid(modelConfig);
  const featureRows = parseCsv(path.join(datasetsDir, "trail_features.csv"));
  const trails = db.prepare("SELECT id, name, difficulty FROM trails").all();
  const trailsByName = new Map(trails.map((trail) => [normalize(trail.name), trail]));
  const updates = [];
  const missing = [];

  for (const row of featureRows) {
    const trail = trailsByName.get(normalize(row.route_name));

    if (!trail) {
      missing.push(row.route_name);
      continue;
    }

    const prediction = predictNearestCentroid(model, row);
    updates.push({
      id: trail.id,
      name: trail.name,
      previousDifficulty: trail.difficulty,
      nextDifficulty: prediction.label,
      distances: prediction.distances,
    });
  }

  fs.mkdirSync(outputDir, { recursive: true });
  fs.writeFileSync(
    path.join(outputDir, "routeDifficultyModel.json"),
    `${JSON.stringify(model, null, 2)}\n`
  );

  if (!dryRun) {
    const updateStatement = db.prepare("UPDATE trails SET difficulty = ? WHERE id = ?");
    const transaction = db.transaction((rows) => {
      for (const row of rows) {
        updateStatement.run(row.nextDifficulty, row.id);
      }
    });

    transaction(updates);
  }

  console.table(
    updates.map((update) => ({
      id: update.id,
      route: update.name,
      previous: update.previousDifficulty,
      next: update.nextDifficulty,
    }))
  );

  if (missing.length > 0) {
    console.warn(`No backend trail match for: ${missing.join(", ")}`);
  }

  console.log(
    dryRun
      ? `dry-run complete: ${updates.length} route difficulties evaluated`
      : `database updated: ${updates.length} route difficulties saved`
  );
}

updateTrailDifficulties();

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const datasetsDir = path.join(root, "ai", "datasets");
const modelsDir = path.join(root, "ai", "models");
const restrictedHeaderPatterns = [
  /name/i,
  /nombre/i,
  /email/i,
  /mail/i,
  /phone/i,
  /telefono/i,
  /dni/i,
  /document/i,
  /user.?id/i,
  /session.?id/i,
  /exact.?lat/i,
  /exact.?lng/i,
  /exact.?lon/i,
  /location/i,
  /ubicacion/i,
  /address/i,
  /direccion/i,
];

const modelConfigs = [
  {
    id: "fatigue",
    version: 1,
    source: "PAMAP2 + WESAD normalized wearable windows",
    input: "fatigue_windows.csv",
    output: "fatigueModel.json",
    features: ["hr", "speed_kmh", "elapsed_minutes", "hr_reserve_percent"],
  },
  {
    id: "physio_risk",
    version: 1,
    source: "BIDMC physiological records + synthetic trekking context",
    input: "physio_risk.csv",
    output: "riskModel.json",
    features: [
      "hr",
      "speed_kmh",
      "elapsed_minutes",
      "elevation_gain_m",
      "fatigue_score",
    ],
  },
];

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
    trained_at: process.env.AI_TRAINED_AT || "2026-08-13T00:00:00.000Z",
    algorithm: "nearest_centroid_standardized",
    source: config.source,
    features: config.features,
    labels: Object.keys(centroids),
    statistics,
    centroids,
  };
}

fs.mkdirSync(modelsDir, { recursive: true });

for (const config of modelConfigs) {
  const model = trainNearestCentroid(config);
  const outputPath = path.join(modelsDir, config.output);
  fs.writeFileSync(outputPath, `${JSON.stringify(model, null, 2)}\n`);
  console.log(`trained ${config.id} -> ${path.relative(root, outputPath)}`);
}

const fs = require("fs");
const path = require("path");

const projectDir = __dirname;
const datasetsDir = path.join(projectDir, "datasets");
const outputDir = path.join(projectDir, "output");
const modelPath = path.join(
  projectDir,
  "..",
  "python",
  "route_difficulty",
  "output",
  "model.forest.json"
);

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

// Mirrors the leaf-detection convention used by sklearn's exported
// tree.children_left/right arrays: -1 means "no child", i.e. this node is a
// leaf. Same algorithm as ai/inferenceEngine.ts's predictRandomForest, kept
// here in plain CommonJS since this script has no TS toolchain of its own.
function predictRandomForest(model, row) {
  const featureValues = model.feature_order.map((feature) => Number(row[feature]) || 0);
  const classCount = model.classes.length;
  const summedProbabilities = new Array(classCount).fill(0);

  for (const tree of model.trees) {
    let nodeIndex = 0;

    while (tree.left[nodeIndex] !== -1) {
      const featureIndex = tree.feature[nodeIndex];
      const goLeft = featureValues[featureIndex] <= tree.threshold[nodeIndex];
      nodeIndex = goLeft ? tree.left[nodeIndex] : tree.right[nodeIndex];
    }

    const leafProbabilities = tree.value[nodeIndex];
    for (let classIndex = 0; classIndex < classCount; classIndex++) {
      summedProbabilities[classIndex] += leafProbabilities[classIndex] || 0;
    }
  }

  let bestIndex = 0;
  for (let classIndex = 1; classIndex < classCount; classIndex++) {
    if (summedProbabilities[classIndex] > summedProbabilities[bestIndex]) {
      bestIndex = classIndex;
    }
  }

  return {
    label: model.classes[bestIndex],
    confidence: Number((summedProbabilities[bestIndex] / model.trees.length).toFixed(2)),
  };
}

function evaluateTrailDifficulties() {
  if (!fs.existsSync(modelPath)) {
    throw new Error(
      `Missing trained model at ${modelPath}. Run "py training/python/route_difficulty/train.py" (or "npm run train:ai" from the repo root) first.`
    );
  }

  const model = JSON.parse(fs.readFileSync(modelPath, "utf8"));
  const featureRows = parseCsv(path.join(datasetsDir, "trail_features.csv"));

  const predictions = featureRows.map((row) => {
    const prediction = predictRandomForest(model, row);
    return {
      route_name: row.route_name,
      difficulty: prediction.label,
      confidence: prediction.confidence,
    };
  });

  fs.mkdirSync(outputDir, { recursive: true });
  fs.writeFileSync(
    path.join(outputDir, "predictions.json"),
    `${JSON.stringify(predictions, null, 2)}\n`
  );

  console.table(predictions);
  console.log(
    `predictions written for ${predictions.length} routes -> ${path.relative(projectDir, path.join(outputDir, "predictions.json"))}`
  );
  console.log(
    "This script does not write to any database. Applying these predictions to the backend's trails.difficulty field is a separate, manual/future step."
  );
}

evaluateTrailDifficulties();

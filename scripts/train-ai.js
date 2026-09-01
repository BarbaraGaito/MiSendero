const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const pythonDir = path.join(root, "training", "python");
const modelsDir = path.join(root, "ai", "models");

// Assumes `py -m pip install -r training/python/requirements.txt` has already
// been run once (see training/python/requirements.txt and ai/datasets/README.md).
// Reinstalling on every `npm run train:ai` invocation would slow down the
// common case of just retraining after a dataset tweak.
const trainingScripts = [
  {
    id: "fatigue",
    script: path.join(pythonDir, "fatigue", "train.py"),
    forestOutput: path.join(pythonDir, "fatigue", "output", "model.forest.json"),
    metricsOutput: path.join(pythonDir, "fatigue", "output", "metrics.json"),
    modelTarget: path.join(modelsDir, "fatigueModel.json"),
    metricsTarget: path.join(modelsDir, "fatigueMetrics.json"),
  },
  {
    id: "physio_risk",
    script: path.join(pythonDir, "physio_risk", "train.py"),
    forestOutput: path.join(pythonDir, "physio_risk", "output", "model.forest.json"),
    metricsOutput: path.join(pythonDir, "physio_risk", "output", "metrics.json"),
    modelTarget: path.join(modelsDir, "riskModel.json"),
    metricsTarget: path.join(modelsDir, "riskMetrics.json"),
  },
  {
    id: "route_difficulty",
    script: path.join(pythonDir, "route_difficulty", "train.py"),
    forestOutput: path.join(pythonDir, "route_difficulty", "output", "model.forest.json"),
    metricsOutput: path.join(pythonDir, "route_difficulty", "output", "metrics.json"),
    // Consumed by training/route-difficulty/index.js, not bundled in the app.
    modelTarget: null,
    metricsTarget: path.join(modelsDir, "routeDifficultyMetrics.json"),
  },
];

fs.mkdirSync(modelsDir, { recursive: true });

for (const config of trainingScripts) {
  execFileSync("py", [config.script], { stdio: "inherit" });

  if (config.modelTarget) {
    fs.copyFileSync(config.forestOutput, config.modelTarget);
    console.log(`copied ${config.id} -> ${path.relative(root, config.modelTarget)}`);
  }

  fs.copyFileSync(config.metricsOutput, config.metricsTarget);
  console.log(`copied ${config.id} metrics -> ${path.relative(root, config.metricsTarget)}`);
}

const fs = require("fs");
const path = require("path");
const { query } = require("./db");
const logger = require("./logger");

const predictionsPath = path.join(
  __dirname,
  "..",
  "..",
  "training",
  "route-difficulty",
  "output",
  "predictions.json"
);

// Applies the RandomForest predictions from training/python/route_difficulty (via
// training/route-difficulty/index.js) to trails.difficulty. Kept as a standalone,
// manually-run script rather than an HTTP endpoint since it's a maintenance/offline
// task, not something the app needs to trigger at runtime.
const applyRouteDifficultyPredictions = async (overridePath) => {
  const targetPath = overridePath || predictionsPath;

  if (!fs.existsSync(targetPath)) {
    throw new Error(
      `No se encontraron predicciones en ${targetPath}. Corre "npm run train:route-difficulty" (raiz del repo) primero.`
    );
  }

  const predictions = JSON.parse(fs.readFileSync(targetPath, "utf8"));
  let updated = 0;

  for (const prediction of predictions) {
    const { rowCount } = await query(`UPDATE trails SET difficulty = $1 WHERE name = $2`, [
      prediction.difficulty,
      prediction.route_name,
    ]);
    updated += rowCount;
  }

  return { total: predictions.length, updated };
};

module.exports = applyRouteDifficultyPredictions;

if (require.main === module) {
  applyRouteDifficultyPredictions()
    .then(({ total, updated }) => {
      logger.info({ total, updated }, "Predicciones de dificultad aplicadas");
      process.exit(0);
    })
    .catch((error) => {
      logger.error(error, "No se pudieron aplicar las predicciones de dificultad");
      process.exit(1);
    });
}

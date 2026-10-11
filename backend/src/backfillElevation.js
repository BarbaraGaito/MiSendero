require("dotenv").config();
const { query, getPool } = require("./db");
const runMigrations = require("./migrate");
const { ensureTrailElevation } = require("./trailElevation");

const main = async () => {
  await runMigrations();
  const { rows } = await query("SELECT * FROM trails ORDER BY id");
  let failures = 0;
  for (const trail of rows) {
    try {
      const elevation = await ensureTrailElevation(trail, { timeoutMs: 60000 });
      console.log(`${trail.id}: ${trail.name}: +${elevation.ascent_m} m / -${elevation.descent_m} m, ${elevation.points.length} puntos`);
    } catch (error) {
      failures++;
      console.error(`${trail.id}: ${trail.name}: ${error.message}`);
    }
  }
  console.log(`Altimetria: ${rows.length - failures}/${rows.length} rutas disponibles.`);
  process.exitCode = failures ? 1 : 0;
};

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
}).finally(async () => (await getPool()).end());

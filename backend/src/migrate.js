const fs = require("fs");
const path = require("path");
const { query } = require("./db");
const logger = require("./logger");

const migrationsDir = path.join(__dirname, "..", "migrations");

const runMigrations = async () => {
  const files = fs
    .readdirSync(migrationsDir)
    .filter((file) => file.endsWith(".sql"))
    .sort();

  for (const file of files) {
    const sql = fs.readFileSync(path.join(migrationsDir, file), "utf8");
    await query(sql);
  }
};

module.exports = runMigrations;

if (require.main === module) {
  runMigrations()
    .then(() => {
      logger.info("Migraciones aplicadas correctamente");
      process.exit(0);
    })
    .catch((error) => {
      logger.error(error, "Error al aplicar migraciones");
      process.exit(1);
    });
}

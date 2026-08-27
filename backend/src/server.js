require("dotenv").config();

const express = require("express");
const cors = require("cors");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");
const pinoHttp = require("pino-http");
const logger = require("./logger");
const runMigrations = require("./migrate");
const seedDatabase = require("./seed");
const { cleanupStaleReports } = require("./cleanupStaleReports");
const authRoutes = require("./routes/auth.routes");
const trailsRoutes = require("./routes/trails.routes");
const activitiesRoutes = require("./routes/activities.routes");
const emergencyAlertsRoutes = require("./routes/emergencyAlerts.routes");

if (!process.env.JWT_SECRET) {
  logger.error(
    "JWT_SECRET no esta configurado. Copia backend/.env.example a backend/.env y generá un secreto."
  );
  process.exit(1);
}

const app = express();
const port = process.env.PORT || 3001;
const corsOrigins = (process.env.CORS_ORIGIN || "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);
const CLEANUP_INTERVAL_MS = 24 * 60 * 60 * 1000;

app.use(helmet());
app.use(
  cors({
    origin: corsOrigins.length > 0 ? corsOrigins : false,
  })
);
if (process.env.NODE_ENV !== "test") {
  app.use(pinoHttp({ logger }));
}
app.use(express.json());

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { message: "Demasiados intentos. Intenta nuevamente en unos minutos." },
});

app.get("/api/health", (req, res) => {
  res.json({ ok: true, service: "misendero-backend" });
});

app.use("/api/auth/login", authLimiter);
app.use("/api/auth/register", authLimiter);
app.use("/api/auth", authRoutes);
app.use("/api/trails", trailsRoutes);
app.use("/api/activities", activitiesRoutes);
app.use("/api/emergency-alerts", emergencyAlertsRoutes);

app.use((req, res) => {
  res.status(404).json({ message: "Ruta no encontrada" });
});

app.use((error, req, res, next) => {
  logger.error(error);
  res.status(500).json({ message: "Error interno del servidor" });
});

const scheduleStaleReportsCleanup = () => {
  const runCleanup = async () => {
    try {
      const removed = await cleanupStaleReports();
      if (removed > 0) {
        logger.info({ removed }, "Reportes de terreno obsoletos descartados");
      }
    } catch (error) {
      logger.error(error, "Fallo la limpieza de reportes obsoletos");
    }
  };

  runCleanup();
  return setInterval(runCleanup, CLEANUP_INTERVAL_MS);
};

const start = async () => {
  await runMigrations();
  await seedDatabase();
  scheduleStaleReportsCleanup();

  app.listen(port, () => {
    logger.info(`MiSendero backend running on http://localhost:${port}`);
  });
};

if (require.main === module) {
  start().catch((error) => {
    logger.error(error, "No se pudo iniciar el backend");
    process.exit(1);
  });
}

module.exports = app;

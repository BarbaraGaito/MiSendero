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
const nationalParksRoutes = require("./routes/nationalParks.routes");
const activitiesRoutes = require("./routes/activities.routes");
const emergencyAlertsRoutes = require("./routes/emergencyAlerts.routes");
const tripPlansRoutes = require("./routes/tripPlans.routes");
const { processTripNotifications } = require("./tripNotifications");

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
  app.use(pinoHttp({ logger, serializers: {
    req: (req) => ({ id: req.id, method: req.method }),
    res: (res) => ({ statusCode: res.statusCode }),
  } }));
}
app.use(express.json());
app.use((req, res, next) => {
  if (req.path.startsWith("/api/auth") || req.path.startsWith("/account")) res.set("Cache-Control", "no-store");
  next();
});
app.get("/account-deletion", (_req, res) => res.sendFile(require("path").join(__dirname, "public", "account-deletion.html")));
app.use("/account-assets", express.static(require("path").join(__dirname, "public")));
app.get("/api/privacy-contact", (_req, res) => {
  const url = process.env.PRIVACY_CONTACT_URL || "";
  res.json({ url: /^(https:\/\/|mailto:)/.test(url) ? url : null });
});

const authLimiter = rateLimit({
  windowMs: Number(process.env.AUTH_RATE_LIMIT_WINDOW_MS || 15 * 60 * 1000),
  limit: Number(process.env.AUTH_RATE_LIMIT_MAX || 10),
  standardHeaders: true,
  legacyHeaders: false,
  message: { message: "Demasiados intentos. Intenta nuevamente en unos minutos." },
});

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, service: "misendero-backend" });
});

app.use("/api/auth/login", authLimiter);
app.use("/api/auth/register", authLimiter);
app.use("/api/auth/me", (req, res, next) => req.method === "DELETE" ? authLimiter(req, res, next) : next());
app.use("/api/auth", authRoutes);
app.use("/api/auth", require("./routes/account.routes"));
app.use("/api/trails", trailsRoutes);
app.use("/api/reports", require("./routes/reportModeration.routes"));
app.use("/api/national-parks", nationalParksRoutes);
app.use("/api/activities", activitiesRoutes);
app.use("/api/emergency-alerts", emergencyAlertsRoutes);
app.use("/api/trip-plans", tripPlansRoutes);
app.use("/api/ai", require("./routes/ai.routes"));

app.use((_req, res) => {
  res.status(404).json({ message: "Ruta no encontrada" });
});

app.use((error, _req, res, _next) => {
  if (error.type === "entity.too.large") return res.status(413).json({ message: "La solicitud es demasiado extensa." });
  if (error.type === "entity.parse.failed") return res.status(400).json({ message: "El JSON de la solicitud no es válido." });
  logger.error({ err: error }, "Solicitud fallida");
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
  // RDS schema and catalog changes are explicit operator actions, never production boot effects.
  if (process.env.NODE_ENV !== "production") {
    await runMigrations();
    await seedDatabase();
  }
  void require("../dist/ai/model").localRanker.start();
  scheduleStaleReportsCleanup();
  const notifyTrips = () => processTripNotifications().catch((error) => logger.error(error, "No se pudieron procesar avisos de regreso"));
  void notifyTrips();
  setInterval(notifyTrips, 30000);

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

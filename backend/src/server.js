require("dotenv").config();

const express = require("express");
const cors = require("cors");
const initDb = require("./initDb");
const authRoutes = require("./routes/auth.routes");
const trailsRoutes = require("./routes/trails.routes");

const app = express();
const port = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

initDb();

app.get("/api/health", (req, res) => {
  res.json({ ok: true, service: "misendero-backend" });
});

app.use("/api/auth", authRoutes);
app.use("/api/trails", trailsRoutes);

app.use((req, res) => {
  res.status(404).json({ message: "Ruta no encontrada" });
});

app.use((error, req, res, next) => {
  console.error(error);
  res.status(500).json({ message: "Error interno del servidor" });
});

app.listen(port, () => {
  console.log(`MiSendero backend running on http://localhost:${port}`);
});

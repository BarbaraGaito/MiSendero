// Local, read-only HTTP + real PostgreSQL smoke test. Never calls server.start(), seeds or RDS.
const path = require("path");
const http = require("http");
async function main() {
  require("dotenv").config({ path: path.resolve(__dirname, "../.env"), quiet: true });
  require("./importCatalogExpansion").assertLocalDatabase();
  process.env.NODE_ENV = "production";
  const { getPool } = require("../src/db");
  const pool = await getPool();
  const server = http.createServer(require("../src/server"));
  try {
    const user = (await pool.query("SELECT id FROM users ORDER BY id LIMIT 1")).rows[0];
    if (!user) throw new Error("A local test account is required");
    const token = require("jsonwebtoken").sign({ userId: user.id }, process.env.JWT_SECRET, { expiresIn: "1m" });
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const base = `http://127.0.0.1:${server.address().port}/api/ai`;
    const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
    const destinations = await fetch(`${base}/destinations`, { headers, signal: AbortSignal.timeout(10000) });
    const coverage = await destinations.json();
    if (!destinations.ok || !coverage.destinations?.length) throw new Error("No covered local destinations");
    const response = await fetch(`${base}/recommend-trail`, { method: "POST", headers, signal: AbortSignal.timeout(10000),
      body: JSON.stringify({ destination: "Misiones", trailTypes: ["cascadas"], duration: "2-4", difficulty: "moderada", experience: "intermedio" }) });
    const result = await response.json();
    if (!response.ok || result.status !== "ok") throw new Error("Local catalog has no match for the documented smoke query");
    const actual = (await pool.query("SELECT name, duration, distance_km FROM trails WHERE id = $1", [result.recommendation.trailId])).rows[0];
    if (!actual || actual.name !== result.recommendation.name || actual.duration !== result.recommendation.duration || Number(actual.distance_km) !== result.recommendation.distanceKm) throw new Error("Response does not match PostgreSQL");
    console.log(JSON.stringify({ status: result.status, method: result.ranking.method, trailId: result.recommendation.trailId,
      realPostgresRecordMatched: true, coveredDestinations: coverage.destinations.length, databaseWrites: 0 }, null, 2));
  } finally {
    if (server.listening) await new Promise((resolve) => server.close(resolve));
    require("../dist/ai/model").localRanker.stop();
    await pool.end();
  }
}
main().catch((error) => { console.error(error.code ? `Local smoke test failed (${error.code})` : error.message); process.exitCode = 1; });

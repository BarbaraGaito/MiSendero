const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const { query } = require("../src/db");
const { cleanupStaleReports, REPORT_STALE_AFTER_DAYS } = require("../src/cleanupStaleReports");
const app = require("../src/server");
const request = require("supertest");

let trailId;

beforeAll(async () => {
  await runMigrations();
  await seedDatabase();

  const { rows } = await query("SELECT id FROM trails LIMIT 1");
  trailId = rows[0].id;

  await query(
    `
      INSERT INTO trail_reports (trail_id, issue_summary, severity, trail_state, created_at)
      VALUES
        ($1, 'Reporte viejo', 'Media', 'Precaucion', now() - ($2 || ' days')::interval),
        ($1, 'Reporte reciente', 'Leve', 'Transitable', now())
    `,
    [trailId, REPORT_STALE_AFTER_DAYS + 5]
  );
});

describe("cleanupStaleReports", () => {
  test("GET /:id/reports excludes reports older than the staleness window", async () => {
    const response = await request(app).get(`/api/trails/${trailId}/reports`);

    expect(response.status).toBe(200);
    expect(response.body.some((report) => report.issue_summary === "Reporte viejo")).toBe(false);
    expect(response.body).toHaveLength(1);
    expect(response.body[0].severity).toBe("Leve");
    expect(response.body[0].issue_summary).toBe("Incidente de terreno");
  });

  test("cleanupStaleReports deletes only the reports past the staleness window", async () => {
    const removed = await cleanupStaleReports();

    expect(removed).toBeGreaterThanOrEqual(1);

    const { rows } = await query("SELECT issue_summary FROM trail_reports WHERE trail_id = $1", [
      trailId,
    ]);

    expect(rows.some((row) => row.issue_summary === "Reporte viejo")).toBe(false);
    expect(rows.some((row) => row.issue_summary === "Reporte reciente")).toBe(true);
  });
});

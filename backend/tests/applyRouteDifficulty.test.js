const fs = require("fs");
const os = require("os");
const path = require("path");
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const { query } = require("../src/db");
const applyRouteDifficultyPredictions = require("../src/applyRouteDifficulty");

let fixturePath;

beforeAll(async () => {
  await runMigrations();
  await seedDatabase();
});

afterEach(() => {
  if (fixturePath && fs.existsSync(fixturePath)) {
    fs.rmSync(fixturePath);
  }
});

describe("applyRouteDifficultyPredictions", () => {
  test("updates trails.difficulty for matching route names and skips unknown ones", async () => {
    const { rows } = await query("SELECT id, name FROM trails LIMIT 1");
    const trail = rows[0];

    fixturePath = path.join(os.tmpdir(), `predictions-${Date.now()}.json`);
    fs.writeFileSync(
      fixturePath,
      JSON.stringify([
        { route_name: trail.name, difficulty: "Alta", confidence: 0.97 },
        { route_name: "Sendero que no existe", difficulty: "Baja", confidence: 0.5 },
      ])
    );

    const result = await applyRouteDifficultyPredictions(fixturePath);

    expect(result.total).toBe(2);
    expect(result.updated).toBe(1);

    const { rows: updatedRows } = await query("SELECT difficulty FROM trails WHERE id = $1", [
      trail.id,
    ]);
    expect(updatedRows[0].difficulty).toBe("Alta");
  });

  test("throws a clear error when the predictions file is missing", async () => {
    await expect(
      applyRouteDifficultyPredictions(path.join(os.tmpdir(), "does-not-exist.json"))
    ).rejects.toThrow(/no se encontraron predicciones/i);
  });
});

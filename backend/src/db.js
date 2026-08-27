const { Pool } = require("pg");

let poolPromise = null;

const createRealPool = () => {
  if (!process.env.DATABASE_URL && !process.env.PGHOST) {
    throw new Error(
      "DATABASE_URL (or PGHOST/PGUSER/PGPASSWORD/PGDATABASE) must be set. Copy backend/.env.example to backend/.env."
    );
  }

  return new Pool({
    connectionString: process.env.DATABASE_URL,
    max: Number(process.env.PG_POOL_MAX || 10),
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
  });
};

// pg-mem provides an in-memory Postgres-compatible engine so the test suite can run
// the same SQL as production without Docker/a real Postgres server available.
const createTestPool = async () => {
  const { newDb } = require("pg-mem");
  const mem = newDb({ autoCreateForeignKeyIndices: true });

  return mem.adapters.createPg().Pool;
};

const getPool = async () => {
  if (!poolPromise) {
    poolPromise =
      process.env.NODE_ENV === "test"
        ? createTestPool().then((TestPool) => new TestPool())
        : Promise.resolve(createRealPool());
  }

  return poolPromise;
};

const query = async (text, params) => {
  const pool = await getPool();
  return pool.query(text, params);
};

// Test-only escape hatch: lets each test file start from a fresh in-memory database.
const resetForTests = () => {
  poolPromise = null;
};

module.exports = { getPool, query, resetForTests };

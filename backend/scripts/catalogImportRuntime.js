const path = require("node:path");

const normalizeName = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

function duplicate(entry, rows) {
  const names = new Set([entry.name, ...entry.provenance.aliases].map(normalizeName));
  return rows.find((row) => row.provenance?.catalog_key === entry.provenance.catalog_key ||
    [row.name, ...(row.provenance?.aliases || [])].some((name) => names.has(normalizeName(name))));
}

function assertLocalDatabase(env = process.env) {
  let host;
  try { host = env.DATABASE_URL ? new URL(env.DATABASE_URL).hostname : env.PGHOST; }
  catch { throw new Error("Invalid database configuration (credentials omitted)"); }
  if (!["localhost", "127.0.0.1", "[::1]", "::1"].includes(host)) {
    throw new Error("Local-only import refused: target is not a loopback database. RDS was not modified.");
  }
}

function databaseTarget(env = process.env) {
  let host = env.PGHOST, port = env.PGPORT || "5432", database = env.PGDATABASE;
  if (env.DATABASE_URL) {
    try {
      const url = new URL(env.DATABASE_URL);
      if (!["postgres:", "postgresql:"].includes(url.protocol) || ["host", "port", "database", "dbname"].some((key) => url.searchParams.has(key))) throw new Error();
      host = url.hostname; port = url.port || "5432"; database = decodeURIComponent(url.pathname.slice(1));
    } catch { throw new Error("Invalid database target configuration (credentials omitted)"); }
  }
  if (!host || !database || /[\s/]/.test(host) || !/^\d+$/.test(String(port)) || Number(port) < 1 || Number(port) > 65535) {
    throw new Error("Set an explicit database host, port and database name using the existing server configuration.");
  }
  // Only non-secret connection identity; never include username, password or URL options.
  return `${host.toLowerCase()}:${Number(port)}/${database}`;
}

function importOptions(args, env = process.env) {
  const confirmation = args.filter((arg) => arg.startsWith("--confirm-target="));
  const allowed = ["--apply", "--dry-run", "--local-only", "--remote"];
  if (args.some((arg) => !allowed.includes(arg) && !arg.startsWith("--confirm-target=")) ||
      new Set(args).size !== args.length || confirmation.length > 1 ||
      (args.includes("--apply") && args.includes("--dry-run")) ||
      (args.includes("--remote") && args.includes("--local-only"))) {
    throw new Error("Usage: --dry-run | --apply [--local-only | --remote --confirm-target=HOST:PORT/DATABASE]");
  }
  const apply = args.includes("--apply"), remote = args.includes("--remote");
  if (!remote) {
    if (confirmation.length) throw new Error("Target confirmation requires --remote");
    if (apply && !args.includes("--local-only")) throw new Error("Apply requires --local-only or explicit --remote target confirmation");
    assertLocalDatabase(env);
    return { apply, remote, target: databaseTarget(env) };
  }
  if (env.NODE_ENV === "test") throw new Error("Remote import cannot use the in-memory test database");
  const target = databaseTarget(env);
  if (apply && confirmation[0]?.slice("--confirm-target=".length) !== target) {
    throw new Error("Remote apply refused: copy the exact target from --remote --dry-run into --confirm-target=HOST:PORT/DATABASE");
  }
  if (!apply && confirmation.length) throw new Error("Target confirmation is only accepted with --apply");
  return { apply, remote, target };
}

async function runCatalogCli(operation, { backendRoot = path.resolve(__dirname, "..") } = {}) {
  require("dotenv").config({ path: path.resolve(backendRoot, ".env"), quiet: true });
  const options = importOptions(process.argv.slice(2));
  const { getPool } = require(path.resolve(backendRoot, "src/db"));
  const pool = await getPool();
  try {
    const client = await pool.connect();
    try {
      // Check the effective pg connection, not just the URL supplied to the command.
      const actual = databaseTarget({ PGHOST: client.connectionParameters.host, PGPORT: client.connectionParameters.port, PGDATABASE: client.connectionParameters.database });
      if (actual !== options.target) throw new Error("Effective database differs from the confirmed target; import refused.");
      await client.query("SET statement_timeout = '15s'");
      await client.query("SET lock_timeout = '5s'");
      if (!options.apply) await client.query("SET default_transaction_read_only = on");
      console.log(JSON.stringify({ target: actual, ...await operation(client, { apply: options.apply }) }, null, 2));
    }
    finally { client.release(); }
  } finally { await pool.end(); }
}

module.exports = { normalizeName, duplicate, assertLocalDatabase, databaseTarget, importOptions, runCatalogCli };


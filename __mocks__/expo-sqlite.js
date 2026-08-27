// Jest-only stand-in for expo-sqlite, backed by Node's built-in synchronous
// SQLite (node:sqlite, available since Node 22). Real device code never runs
// this file - it exists purely so services/database code can be exercised in
// tests without the native expo-sqlite binary.
const { DatabaseSync } = require("node:sqlite");

const databasesByName = new Map();

const wrap = (nativeDb) => ({
  execAsync: async (sql) => {
    nativeDb.exec(sql);
  },
  runAsync: async (sql, params = []) => {
    const info = nativeDb.prepare(sql).run(...params);
    return { lastInsertRowId: Number(info.lastInsertRowid), changes: info.changes };
  },
  getAllAsync: async (sql, params = []) => nativeDb.prepare(sql).all(...params),
  getFirstAsync: async (sql, params = []) => nativeDb.prepare(sql).get(...params) ?? null,
});

const openDatabaseSync = (name) => {
  if (!databasesByName.has(name)) {
    databasesByName.set(name, new DatabaseSync(":memory:"));
  }

  return wrap(databasesByName.get(name));
};

module.exports = { openDatabaseSync };

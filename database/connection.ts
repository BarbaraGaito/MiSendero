import * as SQLite from "expo-sqlite";

type AsyncDatabase = Pick<SQLite.SQLiteDatabase, "execAsync" | "runAsync" | "getFirstAsync" | "getAllAsync" | "withTransactionAsync">;
let connectionPromise: Promise<SQLite.SQLiteDatabase> | undefined;

const getConnection = () => {
  if (!connectionPromise) {
    // Let the web worker initialize without blocking the UI thread.
    connectionPromise = SQLite.openDatabaseAsync("trekking.db").catch((error) => {
      connectionPromise = undefined;
      throw error;
    });
  }
  return connectionPromise;
};

const forward = <K extends keyof AsyncDatabase>(method: K): AsyncDatabase[K] =>
  (async (...args: unknown[]) => {
    const connection = await getConnection();
    return Reflect.apply(connection[method], connection, args);
  }) as AsyncDatabase[K];

export const db: AsyncDatabase = {
  withTransactionAsync: forward("withTransactionAsync"),
  execAsync: forward("execAsync"),
  runAsync: forward("runAsync"),
  getFirstAsync: forward("getFirstAsync"),
  getAllAsync: forward("getAllAsync"),
};

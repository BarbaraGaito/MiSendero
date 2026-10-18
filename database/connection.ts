import type * as SQLite from "expo-sqlite";
import { Platform } from "react-native";
import { openProtectedDatabase } from "./protectedStorage";

export type SqlExecutor = Pick<SQLite.SQLiteDatabase, "execAsync" | "runAsync" | "getFirstAsync" | "getAllAsync">;
type AsyncDatabase = SqlExecutor & Pick<SQLite.SQLiteDatabase, "withTransactionAsync">;
let connectionPromise: Promise<SQLite.SQLiteDatabase> | undefined;
const getConnection = () => connectionPromise ??= openProtectedDatabase().catch((error) => {
  connectionPromise = undefined; throw error;
});
const forward = <K extends keyof AsyncDatabase>(method: K): AsyncDatabase[K] =>
  (async (...args: unknown[]) => {
    const connection = await getConnection();
    return Reflect.apply(connection[method], connection, args);
  }) as AsyncDatabase[K];
export const db: AsyncDatabase = {
  withTransactionAsync: forward("withTransactionAsync"), execAsync: forward("execAsync"),
  runAsync: forward("runAsync"), getFirstAsync: forward("getFirstAsync"), getAllAsync: forward("getAllAsync"),
};

// An owned native connection keeps unrelated writes outside this transaction.
let writes: Promise<unknown> = Promise.resolve();
export const withWriteTransaction = <T>(work: (tx: SqlExecutor) => Promise<T>): Promise<T> => {
  const result = writes.then(async () => {
    const main = await getConnection();
    const tx = Platform.OS === "web" ? main : await openProtectedDatabase(true);
    try {
      await tx.execAsync("BEGIN IMMEDIATE");
      try {
        const value = await work(tx);
        await tx.execAsync("COMMIT");
        return value;
      } catch (error) { await tx.execAsync("ROLLBACK"); throw error; }
    } finally { if (tx !== main) await tx.closeAsync(); }
  });
  writes = result.catch(() => undefined);
  return result;
};

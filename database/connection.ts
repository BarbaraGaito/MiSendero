import type * as SQLite from "expo-sqlite";
import { Platform } from "react-native";
import { openProtectedDatabase, releaseProtectedDatabase } from "./protectedStorage";

export type SqlExecutor = Pick<SQLite.SQLiteDatabase, "execAsync" | "runAsync" | "getFirstAsync" | "getAllAsync">;
type AsyncDatabase = SqlExecutor & Pick<SQLite.SQLiteDatabase, "withTransactionAsync">;
let connectionPromise: Promise<SQLite.SQLiteDatabase> | undefined;
let suspended = false;
let lifecycleGeneration = 0;
let activeOperations = 0;
let suspendPromise: Promise<void> | null = null;
let suspensionFailure: unknown = null;
let idleResolvers: Array<() => void> = [];
const completedOperation = () => {
  activeOperations -= 1;
  if (!activeOperations) { const resolvers=idleResolvers;idleResolvers=[];resolvers.forEach(resolve=>resolve()); }
};
const assertStorageAvailable = () => { if (suspended) throw new Error("El almacenamiento protegido está suspendido. Volvé a abrir la app con el equipo desbloqueado."); };
const getConnection = () => connectionPromise ??= openProtectedDatabase().catch((error) => {
  connectionPromise = undefined; throw error;
});
const forward = <K extends keyof AsyncDatabase>(method: K): AsyncDatabase[K] =>
  (async (...args: unknown[]) => {
    assertStorageAvailable();
    activeOperations += 1;
    try {
      const connection = await getConnection();
      return await Reflect.apply(connection[method], connection, args);
    } finally { completedOperation(); }
  }) as AsyncDatabase[K];
export const db: AsyncDatabase = {
  withTransactionAsync: forward("withTransactionAsync"), execAsync: forward("execAsync"),
  runAsync: forward("runAsync"), getFirstAsync: forward("getFirstAsync"), getAllAsync: forward("getAllAsync"),
};

// An owned native connection keeps unrelated writes outside this transaction.
let writes: Promise<unknown> = Promise.resolve();
export const withWriteTransaction = <T>(work: (tx: SqlExecutor) => Promise<T>): Promise<T> => {
  const result = writes.then(async () => {
    assertStorageAvailable();
    activeOperations += 1;
    try {
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
    } finally { completedOperation(); }
  });
  writes = result.catch(() => undefined);
  return result;
};

export const suspendProtectedStorage = () => {
  suspended = true;
  lifecycleGeneration += 1;
  return suspendPromise ??= (async () => {
    if (activeOperations) await new Promise<void>(resolve => idleResolvers.push(resolve));
    await writes.catch(() => undefined);
    if (Platform.OS !== "web") {
      connectionPromise = undefined;
      await releaseProtectedDatabase();
    }
    suspensionFailure = null;
  })().catch(error => { suspensionFailure = error; throw error; }).finally(() => { suspendPromise = null; });
};
export const resumeProtectedStorage = async () => {
  const generation = ++lifecycleGeneration;
  await suspendPromise;
  if (suspensionFailure) {
    await releaseProtectedDatabase();
    suspensionFailure = null;
  }
  if (generation === lifecycleGeneration) suspended = false;
};

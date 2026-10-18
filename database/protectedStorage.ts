import * as SQLite from "expo-sqlite";
import { File } from "expo-file-system";
import * as SecureStore from "expo-secure-store";
import { randomUUID } from "expo-crypto";
import { Platform } from "react-native";

const KEY_NAME = "misendero.sqlite.key.v1";
const SECURE_DB = "trekking-secure-v1.db";
const LEGACY_DB = "trekking.db";
const MARKER = "_misendero_encrypted_migration";
let keyPromise: Promise<string> | undefined;
let migration: Promise<SQLite.SQLiteDatabase> | undefined;
const secret = () => keyPromise ??= (async () => {
  if (!await SecureStore.isAvailableAsync()) throw new Error("El almacenamiento seguro no está disponible. No se abrió una base sin cifrar.");
  let key = await SecureStore.getItemAsync(KEY_NAME);
  if (!key) {
    key = randomUUID().replace(/-/g, "") + randomUUID().replace(/-/g, "");
    await SecureStore.setItemAsync(KEY_NAME, key, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
  }
  if (!/^[a-f0-9]{64}$/i.test(key)) throw new Error("La clave local no es válida. Se preservó la base existente.");
  return key;
})().catch((error) => { keyPromise = undefined; throw error; });

const openKeyed = async (key: string, useNewConnection = false) => {
  const connection = await SQLite.openDatabaseAsync(SECURE_DB, { useNewConnection });
  try {
    await connection.execAsync(`PRAGMA key = "x'${key}'"`);
    const version = await connection.getFirstAsync<Record<string, unknown>>("PRAGMA cipher_version");
    if (!version || !Object.values(version).some(Boolean)) throw new Error("Esta build no incluye SQLCipher. Generá una build nativa; no se permite SQLite sin cifrar.");
    await connection.getFirstAsync("SELECT count(*) FROM sqlite_master");
    await connection.execAsync("PRAGMA busy_timeout = 5000; PRAGMA secure_delete = ON;");
    return connection;
  } catch (error) { await connection.closeAsync(); throw error; }
};

const initialize = async () => {
  const key = await secret();
  let secure = await openKeyed(key);
  let secureClosed = false;
  try {
    const ready = await secure.getFirstAsync<{ name: string }>("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", [MARKER]);
    if (!ready) {
      const legacy = await SQLite.openDatabaseAsync(LEGACY_DB, { useNewConnection: true });
      try {
        const objects = await secure.getFirstAsync<{ count: number }>("SELECT count(*) AS count FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'");
        if (objects?.count) throw new Error("La copia cifrada incompleta requiere recuperación; no se sobrescribieron datos.");
        const path = secure.databasePath.replace(/'/g, "''");
        await secure.closeAsync(); secureClosed = true;
        const userVersion = await legacy.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
        await legacy.execAsync(`ATTACH DATABASE '${path}' AS encrypted KEY "x'${key}'"`);
        try {
          await legacy.execAsync("BEGIN IMMEDIATE");
          try {
            await legacy.getFirstAsync("SELECT sqlcipher_export('encrypted')");
            await legacy.execAsync(`PRAGMA encrypted.user_version = ${Number(userVersion?.user_version ?? 0)};
              CREATE TABLE encrypted.${MARKER} (version INTEGER NOT NULL);
              INSERT INTO encrypted.${MARKER} VALUES (1);`);
            await legacy.execAsync("COMMIT");
          } catch (error) { await legacy.execAsync("ROLLBACK"); throw error; }
        } finally { await legacy.execAsync("DETACH DATABASE encrypted"); }
        await legacy.execAsync("PRAGMA wal_checkpoint(TRUNCATE)");
      } finally { await legacy.closeAsync(); }
      secure = await openKeyed(key); secureClosed = false;
    }
    const integrity = await secure.getFirstAsync<Record<string, unknown>>("PRAGMA integrity_check");
    const cipherErrors = await secure.getAllAsync("PRAGMA cipher_integrity_check");
    if (!integrity || !Object.values(integrity).includes("ok") || cipherErrors.length) {
      throw new Error("La copia cifrada no pasó la verificación; se conservó la base anterior.");
    }
    // Copy -> validate -> remove. Failure is visible; the verified copy remains.
    try {
      if (new File(SQLite.defaultDatabaseDirectory, LEGACY_DB).exists) {
        await SQLite.deleteDatabaseAsync(LEGACY_DB);
      }
      // Expo deletes the main file only. A crash may leave plaintext sidecars.
      for (const suffix of ["-wal", "-shm", "-journal"]) {
        const file = new File(SQLite.defaultDatabaseDirectory, LEGACY_DB + suffix);
        if (file.exists) file.delete();
      }
    } catch {
      throw new Error("La base cifrada está verificada, pero falta retirar la copia anterior y sus archivos auxiliares.");
    }
    return secure;
  } catch (error) { if (!secureClosed) await secure.closeAsync(); throw error; }
};

export const openProtectedDatabase = async (useNewConnection = false) => {
  // Web is a volatile preview; no contacts, tracks or health persist in cleartext.
  if (Platform.OS === "web") return SQLite.openDatabaseAsync(":memory:");
  migration ??= initialize().catch((error) => { migration = undefined; throw error; });
  const connection = await migration;
  return useNewConnection ? openKeyed(await secret(), true) : connection;
};

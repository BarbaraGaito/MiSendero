import { db } from "../database/database";

export interface FavoriteTrail {
  trailId: number;
  createdAt: number;
}

const initFavoriteTrailsTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS favorite_trails (
      trail_id INTEGER PRIMARY KEY,
      created_at INTEGER NOT NULL
    );
  `);
};

export const getFavoriteTrailIds = async (): Promise<number[]> => {
  await initFavoriteTrailsTable();

  const rows = await db.getAllAsync<{ trail_id: number }>(
    `SELECT trail_id FROM favorite_trails ORDER BY created_at DESC`
  );

  return rows.map((row) => row.trail_id);
};

export const isTrailFavorite = async (trailId: number): Promise<boolean> => {
  await initFavoriteTrailsTable();

  const row = await db.getFirstAsync<{ trail_id: number }>(
    `SELECT trail_id FROM favorite_trails WHERE trail_id = ? LIMIT 1`,
    [trailId]
  );

  return Boolean(row);
};

export const setTrailFavorite = async (
  trailId: number,
  favorite: boolean
): Promise<boolean> => {
  await initFavoriteTrailsTable();

  if (!favorite) {
    await db.runAsync(`DELETE FROM favorite_trails WHERE trail_id = ?`, [trailId]);
    return false;
  }

  await db.runAsync(
    `INSERT OR REPLACE INTO favorite_trails (trail_id, created_at)
     VALUES (?, ?)`,
    [trailId, Date.now()]
  );

  return true;
};


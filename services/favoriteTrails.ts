import { getAuthSession } from "./authSession";
import { db } from "../database/database";

export interface FavoriteTrail {
  trailId: number;
  createdAt: number;
}

const initFavoriteTrailsTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS user_favorite_trails (
      user_id INTEGER NOT NULL,
      trail_id INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      PRIMARY KEY (user_id, trail_id)
    );
  `);
};

export const getFavoriteTrailIds = async (): Promise<number[]> => {
  await initFavoriteTrailsTable();
  const userId = (await getAuthSession())?.user.id ?? null;

  const rows = await db.getAllAsync<{ trail_id: number }>(
    `SELECT trail_id FROM user_favorite_trails WHERE user_id = ? ORDER BY created_at DESC`, [userId]
  );

  return rows.map((row) => row.trail_id);
};

export const isTrailFavorite = async (trailId: number): Promise<boolean> => {
  await initFavoriteTrailsTable();
  const userId = (await getAuthSession())?.user.id ?? null;

  const row = await db.getFirstAsync<{ trail_id: number }>(
    `SELECT trail_id FROM user_favorite_trails WHERE user_id = ? AND trail_id = ? LIMIT 1`,
    [userId, trailId]
  );

  return Boolean(row);
};

export const setTrailFavorite = async (
  trailId: number,
  favorite: boolean
): Promise<boolean> => {
  await initFavoriteTrailsTable();
  const userId = (await getAuthSession())?.user.id ?? null;

  if (!userId) throw new Error("Iniciá sesión para guardar favoritos.");

  if (!favorite) {
    await db.runAsync(`DELETE FROM user_favorite_trails WHERE user_id = ? AND trail_id = ?`, [userId, trailId]);
    return false;
  }

  await db.runAsync(
    `INSERT OR REPLACE INTO user_favorite_trails (user_id, trail_id, created_at)
     VALUES (?, ?, ?)`,
    [userId, trailId, Date.now()]
  );

  return true;
};


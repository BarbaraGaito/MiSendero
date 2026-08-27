import { initDB } from "../../database/database";
import {
  getFavoriteTrailIds,
  isTrailFavorite,
  setTrailFavorite,
} from "../favoriteTrails";

beforeAll(async () => {
  await initDB();
});

describe("favoriteTrails", () => {
  test("stores and removes favorite trails locally", async () => {
    const trailId = 98765;

    expect(await isTrailFavorite(trailId)).toBe(false);

    await setTrailFavorite(trailId, true);
    expect(await isTrailFavorite(trailId)).toBe(true);
    expect(await getFavoriteTrailIds()).toContain(trailId);

    await setTrailFavorite(trailId, false);
    expect(await isTrailFavorite(trailId)).toBe(false);
  });
});


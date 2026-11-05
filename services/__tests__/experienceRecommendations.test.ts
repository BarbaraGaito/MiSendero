import { ExperienceLevel, ExperienceProfile, getRecommendedTrailForProfile } from "../experienceProfile";
import { trail } from "../../testing/fixtures";

const profile = (level: ExperienceLevel): ExperienceProfile => ({
  completed: true, skipped: false, level, answers: {},
  completedAt: 1, skippedAt: null, updatedAt: 1,
});
const easy = { ...trail, id: 1, difficulty: "Baja" };
const medium = { ...trail, id: 2, difficulty: "Media" };
const hard = { ...trail, id: 3, difficulty: "Alta" };

test.each([
  ["principiante", easy], ["intermedio", medium], ["avanzado", hard],
] as const)("home chooses the closest difficulty for %s regardless of catalog order", (level, expected) => {
  for (const catalog of [[easy, medium, hard], [hard, easy, medium], [medium, hard, easy]]) {
    expect(getRecommendedTrailForProfile(catalog, profile(level))).toBe(expected);
  }
});

test("missing target difficulties fall back only to lower levels", () => {
  expect(getRecommendedTrailForProfile([easy, medium], profile("avanzado"))).toBe(medium);
  expect(getRecommendedTrailForProfile([hard, easy], profile("intermedio"))).toBe(easy);
  expect(getRecommendedTrailForProfile([hard], profile("intermedio"))).toBeNull();
  expect(getRecommendedTrailForProfile([hard, medium], profile("principiante"))).toBeNull();
  expect(getRecommendedTrailForProfile([], profile("avanzado"))).toBeNull();
});

test("unknown difficulty and incomplete or skipped profiles never produce a recommendation", () => {
  expect(getRecommendedTrailForProfile([{ ...easy, difficulty: "A confirmar" }], profile("avanzado"))).toBeNull();
  for (const change of [{ completed: false }, { skipped: true }, { level: null }]) {
    expect(getRecommendedTrailForProfile([easy], { ...profile("principiante"), ...change })).toBeNull();
  }
  const formatted = { ...medium, difficulty: "  MEDIA  " };
  expect(getRecommendedTrailForProfile([easy, formatted], profile("intermedio"))).toBe(formatted);
});

test("a usable photo takes priority among compatible routes, including when the best-level photo fails", () => {
  const easyPhoto = { ...easy, image_url: "https://images.example.test/easy.jpg" };
  const hardPhoto = { ...hard, image_url: "https://images.example.test/hard.jpg" };
  const mediumWithoutPhoto = { ...medium, image_url: null };
  expect(getRecommendedTrailForProfile([mediumWithoutPhoto, easyPhoto], profile("intermedio"))).toBe(easyPhoto);
  expect(getRecommendedTrailForProfile([easyPhoto, hardPhoto], profile("avanzado"))).toBe(hardPhoto);
  expect(getRecommendedTrailForProfile([hardPhoto, easyPhoto], profile("avanzado"), new Set([hardPhoto.image_url]))).toBe(easyPhoto);
  expect(getRecommendedTrailForProfile([hardPhoto, { ...easy, image_url: null }], profile("principiante"))?.id).toBe(easy.id);
  expect(getRecommendedTrailForProfile([hardPhoto], profile("principiante"))).toBeNull();
});

import { getAuthSession } from "./authSession";
import { db } from "../database/connection";
import { Trail } from "../types";


export type ExperienceLevel = "principiante" | "intermedio" | "avanzado";

export interface ExperienceProfile {
  completed: boolean;
  skipped: boolean;
  level: ExperienceLevel | null;
  answers: Record<string, string>;
  completedAt: number | null;
  skippedAt: number | null;
  updatedAt: number | null;
}

const defaultProfile: ExperienceProfile = {
  completed: false,
  skipped: false,
  level: null,
  answers: {},
  completedAt: null,
  skippedAt: null,
  updatedAt: null,
};

const initExperienceProfileTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS user_experience_profile (
      id INTEGER PRIMARY KEY,
      completed INTEGER NOT NULL DEFAULT 0,
      skipped INTEGER NOT NULL DEFAULT 0,
      experience_level TEXT,
      answers_json TEXT,
      completed_at INTEGER,
      skipped_at INTEGER,
      updated_at INTEGER
    );
  `);
};

export const getExperienceProfile = async (): Promise<ExperienceProfile> => {
  await initExperienceProfileTable();

  const row = await db.getFirstAsync<{
    completed: number;
    skipped: number;
    experience_level: string | null;
    answers_json: string | null;
    completed_at: number | null;
    skipped_at: number | null;
    updated_at: number | null;
  }>(
    `SELECT
       completed,
       skipped,
       experience_level,
       answers_json,
       completed_at,
       skipped_at,
       updated_at
     FROM user_experience_profile
     WHERE id = ?`, [(await getAuthSession())?.user.id ?? null]
  );

  if (!row) return defaultProfile;

  return {
    completed: row.completed === 1,
    skipped: row.skipped === 1,
    level: toExperienceLevel(row.experience_level),
    answers: row.answers_json ? JSON.parse(row.answers_json) : {},
    completedAt: row.completed_at ?? null,
    skippedAt: row.skipped_at ?? null,
    updatedAt: row.updated_at ?? null,
  };
};

export const saveExperienceProfile = async (
  answers: Record<string, string>
) => {
  await initExperienceProfileTable();

  const level = calculateExperienceLevel(answers);
  const now = Date.now();

  await db.runAsync(
    `INSERT OR REPLACE INTO user_experience_profile (
       id,
       completed,
       skipped,
       experience_level,
       answers_json,
       completed_at,
       skipped_at,
       updated_at
     )
     VALUES (?, 1, 0, ?, ?, ?, NULL, ?)`,
    [(await getAuthSession())?.user.id ?? -1, level, JSON.stringify(answers), now, now]
  );

  return getExperienceProfile();
};

export const skipExperienceProfile = async () => {
  await initExperienceProfileTable();

  const now = Date.now();

  await db.runAsync(
    `INSERT OR REPLACE INTO user_experience_profile (
       id,
       completed,
       skipped,
       experience_level,
       answers_json,
       completed_at,
       skipped_at,
       updated_at
     )
     VALUES (?, 0, 1, NULL, NULL, NULL, ?, ?)`,
    [(await getAuthSession())?.user.id ?? -1, now, now]
  );
};

export const calculateExperienceLevel = (
  answers: Record<string, string>
): ExperienceLevel => {
  const score = Object.values(answers).reduce((total, answer) => {
    if (answer.includes("alta") || answer.includes("larga") || answer.includes("tecnico")) {
      return total + 2;
    }

    if (answer.includes("media") || answer.includes("moderada") || answer.includes("ocasional")) {
      return total + 1;
    }

    return total;
  }, 0);

  if (score >= 6) return "avanzado";
  if (score >= 3) return "intermedio";
  return "principiante";
};

export const getRecommendedTrailForProfile = (
  trails: Trail[],
  profile: ExperienceProfile
) => {
  if (!profile.completed || !profile.level) return null;

  const preferredDifficulties: Record<ExperienceLevel, string[]> = {
    principiante: ["baja"],
    intermedio: ["media", "baja"],
    avanzado: ["alta", "media", "baja"],
  };
  const difficulties = preferredDifficulties[profile.level];

  return (
    trails.find((trail) =>
      difficulties.some((difficulty) =>
        trail.difficulty.toLowerCase().includes(difficulty)
      )
    ) ||
    trails[0] ||
    null
  );
};

export const getTrailRecommendationReasons = (
  trail: Trail | null,
  profile: ExperienceProfile
) => {
  if (!trail || !profile.completed || !profile.level) return [];

  const reasons = [
    `Nivel ${profile.level}: dificultad ${trail.difficulty.toLowerCase()}.`,
  ];

  if (typeof trail.distance_km === "number") {
    reasons.push(
      trail.distance_km <= 5
        ? "Distancia corta para una salida controlada."
        : trail.distance_km <= 10
          ? "Distancia moderada acorde a una caminata planificada."
          : "Ruta larga sugerida solo con margen de luz y preparacion."
    );
  }

  if (trail.duration) {
    reasons.push(`Duracion estimada: ${trail.duration}.`);
  }

  if (profile.answers.preferencia_offline || profile.answers.offline) {
    reasons.push("Compatible con planificacion offline previa.");
  }

  return reasons.slice(0, 3);
};

const toExperienceLevel = (value: string | null): ExperienceLevel | null => {
  if (value === "principiante" || value === "intermedio" || value === "avanzado") {
    return value;
  }

  return null;
};

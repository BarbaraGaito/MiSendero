import { randomUUID } from "expo-crypto";
import { db, withWriteTransaction } from "../database/connection";
import { initDB } from "../database/database";
import type { SqlExecutor } from "../database/connection";
import { captureAccountContext, assertAccountContext, type AccountContext } from "./accountContext";
import { isAccountDeletionPending } from "./accountLifecycle";
import { getPrivacyPreferences } from "./privacyConsent";
import { getRouteSession, getActiveRouteSession } from "./routeSession";
import { getWearableConnection } from "./wearableMetrics";
import { readNativeFieldSamples } from "./nativeWearableBridge";
import { completedHeartRateWindow, freshMorningPair } from "./fieldSensorWindow";
import { fatigueInputs, fieldUnavailable, predictFieldModel, type BorgCheckin, type FieldPrediction } from "../ai/fieldInference";
import { fieldModels, amsBinaryDecisionSupported } from "../ai/fieldRegistry";
import type { DeviceLocation } from "./deviceLocation";

export interface FieldSnapshot {
  enabled: boolean;
  reason: string | null;
  checkins: BorgCheckin[];
  fatigue: FieldPrediction;
  reminderDue: boolean;
}

async function access(): Promise<AccountContext> {
  const context = await captureAccountContext();
  if (!context.userId) throw new Error("Iniciá sesión para guardar tus controles.");
  await initDB();
  if (!(await getPrivacyPreferences(context)).sensitiveDataConsent || await isAccountDeletionPending(context.userId)) throw new Error("Habilitá el consentimiento para métricas de salud desde tu perfil.");
  assertAccountContext(context);
  return context;
}

async function writable(context: AccountContext, tx: SqlExecutor) {
  assertAccountContext(context);
  const consent = await tx.getFirstAsync<{ sensitive_data_consent: number }>("SELECT sensitive_data_consent FROM user_privacy_preferences WHERE id = ?", [context.userId]);
  const deleting = await tx.getFirstAsync("SELECT user_id FROM account_deletion_state WHERE user_id = ?", [context.userId]);
  if (consent?.sensitive_data_consent !== 1 || deleting) throw new Error("El permiso para guardar métricas cambió. Revisá tus preferencias.");
  assertAccountContext(context);
}

async function realSession(trailId: number, startedAt: number, context: AccountContext) {
  if (!Number.isInteger(trailId) || trailId <= 0 || !Number.isFinite(startedAt) || startedAt <= 0) throw new Error("Iniciá un recorrido real para registrar esfuerzo.");
  const session = await getRouteSession(trailId, startedAt);
  assertAccountContext(context);
  if (!session || session.simulated || session.state === "completed") throw new Error("Los controles de prueba no se guardan en el historial real.");
  return session;
}

export async function saveBorgCheckin(trailId: number, startedAt: number, borg: number, now = Date.now()) {
  if (!Number.isFinite(borg) || borg < 0 || borg > 10 || !Number.isFinite(now) || now < startedAt || now > Date.now()+30000) throw new Error("Ingresá un esfuerzo real entre 0 y 10 con fecha válida.");
  const context = await access();
  await realSession(trailId, startedAt, context);
  const id = randomUUID();
  await withWriteTransaction(async tx => {
    await writable(context, tx);
    await tx.runAsync("INSERT INTO fatigue_checkins(id,user_id,trail_id,started_at,borg,recorded_at,created_at) VALUES(?,?,?,?,?,?,?)",
      [id, context.userId, trailId, startedAt, borg, now, now]);
  });
  return { borg, recordedAt: now };
}

async function checkinsFor(context: AccountContext, trailId: number, startedAt: number, now: number) {
  const rows = await db.getAllAsync<{ borg: number; recorded_at: number }>(
    "SELECT borg,recorded_at FROM fatigue_checkins WHERE user_id = ? AND trail_id = ? AND started_at = ? AND recorded_at <= ? ORDER BY recorded_at DESC LIMIT 50",
    [context.userId, trailId, startedAt, now]);
  assertAccountContext(context);
  return rows.map(row => ({ borg: row.borg, recordedAt: row.recorded_at }));
}

async function sensorSamples(context: AccountContext, now: number) {
  const link = await getWearableConnection(context);
  assertAccountContext(context);
  if (!link.linked || !link.permissionsGranted || link.provider === "development_simulator") return null;
  const samples = await readNativeFieldSamples(now-300000, now);
  assertAccountContext(context);
  return samples;
}

async function persist(context: AccountContext, trailId: number, startedAt: number, result: FieldPrediction, inputs: unknown) {
  if (result.status !== "available" || !result.modelId) return;
  const key = `${result.task}:${result.modelId}:${trailId}:${startedAt}:${Math.floor(result.assessedAt/60000)}`;
  await withWriteTransaction(async tx => {
    await writable(context, tx);
    await tx.runAsync("INSERT OR IGNORE INTO field_model_assessments(id,user_id,trail_id,started_at,task,model_id,assessment_key,result_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
      [randomUUID(), context.userId, trailId, startedAt, result.task, result.modelId, key, JSON.stringify({ result, inputs }), result.assessedAt]);
  });
}

export async function getFieldSnapshot(trailId: number, startedAt: number, now = Date.now()): Promise<FieldSnapshot> {
  let context: AccountContext;
  try { context = await access(); }
  catch (error) {
    const reason = error instanceof Error ? error.message : "No pudimos leer tus controles.";
    return { enabled: false, reason, checkins: [], reminderDue: false, fatigue: fieldUnavailable("fatigue", "missing_inputs", reason, now) };
  }
  const checkins = await checkinsFor(context, trailId, startedAt, now);
  const reminderDue = startedAt > 0 && now >= startedAt && (!checkins.length || now-checkins[0].recordedAt >= 600000);
  if (startedAt <= 0) return { enabled: true, reason: null, checkins, reminderDue: false, fatigue: fieldUnavailable("fatigue", "missing_inputs", "El registro de esfuerzo estará disponible al iniciar el recorrido.", now) };
  await realSession(trailId, startedAt, context);
  const samples = fieldModels.fatigue?.runtime_eligible ? await sensorSamples(context, now) : null;
  const window = completedHeartRateWindow(samples, now);
  const inputs = fatigueInputs(window?.meanBpm ?? null, checkins, now);
  const result = predictFieldModel(fieldModels.fatigue, "fatigue", inputs, "fatigue_recent_borg", now);
  await persist(context, trailId, startedAt, result, { ...inputs, heartRateWindow: window });
  assertAccountContext(context);
  return { enabled: true, reason: null, checkins, reminderDue, fatigue: result };
}

export async function evaluateMorningAms(options: {
  trailId: number; startedAt: number; restedOvernight: boolean; restingNow: boolean;
  beforeAscent: boolean; location: DeviceLocation | null; now?: number;
}): Promise<FieldPrediction> {
  const now = options.now ?? Date.now();
  const context = await access();
  const active = await getActiveRouteSession();
  assertAccountContext(context);
  const hour = new Date(now).getHours();
  if (!options.restedOvernight || !options.restingNow || !options.beforeAscent || hour < 5 || hour >= 12 || active?.simulated || active?.state === "running") {
    return fieldUnavailable("ams", "outside_scope", "Realizá el control por la mañana, en reposo tras la noche y antes de continuar el ascenso.", now, fieldModels.ams);
  }
  if (options.startedAt > 0) await realSession(options.trailId, options.startedAt, context);
  const location = options.location;
  if (!location || !Number.isFinite(location.altitudeM) || location.altitudeM == null || location.altitudeAccuracyM == null ||
      !Number.isFinite(location.altitudeAccuracyM) || location.altitudeAccuracyM < 0 || location.altitudeAccuracyM > 50 ||
      !Number.isFinite(location.timestamp) || location.timestamp > now || now-location.timestamp > 300000) {
    return fieldUnavailable("ams", "missing_inputs", "Se necesita una altitud GPS reciente con precisión vertical de hasta 50 m. El desnivel del sendero no reemplaza esa medición.", now, fieldModels.ams);
  }
  const samples = await sensorSamples(context, now);
  const pair = freshMorningPair(samples, now);
  const inputs = { hr: pair?.hr ?? null, spo2: pair?.spo2 ?? null, altitude_m: location.altitudeM };
  const result = predictFieldModel(fieldModels.ams, "ams", inputs, "ams_morning_next_ascent", now);
  if (result.status === "available" && !amsBinaryDecisionSupported) {
    result.label = null;
    result.reason = "Puntuación orientativa sin clasificación: el umbral evaluado no distinguió los casos negativos del test.";
  }
  await persist(context, options.trailId, options.startedAt, result, { ...inputs, measurement: pair, altitudeAccuracyM: location.altitudeAccuracyM, context: "morning_rest_before_ascent" });
  assertAccountContext(context);
  return result;
}

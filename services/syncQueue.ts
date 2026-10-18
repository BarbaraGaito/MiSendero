import { randomUUID } from "expo-crypto";
import * as Network from "expo-network";
import { db, initDB } from "../database/database";
import { getAuthSession } from "./authSession";
import { createActivity, createEmergencyAlert, createTrailReport, getTrailReports, closeTripPlan, recordPrivacyDecision } from "./api";
import { isAccountDeletionPending } from "./accountLifecycle";
import { refreshOfflineTrailReports, getOfflineMaps } from "./offlineMaps";

export type PendingEntityType = "trail_report" | "activity" | "emergency_alert" | "trip_check_in" | "privacy_decision";
export type PendingStatus = "pending" | "syncing" | "synced" | "failed" | "abandoned";

// After this many failed attempts, an operation stops being retried automatically
// and is surfaced to the user to decide whether to keep waiting or discard it.
export const MAX_RETRY_ATTEMPTS = 5;

export interface PendingOperation {
  id: number;
  userId: number | null;
  entityType: PendingEntityType;
  payload: Record<string, unknown>;
  dedupeKey: string | null;
  status: PendingStatus;
  retryCount: number;
  lastError: string | null;
  serverId: number | null;
  createdAt: number;
  updatedAt: number;
}

export interface SyncSummary {
  pending: number;
  syncing: number;
  synced: number;
  failed: number;
  abandoned: number;
  // Of "failed", how many already hit MAX_RETRY_ATTEMPTS and are no longer
  // retried automatically by runSync().
  exhausted: number;
}

interface PendingOperationRow {
  id: number;
  user_id: number | null;
  entity_type: PendingEntityType;
  payload_json: string;
  dedupe_key: string | null;
  status: PendingStatus;
  retry_count: number;
  last_error: string | null;
  server_id: number | null;
  created_at: number;
  updated_at: number;
}

const toPendingOperation = (row: PendingOperationRow): PendingOperation => ({
  id: row.id,
  userId: row.user_id,
  entityType: row.entity_type,
  payload: JSON.parse(row.payload_json),
  dedupeKey: row.dedupe_key,
  status: row.status,
  retryCount: row.retry_count,
  lastError: row.last_error,
  serverId: row.server_id,
  createdAt: row.created_at,
  updatedAt: row.updated_at,
});

export const enqueue = async (
  entityType: PendingEntityType,
  payload: Record<string, unknown>
): Promise<number> => {
  await initDB();
  const owner = (await getAuthSession())?.user.id ?? null;
  if (owner && await isAccountDeletionPending(owner)) throw new Error("La cuenta tiene una baja pendiente; no se guardan nuevos envíos.");
  if (!owner && entityType !== "emergency_alert") throw new Error("Iniciá sesión para guardar esta operación.");
  if (entityType === "trail_report") {
    const eventId = typeof payload.client_event_id === "string" ? payload.client_event_id : randomUUID();
    return enqueueUnique(entityType, { ...payload, client_event_id: eventId }, `report:${eventId}`);
  }
  const now = Date.now();
  const result = await db.runAsync(
    `INSERT INTO pending_operations (entity_type, payload_json, user_id, status, created_at, updated_at)
     VALUES (?, ?, ?, 'pending', ?, ?)`,
    [entityType, JSON.stringify(payload), owner, now, now]
  );

  return result.lastInsertRowId;
};

export const enqueueUnique = async (
  entityType: PendingEntityType,
  payload: Record<string, unknown>,
  dedupeKey: string
): Promise<number> => {
  await initDB();
  const owner = (await getAuthSession())?.user.id ?? null;
  if (!owner && entityType !== "emergency_alert") throw new Error("Iniciá sesión para guardar esta operación.");
  dedupeKey = `${owner ?? "guest"}:${dedupeKey}`;
  if (owner && await isAccountDeletionPending(owner)) throw new Error("La cuenta tiene una baja pendiente; no se guardan nuevos envíos.");
  const existing = await db.getFirstAsync<{ id: number }>(
    `SELECT id FROM pending_operations
     WHERE dedupe_key = ?
     LIMIT 1`,
    [dedupeKey]
  );

  if (existing) return existing.id;

  const now = Date.now();

  try {
    const result = await db.runAsync(
      `INSERT INTO pending_operations (entity_type, payload_json, dedupe_key, user_id, status, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'pending', ?, ?)`,
      [entityType, JSON.stringify(payload), dedupeKey, owner, now, now]
    );

    return result.lastInsertRowId;
  } catch (error) {
    const racedExisting = await db.getFirstAsync<{ id: number }>(
      `SELECT id FROM pending_operations
       WHERE dedupe_key = ?
       LIMIT 1`,
      [dedupeKey]
    );

    if (racedExisting) return racedExisting.id;

    throw error;
  }
};

export const getPendingOperations = async (): Promise<PendingOperation[]> => {
  await initDB();
  const owner = (await getAuthSession())?.user.id ?? null;
  const rows = await db.getAllAsync<PendingOperationRow>(
    `SELECT * FROM pending_operations
     WHERE user_id = ? AND status IN ('pending', 'failed')
     ORDER BY created_at ASC`, [owner]
  );

  return rows.map(toPendingOperation);
};

const getRetryableOperations = async (owner: number): Promise<PendingOperation[]> => {
  const rows = await db.getAllAsync<PendingOperationRow>(
    `SELECT * FROM pending_operations
     WHERE user_id = ? AND next_attempt_at <= ? AND
       (status = 'pending' OR (status = 'failed' AND (retry_count < ? OR entity_type IN ('emergency_alert', 'trip_check_in'))))
     ORDER BY CASE WHEN entity_type = 'emergency_alert' THEN 0 ELSE 1 END, created_at ASC`,
    [owner, Date.now(), MAX_RETRY_ATTEMPTS]
  );

  return rows.map(toPendingOperation);
};

export const getSyncSummary = async (): Promise<SyncSummary> => {
  await initDB();
  const owner = (await getAuthSession())?.user.id ?? null;
  const rows = await db.getAllAsync<{ status: PendingStatus; count: number }>(
    `SELECT status, COUNT(*) AS count FROM pending_operations WHERE user_id = ? GROUP BY status`, [owner]
  );
  const summary: SyncSummary = {
    pending: 0,
    syncing: 0,
    synced: 0,
    failed: 0,
    abandoned: 0,
    exhausted: 0,
  };

  rows.forEach((row) => {
    summary[row.status] = row.count;
  });

  const exhausted = await db.getFirstAsync<{ count: number }>(
    `SELECT COUNT(*) AS count FROM pending_operations
     WHERE user_id = ? AND entity_type NOT IN ('emergency_alert', 'trip_check_in') AND status = 'failed' AND retry_count >= ?`,
    [owner, MAX_RETRY_ATTEMPTS]
  );
  summary.exhausted = exhausted?.count ?? 0;

  return summary;
};

export const discardExhaustedOperations = async (): Promise<number> => {
  await initDB();
  const owner = (await getAuthSession())?.user.id ?? null;
  const result = await db.runAsync(
    `UPDATE pending_operations
     SET status = 'abandoned', updated_at = ?
     WHERE user_id = ? AND entity_type NOT IN ('emergency_alert', 'trip_check_in') AND status = 'failed' AND retry_count >= ?`,
    [Date.now(), owner, MAX_RETRY_ATTEMPTS]
  );

  return result.changes;
};

export const isOnline = async (): Promise<boolean> => {
  const networkState = await Network.getNetworkStateAsync().catch(() => null);

  return Boolean(networkState?.isConnected) && networkState?.isInternetReachable !== false;
};

const markSyncing = (id: number) =>
  db.runAsync(
    `UPDATE pending_operations SET status = 'syncing', updated_at = ? WHERE id = ?`,
    [Date.now(), id]
  );

const markSynced = (id: number, serverId: number | null) =>
  db.runAsync(
    `UPDATE pending_operations SET status = 'synced', server_id = ?, updated_at = ? WHERE id = ?`,
    [serverId, Date.now(), id]
  );

const markFailed = (id: number, retryCount: number, error: string) =>
  db.runAsync(
    `UPDATE pending_operations
     SET status = 'failed', retry_count = ?, last_error = ?, updated_at = ?, next_attempt_at = ?
     WHERE id = ?`,
    [retryCount, error, Date.now(), Date.now() + Math.min(300000, 5000 * 2 ** Math.min(retryCount - 1, 6)), id]
  );

const dispatchOperation = async (
  operation: PendingOperation,
  token: string
): Promise<number | null> => {
  switch (operation.entityType) {
    case "privacy_decision": {
      await recordPrivacyDecision(operation.payload, token);
      return null;
    }
    case "trip_check_in": {
      const payload = operation.payload as { planId: number; status: "checked_in" | "cancelled" };
      const result = await closeTripPlan(payload.planId, payload.status, token);
      return result.id;
    }
    case "trail_report": {
      const { trailId, ...report } = operation.payload as {
        trailId: number;
        issue_summary: string;
        severity: string;
        trail_state: string;
        cause?: string | null;
        blocks_path?: boolean;
        details?: string;
        latitude?: number | null;
        longitude?: number | null;
        accuracy_meters?: number | null;
        route_progress_meters?: number | null;
      };
      const created = await createTrailReport(trailId, report, token);
      return created.id;
    }
    case "activity": {
      const created = await createActivity(
        operation.payload as Parameters<typeof createActivity>[0],
        token
      );
      return created.id;
    }
    case "emergency_alert": {
      const created = await createEmergencyAlert(
        operation.payload as Parameters<typeof createEmergencyAlert>[0],
        token
      );
      return created.id;
    }
    default:
      throw new Error(`Tipo de operacion desconocido: ${operation.entityType}`);
  }
};

const refreshDownloadedTrailReports = async () => {
  const offlineMaps = await getOfflineMaps().catch(() => []);

  for (const offlineMap of offlineMaps) {
    if (!offlineMap.trail) continue;

    const freshReports = await getTrailReports(offlineMap.trail.id).catch(() => null);
    if (freshReports) {
      await refreshOfflineTrailReports(offlineMap.trail.id, freshReports);
    }
  }
};

const syncOnce = async (): Promise<{ processed: number; failed: number }> => {
  await initDB();
  if (!(await isOnline())) {
    return { processed: 0, failed: 0 };
  }

  const session = await getAuthSession();
  if (!session || await isAccountDeletionPending(session.user.id)) {
    return { processed: 0, failed: 0 };
  }

  // A killed process can leave an operation leased. Recover after one minute;
  // SOS has a stable client_event_id so retrying cannot create a second alert.
  await db.runAsync(
    `UPDATE pending_operations SET status = 'failed' WHERE user_id = ? AND status = 'syncing' AND updated_at < ?`,
    [session.user.id, Date.now() - 60000]
  );
  const retryableOperations = await getRetryableOperations(session.user.id);
  let processed = 0;
  let failed = 0;

  for (const operation of retryableOperations) {
    const current = await getAuthSession();
    if (current?.user.id !== session.user.id || current.token !== session.token || await isAccountDeletionPending(session.user.id)) break;
    if (operation.entityType === "trail_report" && !operation.payload.client_event_id) {
      operation.payload.client_event_id = randomUUID();
      await db.runAsync("UPDATE pending_operations SET payload_json = ? WHERE id = ? AND user_id = ?",
        [JSON.stringify(operation.payload), operation.id, session.user.id]);
    }
    await markSyncing(operation.id);

    try {
      const serverId = await dispatchOperation(operation, session.token);
      await markSynced(operation.id, serverId);
      processed += 1;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error desconocido";
      await markFailed(operation.id, operation.retryCount + 1, message);
      failed += 1;
    }
  }

  if (processed > 0 || Date.now() - (reportsRefreshedAt.get(session.user.id) || 0) > 300000) {
    await refreshDownloadedTrailReports();
    reportsRefreshedAt.set(session.user.id, Date.now());
  }

  return { processed, failed };
};

let syncInFlight: Promise<{ processed: number; failed: number }> | null = null;
const reportsRefreshedAt = new Map<number, number>();
export const runSync = () => {
  if (!syncInFlight) syncInFlight = syncOnce().finally(() => { syncInFlight = null; });
  return syncInFlight;
};

export const getEmergencyOperation = async (id: number) => {
  await initDB();
  const owner = (await getAuthSession())?.user.id ?? null;
  const row = await db.getFirstAsync<PendingOperationRow>(
    `SELECT * FROM pending_operations WHERE id = ? AND entity_type = 'emergency_alert' AND user_id IS ?`,
    [id, owner]
  );
  return row ? toPendingOperation(row) : null;
};

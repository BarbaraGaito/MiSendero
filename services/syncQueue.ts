import * as Network from "expo-network";
import { db } from "../database/database";
import { getAuthSession } from "./authSession";
import { createActivity, createEmergencyAlert, createTrailReport, getTrailReports } from "./api";
import { refreshOfflineTrailReports, getOfflineMaps } from "./offlineMaps";

export type PendingEntityType = "trail_report" | "activity" | "emergency_alert";
export type PendingStatus = "pending" | "syncing" | "synced" | "failed" | "abandoned";

// After this many failed attempts, an operation stops being retried automatically
// and is surfaced to the user to decide whether to keep waiting or discard it.
export const MAX_RETRY_ATTEMPTS = 5;

export interface PendingOperation {
  id: number;
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
  const now = Date.now();
  const result = await db.runAsync(
    `INSERT INTO pending_operations (entity_type, payload_json, status, created_at, updated_at)
     VALUES (?, ?, 'pending', ?, ?)`,
    [entityType, JSON.stringify(payload), now, now]
  );

  return result.lastInsertRowId;
};

export const enqueueUnique = async (
  entityType: PendingEntityType,
  payload: Record<string, unknown>,
  dedupeKey: string
): Promise<number> => {
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
      `INSERT INTO pending_operations (entity_type, payload_json, dedupe_key, status, created_at, updated_at)
       VALUES (?, ?, ?, 'pending', ?, ?)`,
      [entityType, JSON.stringify(payload), dedupeKey, now, now]
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
  const rows = await db.getAllAsync<PendingOperationRow>(
    `SELECT * FROM pending_operations
     WHERE status IN ('pending', 'failed')
     ORDER BY created_at ASC`
  );

  return rows.map(toPendingOperation);
};

const getRetryableOperations = async (): Promise<PendingOperation[]> => {
  const rows = await db.getAllAsync<PendingOperationRow>(
    `SELECT * FROM pending_operations
     WHERE status = 'pending' OR (status = 'failed' AND retry_count < ?)
     ORDER BY created_at ASC`,
    [MAX_RETRY_ATTEMPTS]
  );

  return rows.map(toPendingOperation);
};

export const getSyncSummary = async (): Promise<SyncSummary> => {
  const rows = await db.getAllAsync<{ status: PendingStatus; count: number }>(
    `SELECT status, COUNT(*) AS count FROM pending_operations GROUP BY status`
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
     WHERE status = 'failed' AND retry_count >= ?`,
    [MAX_RETRY_ATTEMPTS]
  );
  summary.exhausted = exhausted?.count ?? 0;

  return summary;
};

export const discardExhaustedOperations = async (): Promise<number> => {
  const result = await db.runAsync(
    `UPDATE pending_operations
     SET status = 'abandoned', updated_at = ?
     WHERE status = 'failed' AND retry_count >= ?`,
    [Date.now(), MAX_RETRY_ATTEMPTS]
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
     SET status = 'failed', retry_count = ?, last_error = ?, updated_at = ?
     WHERE id = ?`,
    [retryCount, error, Date.now(), id]
  );

const dispatchOperation = async (
  operation: PendingOperation,
  token: string
): Promise<number | null> => {
  switch (operation.entityType) {
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

export const runSync = async (): Promise<{ processed: number; failed: number }> => {
  if (!(await isOnline())) {
    return { processed: 0, failed: 0 };
  }

  const session = await getAuthSession();
  if (!session) {
    return { processed: 0, failed: 0 };
  }

  const retryableOperations = await getRetryableOperations();
  let processed = 0;
  let failed = 0;

  for (const operation of retryableOperations) {
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

  if (processed > 0) {
    await refreshDownloadedTrailReports();
  }

  return { processed, failed };
};

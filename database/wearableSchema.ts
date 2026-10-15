export const wearableTablesSql = `
  CREATE TABLE IF NOT EXISTS wearable_connections (
    user_id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    linked INTEGER NOT NULL DEFAULT 0,
    permissions_granted INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL,
    last_sync_at INTEGER
  );

  CREATE TABLE IF NOT EXISTS wearable_metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    heart_rate_bpm INTEGER,
    steps INTEGER,
    active_energy_kcal REAL,
    speed_kmh REAL,
    oxygen_saturation REAL,
    recorded_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL
  );
`;

export const wearableIndexesSql = `
  CREATE INDEX IF NOT EXISTS idx_wearable_samples_user_recorded
  ON wearable_metric_samples (user_id, recorded_at DESC);

  CREATE INDEX IF NOT EXISTS idx_wearable_samples_user_provider_recorded
  ON wearable_metric_samples (user_id, provider, recorded_at DESC);
`;

export const wearableStorageSql = `
  ${wearableTablesSql}
  ${wearableIndexesSql}
`;

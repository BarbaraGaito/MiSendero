export const fieldAssessmentsSql = `
  CREATE TABLE IF NOT EXISTS fatigue_checkins (
    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, trail_id INTEGER NOT NULL,
    started_at INTEGER NOT NULL, borg REAL NOT NULL CHECK(borg >= 0 AND borg <= 10),
    recorded_at INTEGER NOT NULL, created_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_borg_owner_session_time
    ON fatigue_checkins(user_id, trail_id, started_at, recorded_at DESC);
  CREATE TABLE IF NOT EXISTS field_model_assessments (
    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, trail_id INTEGER NOT NULL,
    started_at INTEGER NOT NULL, task TEXT NOT NULL, model_id TEXT NOT NULL,
    assessment_key TEXT NOT NULL, result_json TEXT NOT NULL, created_at INTEGER NOT NULL,
    UNIQUE(user_id, assessment_key)
  );
  CREATE INDEX IF NOT EXISTS idx_field_assessment_owner
    ON field_model_assessments(user_id, created_at DESC);
`;

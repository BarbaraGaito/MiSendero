import { db } from "../database/connection";


export { version as CURRENT_TERMS_VERSION } from "../backend/src/terms.json";
import { version as CURRENT_TERMS_VERSION } from "../backend/src/terms.json";

export interface TermsAcceptance {
  accepted: boolean;
  termsVersion: string | null;
  acceptedAt: number | null;
}

const initLegalTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS legal_acceptance (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      terms_version TEXT NOT NULL,
      accepted_at INTEGER NOT NULL
    );
  `);
};

export const saveTermsAcceptance = async (
  termsVersion = CURRENT_TERMS_VERSION
) => {
  await initLegalTable();

  await db.runAsync(
    `INSERT OR REPLACE INTO legal_acceptance (
       id,
       terms_version,
       accepted_at
     )
     VALUES (1, ?, ?)`,
    [termsVersion, Date.now()]
  );
};

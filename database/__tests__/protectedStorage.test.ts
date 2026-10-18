// Control-flow tests at the native boundary: these do not prove cryptography on a device.
type Scenario = { noCipher?: boolean; noStore?: boolean; exportError?: boolean; integrityError?: boolean; ready?: boolean };
function setup(scenario: Scenario = {}) {
  jest.resetModules();
  const events: string[] = [];
  const secure = {
    databasePath: '/private/SQLite/trekking-secure-v1.db',
    closeAsync: jest.fn().mockResolvedValue(undefined),
    execAsync: jest.fn(async (sql: string) => { events.push(sql); }),
    getAllAsync: jest.fn(async (sql: string) => { events.push(sql); return []; }),
    getFirstAsync: jest.fn(async (sql: string) => {
      events.push(sql);
      if (sql === 'PRAGMA cipher_version') return scenario.noCipher ? null : { cipher_version: 'boundary-double' };
      if (sql === 'PRAGMA integrity_check') return { integrity_check: scenario.integrityError ? 'corrupt' : 'ok' };
      if (sql.includes('AND name = ?')) return scenario.ready ? { name: '_misendero_encrypted_migration' } : null;
      return { count: 0 };
    }),
  };
  const legacy = {
    closeAsync: jest.fn().mockResolvedValue(undefined),
    execAsync: jest.fn(async (sql: string) => { events.push(sql); }),
    getFirstAsync: jest.fn(async (sql: string) => {
      events.push(sql);
      if (sql.includes('sqlcipher_export') && scenario.exportError) throw new Error('export failed');
      return { user_version: 4 };
    }),
  };
  const sqlite = {
    defaultDatabaseDirectory: "/private/SQLite",
    openDatabaseAsync: jest.fn(async (name: string) => name === 'trekking.db' ? legacy : secure),
    deleteDatabaseAsync: jest.fn(async () => { events.push('delete plaintext'); }),
  };
  const store = { isAvailableAsync: jest.fn().mockResolvedValue(!scenario.noStore), getItemAsync: jest.fn().mockResolvedValue(null),
    setItemAsync: jest.fn().mockResolvedValue(undefined), WHEN_UNLOCKED_THIS_DEVICE_ONLY: 1 };
  jest.doMock('expo-file-system', () => ({ File: class {
    exists = true;
    constructor(_directory: string, private filename: string) {}
    delete() { events.push(`delete ${this.filename}`); }
  } }));
  jest.doMock('expo-sqlite', () => sqlite); jest.doMock('expo-secure-store', () => store);
  jest.doMock('expo-crypto', () => ({ randomUUID: () => '12345678-1234-4234-a234-123456789abc' }));
  jest.doMock('react-native', () => ({ Platform: { OS: 'ios' } }));
  return { ...jest.requireActual('../protectedStorage'), sqlite, store, events, secure, legacy };
}
test('refuses an unavailable keystore without opening plaintext', async () => {
  const s = setup({ noStore: true }); await expect(s.openProtectedDatabase()).rejects.toThrow('seguro');
  expect(s.sqlite.openDatabaseAsync).not.toHaveBeenCalled();
});
test('refuses a native build without SQLCipher and keeps the original', async () => {
  const s = setup({ noCipher: true }); await expect(s.openProtectedDatabase()).rejects.toThrow('SQLCipher');
  expect(s.sqlite.deleteDatabaseAsync).not.toHaveBeenCalled();
  expect(s.sqlite.openDatabaseAsync).toHaveBeenCalledTimes(1);
});
test.each([{ exportError: true }, { integrityError: true }])('migration failure preserves plaintext for recovery: %j', async scenario => {
  const s = setup(scenario); await expect(s.openProtectedDatabase()).rejects.toThrow();
  expect(s.sqlite.deleteDatabaseAsync).not.toHaveBeenCalled();
});
test('exports before verification and only then removes plaintext; new connections receive the key', async () => {
  const s = setup(); await s.openProtectedDatabase();
  expect(s.events.indexOf("SELECT sqlcipher_export('encrypted')")).toBeLessThan(s.events.indexOf('PRAGMA integrity_check'));
  expect(s.events.indexOf('PRAGMA cipher_integrity_check')).toBeLessThan(s.events.indexOf('delete plaintext'));
  expect(s.events).toEqual(expect.arrayContaining(['delete trekking.db-wal', 'delete trekking.db-shm', 'delete trekking.db-journal']));
  expect(s.events.indexOf('delete plaintext')).toBeLessThan(s.events.indexOf('delete trekking.db-wal'));
  expect(s.store.setItemAsync).toHaveBeenCalledWith('misendero.sqlite.key.v1', expect.stringMatching(/^[a-f0-9]{64}$/), { keychainAccessible: 1 });
  await s.openProtectedDatabase(true);
  expect(s.sqlite.openDatabaseAsync).toHaveBeenLastCalledWith('trekking-secure-v1.db', { useNewConnection: true });
});
test('a committed migration resumes cleanup without exporting again', async () => {
  const s = setup({ ready: true }); await s.openProtectedDatabase();
  expect(s.legacy.getFirstAsync).not.toHaveBeenCalled(); expect(s.sqlite.deleteDatabaseAsync).toHaveBeenCalledTimes(1);
});

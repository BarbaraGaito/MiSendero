// Native boundary double. Host tests do not verify encryption.
jest.mock("../database/protectedStorage", () => ({
  openProtectedDatabase: async () => require("expo-sqlite").openDatabaseAsync("host-test.db"),
}));

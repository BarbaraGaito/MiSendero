module.exports = {
  testEnvironment: "node",
  transform: { "^.+\\.ts$": "<rootDir>/tests/typescriptTransformer.cjs" },
  moduleNameMapper: { "^(?:\\.\\./)+dist/ai/(.*)$": "<rootDir>/src/ai/$1.ts" },
  setupFiles: ["<rootDir>/tests/setupEnv.js"],
  testMatch: ["<rootDir>/tests/**/*.test.js"],
  collectCoverageFrom: require("../testing/coverage-scope.cjs").backend.map((file) => file.replace(/^backend\//, "")),
  coverageProvider: "babel",
  coverageDirectory: "<rootDir>/../coverage/backend",
  coverageReporters: ["json", "json-summary", "lcov", "html", "text-summary"],
};

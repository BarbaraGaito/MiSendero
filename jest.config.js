const expoPreset = require("jest-expo/jest-preset");

module.exports = {
  preset: "jest-expo",
  transformIgnorePatterns: expoPreset.transformIgnorePatterns.map(pattern =>
    pattern.replace(".pnpm|", ".pnpm|fast-png|iobuffer|")),
  setupFilesAfterEnv: ["<rootDir>/testing/storageSetup.cjs"],
  testMatch: ["**/__tests__/**/*.test.ts", "**/__tests__/**/*.test.tsx"],
  testPathIgnorePatterns: ["/node_modules/", "<rootDir>/backend/", "<rootDir>/training/", "<rootDir>/tmp/"],
  modulePathIgnorePatterns: ["<rootDir>/tmp/"],
  collectCoverageFrom: require("./testing/coverage-scope.cjs").client,
  coverageProvider: "babel",
  coverageDirectory: "<rootDir>/coverage/client",
  coverageReporters: ["json", "json-summary", "lcov", "html", "text-summary"],
};

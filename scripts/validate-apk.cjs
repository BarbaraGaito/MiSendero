const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { getConfig } = require("expo/config");
const ignore = require("ignore");
const semver = require("semver");

const root = path.resolve(__dirname, "..");
const eas = require("../eas.json");
const pkg = require("../package.json");
const preview = eas.build.preview;
assert.equal(preview.android.buildType, "apk");
assert.equal(preview.distribution, "internal");
assert.equal(preview.developmentClient, false);
assert.equal(preview.env.EXPO_PUBLIC_API_URL, "https://18-218-87-168.sslip.io/api");
assert.equal(eas.build.production.android.buildType, "app-bundle");
for (const profile of [preview, eas.build.production]) {
  assert.deepEqual(Object.keys(profile.env), ["EXPO_PUBLIC_API_URL"]);
}

process.env.EXPO_NO_DOTENV = "1";
process.env.EAS_BUILD_PROFILE = "preview";
Object.assign(process.env, preview.env);
const config = getConfig(root).exp;
assert.equal(config.name, "MiSendero");
assert.equal(config.android.package, "com.misendero.app");
assert.equal(config.android.allowBackup, false);
assert.ok(Number.isInteger(config.android.versionCode) && config.android.versionCode > 0);
assert.equal(config.version, pkg.version);
const plugin = (name) => config.plugins.find((entry) => Array.isArray(entry) && entry[0] === name)?.[1];
assert.equal(plugin("expo-sqlite").useSQLCipher, true);
assert.equal(plugin("expo-build-properties").android.usesCleartextTraffic, false);
assert.equal(plugin("expo-location").isAndroidBackgroundLocationEnabled, false);
for (const file of [config.icon, config.android.adaptiveIcon.foregroundImage, plugin("expo-splash-screen").image]) {
  const png = fs.readFileSync(path.resolve(root, file));
  assert.equal(png.subarray(1, 4).toString(), "PNG");
  assert.equal(png.readUInt32BE(16), png.readUInt32BE(20));
}
const expected = require("expo/bundledNativeModules.json");
for (const [name, range] of Object.entries(expected)) {
  if (!(pkg.dependencies[name] || pkg.devDependencies[name])) continue;
  const version = require(`${name}/package.json`).version;
  assert.ok(semver.satisfies(version, range), `${name}: ${version}, SDK requires ${range}`);
}
assert.equal(pkg.dependencies["expo-modules-core"], undefined);
assert.equal(pkg.dependencies["expo-three"], undefined);
const excluded = ignore().add(fs.readFileSync(path.join(root, ".easignore"), "utf8"));
for (const file of [".env", "backend/.env", "backend/src/db.js", "backend/data/example.sqlite", "credentials.json", "release.keystore", "backup.zip", "tmp/test.db"]) {
  assert.ok(excluded.ignores(file), `EAS must exclude ${file}`);
}
for (const file of ["backend", "backend/src", "backend/src/ai", "app/_layout.tsx", "ai/inferenceEngine.ts", "ai/models/fatigueMetrics.json", "database/protectedStorage.ts", "assets/icon.png", "assets/offline-maps/catalog.json", "services/basicOfflineMap.ts", "mobile/components/BasicMapLayer.tsx", "backend/src/terms.json", "backend/src/privacyNotices.json", "backend/src/reportPublicPolicy.json", "backend/src/ai/contracts.ts"]) {
  assert.ok(!excluded.ignores(file), `EAS must include ${file}`);
  assert.ok(fs.existsSync(path.join(root, file)), `Missing ${file}`);
}
console.log("APK: profiles, AWS URL, Android identity, SQLCipher, permissions, assets, SDK versions and upload exclusions OK.");
if (!config.extra?.eas?.projectId) {
  console.log("Pending: link the Expo project with npx eas-cli init before building.");
} else {
  console.log(`Expo project: @${config.owner}/${config.slug} (${config.extra.eas.projectId})`);
}

if (process.argv.includes("--bundle")) {
  const directory = path.join(root, "tmp/offline-android-export/_expo/static/js/android");
  const file = fs.readdirSync(directory).find((name) => name.endsWith(".hbc"));
  assert.ok(file, "Export the Android Hermes bundle first");
  const bundle = fs.readFileSync(path.join(directory, file));
  assert.ok(bundle.includes(Buffer.from(preview.env.EXPO_PUBLIC_API_URL)), "AWS URL must be inlined in the Android bundle");
  const envFile = path.join(root, ".env");
  if (fs.existsSync(envFile)) {
    const local = require("dotenv").parse(fs.readFileSync(envFile));
    const publicLiterals = new Set([pkg.name, config.name, config.slug, config.android.package]);
    for (const name of ["JWT_SECRET", "OPENAI_API_KEY", "POSTGRES_PASSWORD"]) {
      const value = local[name];
      if (publicLiterals.has(value)) {
        console.log(`${name}: value overlaps public application metadata; binary matching is inconclusive.`);
        continue;
      }
      assert.ok(!value || value.length < 6 || !bundle.includes(Buffer.from(value)), "Private server value found in bundle");
    }
  }
  console.log("Android Hermes bundle: AWS URL inlined; private-value scan completed.");
}

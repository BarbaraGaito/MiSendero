// Distribution must fail during configuration as well as at runtime if HTTPS is missing.
module.exports = ({ config }) => {
  const development = process.env.EAS_BUILD_PROFILE === "development" ||
    (!process.env.EAS_BUILD_PROFILE && process.env.NODE_ENV !== "production");
  if (!development) {
    const url = new URL(process.env.EXPO_PUBLIC_API_URL || "https-required:");
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
      throw new Error("La distribución requiere EXPO_PUBLIC_API_URL con HTTPS y sin credenciales.");
    }
  }
  return {
    ...config,
    android: { ...config.android, allowBackup: false },
    plugins: config.plugins.map((plugin) => Array.isArray(plugin) && plugin[0] === "expo-build-properties"
      ? [plugin[0], { ...plugin[1], android: { ...plugin[1].android, usesCleartextTraffic: development } }]
      : plugin),
  };
};

export function resolveApiUrl(configuredUrl: string | undefined, development: boolean, host = "localhost") {
  if (!configuredUrl && !development) throw new Error("Configurá EXPO_PUBLIC_API_URL con HTTPS para distribuir MiSendero.");
  const url = new URL(configuredUrl || `http://${host}:3001/api`);
  if (url.username || url.password || url.search || url.hash ||
      (url.protocol !== "https:" && !(development && url.protocol === "http:"))) {
    throw new Error("La API requiere una URL HTTPS sin credenciales ni parámetros.");
  }
  return url.toString().replace(/\/$/, "");
}

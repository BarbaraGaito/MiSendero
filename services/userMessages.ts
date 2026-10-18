/** Keep service/configuration diagnostics out of alerts and screen notices. */
export function userMessage(error: unknown, fallback: string): string {
  const value = typeof error === "string" ? error : error && typeof error === "object" && "message" in error ? error.message : null;
  if (typeof value !== "string" || !value.trim() || value.length > 600) return fallback;
  if (/\b(api|endpoint|backend|sqlite|sqlstate|syntaxerror|typeerror|referenceerror|undefined|stack trace|fetch|econnrefused|enotfound|timeout|aborterror|zod|json|development build|healthkit bridge|puente nativo|native module|failed to|required|invalid|expected|received)\b|https?:\/\/|EXPO_PUBLIC_|[A-Z][A-Z_]+_[A-Z_]+|proveedor.*configur|canal.*configur|network request failed/i.test(value)) return fallback;
  return value.trim();
}

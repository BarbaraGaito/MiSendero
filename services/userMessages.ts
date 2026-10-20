/** Keep service/configuration diagnostics out of alerts and screen notices. */
export function userMessage(error: unknown, fallback: string): string {
  const value = typeof error === "string" ? error : error && typeof error === "object" && "message" in error ? error.message : null;
  if (typeof value !== "string" || !value.trim() || value.length > 600) return fallback;
  const configurationName = (value.match(/[A-Z][A-Z_]*/gi) || []).some((token) => token.slice(2, -1).includes("_"));
  const configurationDiagnostic = value.split(/[\r\n\u2028\u2029]/).some((line) => {
    const text = line.toLowerCase();
    const end = text.lastIndexOf("configur");
    return end >= 0 && ["proveedor", "canal"].some((word) => {
      const start = text.indexOf(word);
      return start >= 0 && start < end;
    });
  });
  if (configurationName || configurationDiagnostic || /\b(api|endpoint|backend|sqlite|sqlstate|syntaxerror|typeerror|referenceerror|undefined|stack trace|fetch|econnrefused|enotfound|timeout|aborterror|zod|json|development build|healthkit bridge|puente nativo|native module|failed to|required|invalid|expected|received)\b|https?:\/\/|EXPO_PUBLIC_|network request failed/i.test(value)) return fallback;
  return value.trim();
}

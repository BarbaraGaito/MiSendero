export const getEstimatedReturnHours = (duration?: string | null): number | null => {
  if (!duration?.trim()) return null;
  const upperEstimate = duration.trim().toLowerCase().replace(/\s+/g, " ").split(/ (?:a|[-\u2013\u2014]) /).at(-1)?.trim();
  if (!upperEstimate) return null;
  const hoursAndMinutes = upperEstimate.match(/^(\d+(?:[.,]\d+)?)\s*(?:h|horas?)(?:\s+(\d+(?:[.,]\d+)?)\s*(?:min|minutos?))?$/);
  const minutesOnly = upperEstimate.match(/^(\d+(?:[.,]\d+)?)\s*(?:min|minutos?)$/);
  const number = (value: string) => Number(value.replace(",", "."));
  const hours = hoursAndMinutes
    ? number(hoursAndMinutes[1]) + number(hoursAndMinutes[2] || "0") / 60
    : minutesOnly ? number(minutesOnly[1]) / 60 : null;
  return hours !== null && hours > 0 && hours <= 72 ? hours : null;
};

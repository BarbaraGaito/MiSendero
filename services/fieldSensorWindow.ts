import type { WearableProvider } from "../types";
export interface TimedHealthReading { value: number; recordedAt: number }
export interface NativeFieldSamples {
  provider: WearableProvider;
  heartRate: TimedHealthReading[];
  oxygen: TimedHealthReading[];
}
export interface HeartRateWindow {
  meanBpm: number;
  startAt: number;
  endAt: number;
  sampleCount: number;
  provider: WearableProvider;
}

function uniqueReadings(rows: TimedHealthReading[], start: number, end: number, min: number, max: number) {
  const values = new Map<number, number>();
  for (const row of rows) {
    if (!Number.isFinite(row.recordedAt) || !Number.isFinite(row.value) || row.recordedAt < start || row.recordedAt > end || row.value < min || row.value > max) continue;
    if (values.has(row.recordedAt) && values.get(row.recordedAt) !== row.value) return null;
    values.set(row.recordedAt, row.value);
  }
  return [...values.entries()].map(([recordedAt, value]) => ({ recordedAt, value })).sort((a, b) => a.recordedAt-b.recordedAt);
}

export function completedHeartRateWindow(samples: NativeFieldSamples | null, now: number): HeartRateWindow | null {
  if (!samples || samples.provider === "development_simulator" || !Number.isFinite(now)) return null;
  const endAt = Math.floor(now/60000)*60000;
  const startAt = endAt-60000;
  const rows = uniqueReadings(samples.heartRate, startAt, endAt, 30, 240);
  // Sampling adequacy, not a physiological threshold: no interpolation of gaps.
  if (!rows || rows.length < 4 || rows[0].recordedAt-startAt > 15000 || endAt-rows[rows.length-1].recordedAt > 15000 ||
      rows.some((row, index) => index > 0 && row.recordedAt-rows[index-1].recordedAt > 30000)) return null;
  return { meanBpm: rows.reduce((sum, row) => sum+row.value, 0)/rows.length, startAt, endAt, sampleCount: rows.length, provider: samples.provider };
}

export function freshMorningPair(samples: NativeFieldSamples | null, now: number) {
  if (!samples || samples.provider === "development_simulator" || !Number.isFinite(now)) return null;
  const pulse = uniqueReadings(samples.heartRate, now-300000, now, 30, 240)?.at(-1);
  const oxygen = uniqueReadings(samples.oxygen, now-300000, now, 50, 100)?.at(-1);
  if (!pulse || !oxygen || Math.abs(pulse.recordedAt-oxygen.recordedAt) > 60000) return null;
  return { hr: pulse.value, spo2: oxygen.value, pulseRecordedAt: pulse.recordedAt, oxygenRecordedAt: oxygen.recordedAt, provider: samples.provider };
}

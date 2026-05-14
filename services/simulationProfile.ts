export const SENSOR_INTERVAL_MS = 5_000;

const PROFILE = [
  { heartRate: 98, speedMps: 1.5 },
  { heartRate: 106, speedMps: 1.6 },
  { heartRate: 114, speedMps: 1.7 },
  { heartRate: 124, speedMps: 1.6 },
  { heartRate: 136, speedMps: 1.5 },
  { heartRate: 148, speedMps: 1.3 },
  { heartRate: 156, speedMps: 0.35 },
  { heartRate: 162, speedMps: 0.22 },
  { heartRate: 158, speedMps: 0.18 },
  { heartRate: 152, speedMps: 0.2 },
  { heartRate: 144, speedMps: 1.0 },
  { heartRate: 134, speedMps: 1.2 },
  { heartRate: 126, speedMps: 1.45 },
  { heartRate: 118, speedMps: 1.65 },
  { heartRate: 112, speedMps: 1.6 },
  { heartRate: 108, speedMps: 1.55 },
];

export function getSimulationProfile(step: number) {
  return PROFILE[step % PROFILE.length];
}


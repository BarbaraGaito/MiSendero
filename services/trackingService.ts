export interface TrackingTick {
  metersDelta: number;
  speedKmh: number;
}

// GPS simulado y offline-first: evita depender de permisos durante el MVP.
export const getSimulatedTrackingTick = (elapsedSeconds: number): TrackingTick => {
  const baseSpeed = elapsedSeconds < 90 ? 4.6 : elapsedSeconds < 180 ? 3.8 : 2.1;
  const variation = Math.sin(elapsedSeconds / 18) * 0.35;
  const speedKmh = Math.max(0, Number((baseSpeed + variation).toFixed(2)));
  const metersDelta = Number(((speedKmh * 1000) / 3600).toFixed(2));

  return { metersDelta, speedKmh };
};

// Possible fall: a strong impact followed by a period of stillness. Accelerometer
// values are in g (Expo reports g on Android and iOS), so a phone at rest reads ~1 g.
export const FALL_IMPACT_G = 2.5;
export const FALL_SETTLE_MS = 1500;
export const FALL_STILL_MS = 10000;
export const FALL_STILL_TOLERANCE_G = 0.15;
// If stillness has not been reached within this time after the impact, the person
// kept moving (got up, kept walking) and the impact is discarded.
export const FALL_WAIT_MS = 20000;

export type AccelerometerSample = { x: number; y: number; z: number; timestamp: number };

export const createFallDetector = () => {
  let impactAt: number | null = null;
  let stillSince: number | null = null;
  return ({ x, y, z, timestamp }: AccelerometerSample): boolean => {
    const magnitude = Math.hypot(x, y, z);
    if (magnitude >= FALL_IMPACT_G) {
      impactAt = timestamp;
      stillSince = null;
      return false;
    }
    if (impactAt === null || timestamp - impactAt < FALL_SETTLE_MS) return false;
    if (Math.abs(magnitude - 1) <= FALL_STILL_TOLERANCE_G) {
      stillSince ??= timestamp;
      if (timestamp - stillSince >= FALL_STILL_MS) {
        impactAt = null;
        stillSince = null;
        return true;
      }
      return false;
    }
    stillSince = null;
    if (timestamp - impactAt > FALL_WAIT_MS) impactAt = null;
    return false;
  };
};

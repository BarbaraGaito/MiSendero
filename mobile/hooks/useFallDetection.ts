import { useEffect, useRef } from "react";
import { Accelerometer } from "expo-sensors";
import { createFallDetector } from "../../services/fallDetection";

const SAMPLE_INTERVAL_MS = 50;

// Reads the phone accelerometer only while enabled (active route in the
// foreground). Everything runs on the device: no data leaves the phone.
export function useFallDetection(enabled: boolean, onPossibleFall: () => void) {
  const callback = useRef(onPossibleFall);
  callback.current = onPossibleFall;
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let subscription: { remove: () => void } | null = null;
    const detect = createFallDetector();
    void Accelerometer.isAvailableAsync().then((available) => {
      if (!available || !active) return;
      Accelerometer.setUpdateInterval(SAMPLE_INTERVAL_MS);
      subscription = Accelerometer.addListener(({ x, y, z }) => {
        if (detect({ x, y, z, timestamp: Date.now() })) callback.current();
      });
    }).catch(() => undefined);
    return () => { active = false; subscription?.remove(); };
  }, [enabled]);
}

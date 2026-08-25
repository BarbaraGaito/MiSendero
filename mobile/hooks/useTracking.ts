import { useEffect, useRef, useState } from "react";
import { calculateFatigue, fatigueToScore, scoreToFatigue } from "../../ai/fatigueEngine";
import {
  createSession,
  finishSession,
  saveHeartRateLog,
} from "../../database/sessionsRepository";
import { bluetoothSimulator } from "../../services/bluetoothSimulator";
import { hasSensitiveDataConsent } from "../../services/privacyConsent";
import { syncSessions } from "../../services/syncService";
import { getSimulatedTrackingTick } from "../../services/trackingService";
import {
  getLatestWearableMetricSample,
  getWearableConnection,
  syncNativeWearableSample,
} from "../../services/wearableMetrics";
import { FatigueLevel } from "../../types";
import { startWatch, stopWatch } from "../../watch/WatchService";

export const useTracking = () => {
  const [hr, setHr] = useState(0);
  const [fatigue, setFatigue] = useState<FatigueLevel>("bajo");
  const [isActive, setIsActive] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [distanceMeters, setDistanceMeters] = useState(0);
  const [speedKmh, setSpeedKmh] = useState(0);
  const [inactiveTooLong, setInactiveTooLong] = useState(false);
  const [needsSensitiveDataConsent, setNeedsSensitiveDataConsent] = useState(false);

  const sessionIdRef = useRef<number | null>(null);
  const lastMovementRef = useRef(Date.now());
  const fatigueSamplesRef = useRef<number[]>([]);
  const elapsedSecondsRef = useRef(0);
  const speedKmhRef = useRef(0);
  const lastNativeSampleRecordedAtRef = useRef(0);
  const useSimulatorWatchRef = useRef(true);

  useEffect(() => {
    elapsedSecondsRef.current = elapsedSeconds;
  }, [elapsedSeconds]);

  useEffect(() => {
    speedKmhRef.current = speedKmh;
  }, [speedKmh]);

  useEffect(() => {
    const unsubscribe = bluetoothSimulator.subscribe(async (data) => {
      setHr(data.hr);

      if (!sessionIdRef.current) return;

      const currentFatigue = calculateFatigue(
        data.hr,
        speedKmh,
        elapsedSeconds / 60
      );

      fatigueSamplesRef.current.push(fatigueToScore(currentFatigue));
      setFatigue(currentFatigue);
      await saveHeartRateLog(data.hr, data.timestamp, sessionIdRef.current);
    });

    return unsubscribe;
  }, [elapsedSeconds, speedKmh]);

  useEffect(() => {
    if (!isActive) return;

    const interval = setInterval(() => {
      setElapsedSeconds((previous) => {
        const next = previous + 1;
        const tick = getSimulatedTrackingTick(next);

        setSpeedKmh(tick.speedKmh);
        setDistanceMeters((distance) => distance + tick.metersDelta);

        if (tick.speedKmh > 0.8) {
          lastMovementRef.current = Date.now();
          setInactiveTooLong(false);
        } else if (Date.now() - lastMovementRef.current > 30_000) {
          setInactiveTooLong(true);
        }

        return next;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [isActive]);

  useEffect(() => {
    if (!isActive || useSimulatorWatchRef.current) return;

    let cancelled = false;

    const syncNativeHeartRate = async () => {
      const synced = await syncNativeWearableSample().catch(() => false);
      if (!synced || cancelled) return;

      const sample = await getLatestWearableMetricSample().catch(() => null);
      if (
        !sample?.heartRateBpm ||
        sample.recordedAt <= lastNativeSampleRecordedAtRef.current
      ) {
        return;
      }

      lastNativeSampleRecordedAtRef.current = sample.recordedAt;
      setHr(sample.heartRateBpm);

      if (!sessionIdRef.current) return;

      const currentFatigue = calculateFatigue(
        sample.heartRateBpm,
        sample.speedKmh ?? speedKmhRef.current,
        elapsedSecondsRef.current / 60
      );

      fatigueSamplesRef.current.push(fatigueToScore(currentFatigue));
      setFatigue(currentFatigue);
      await saveHeartRateLog(
        sample.heartRateBpm,
        sample.recordedAt,
        sessionIdRef.current
      );
    };

    syncNativeHeartRate();
    const interval = setInterval(syncNativeHeartRate, 12_000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [isActive]);

  const startSession = async () => {
    const canUseSensitiveData = await hasSensitiveDataConsent();

    if (!canUseSensitiveData) {
      setNeedsSensitiveDataConsent(true);
      return false;
    }

    const startedAt = Date.now();
    sessionIdRef.current = await createSession(startedAt);
    fatigueSamplesRef.current = [];
    lastMovementRef.current = startedAt;
    setHr(0);
    setFatigue("bajo");
    setElapsedSeconds(0);
    setDistanceMeters(0);
    setSpeedKmh(0);
    setInactiveTooLong(false);
    setNeedsSensitiveDataConsent(false);
    lastNativeSampleRecordedAtRef.current = 0;

    const wearableConnection = await getWearableConnection().catch(() => null);
    useSimulatorWatchRef.current =
      !wearableConnection?.linked ||
      wearableConnection.provider === "development_simulator";

    setIsActive(true);

    if (useSimulatorWatchRef.current) {
      startWatch();
    }
    return true;
  };

  const stopSession = async () => {
    if (!sessionIdRef.current) return;

    if (useSimulatorWatchRef.current) {
      stopWatch();
    }
    setIsActive(false);

    const scores = fatigueSamplesRef.current;
    const averageScore =
      scores.length === 0
        ? 1
        : scores.reduce((sum, score) => sum + score, 0) / scores.length;
    const avgFatigue = scoreToFatigue(averageScore);

    await finishSession(
      sessionIdRef.current,
      Date.now(),
      elapsedSeconds,
      distanceMeters,
      avgFatigue
    );
    await syncSessions();
    sessionIdRef.current = null;
  };

  return {
    hr,
    fatigue,
    isActive,
    elapsedSeconds,
    distanceMeters,
    speedKmh,
    inactiveTooLong,
    needsSensitiveDataConsent,
    startSession,
    stopSession,
  };
};

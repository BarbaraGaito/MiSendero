import { useEffect, useRef, useState } from "react";
import { calculateFatigue, fatigueToScore, scoreToFatigue } from "../../ai/fatigueEngine";
import {
  createSession,
  finishSession,
  saveHeartRateLog,
} from "../../database/sessionsRepository";
import { getAuthSession } from "../../services/authSession";
import { bluetoothSimulator } from "../../services/bluetoothSimulator";
import { DeviceLocation, watchDeviceLocation } from "../../services/deviceLocation";
import { getDistanceMeters } from "../../services/geoUtils";
import { hasSensitiveDataConsent } from "../../services/privacyConsent";
import { syncSessions } from "../../services/syncService";
import { getSimulatedTrackingTick } from "../../services/trackingService";
import { getTestingLocationMode } from "../../services/testingMode";
import {
  getLatestWearableMetricSample,
  getWearableConnection,
  syncNativeWearableSampleWithStatus,
} from "../../services/wearableMetrics";
import { FatigueLevel } from "../../types";
import { startWatch, stopWatch } from "../../watch/WatchService";

// GPS jitter produces small non-zero deltas even standing still; movements below
// this threshold are treated as noise rather than real displacement.
const GPS_NOISE_FLOOR_METERS = 2;
const NATIVE_HARD_FAILURES_BEFORE_SIMULATOR = 2;
const NATIVE_NO_DATA_FAILURES_BEFORE_SIMULATOR = 5;

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
  const nativeSyncMissesRef = useRef(0);
  const sessionStartedAtRef = useRef(0);
  const useSimulatorWatchRef = useRef(true);
  const useSimulatedMovementRef = useRef(false);
  const lastGpsLocationRef = useRef<DeviceLocation | null>(null);

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
        speedKmhRef.current,
        elapsedSecondsRef.current / 60
      );

      fatigueSamplesRef.current.push(fatigueToScore(currentFatigue));
      setFatigue(currentFatigue);
      await saveHeartRateLog(data.hr, data.timestamp, sessionIdRef.current);
    });

    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!isActive) return;

    const interval = setInterval(() => {
      setElapsedSeconds((previous) => {
        const next = previous + 1;

        if (useSimulatedMovementRef.current) {
          const tick = getSimulatedTrackingTick(next);

          setSpeedKmh(tick.speedKmh);
          setDistanceMeters((distance) => distance + tick.metersDelta);

          if (tick.speedKmh > 0.8) {
            lastMovementRef.current = Date.now();
            setInactiveTooLong(false);
          } else if (Date.now() - lastMovementRef.current > 30_000) {
            setInactiveTooLong(true);
          }
        } else if (Date.now() - lastMovementRef.current > 30_000) {
          setInactiveTooLong(true);
        }

        return next;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [isActive]);

  // Real GPS is the source of truth for distance/speed (RF-06). The synthetic
  // movement tick is only used when an admin explicitly enables testing mode.
  useEffect(() => {
    if (!isActive || useSimulatedMovementRef.current) return;

    let cancelled = false;
    let subscription: { remove: () => void } | null = null;

    const start = async () => {
      subscription = await watchDeviceLocation((location) => {
        if (cancelled) return;

        const previous = lastGpsLocationRef.current;
        lastGpsLocationRef.current = location;

        if (!previous) return;

        const deltaMeters = getDistanceMeters(previous.coordinate, location.coordinate);
        const deltaSeconds = Math.max(0.001, (location.timestamp - previous.timestamp) / 1000);

        if (deltaMeters < GPS_NOISE_FLOOR_METERS) return;

        const instantSpeedKmh = Number(((deltaMeters / deltaSeconds) * 3.6).toFixed(2));

        setDistanceMeters((distance) => distance + deltaMeters);
        setSpeedKmh(instantSpeedKmh);
        lastMovementRef.current = Date.now();
        setInactiveTooLong(false);
      });
    };

    start();

    return () => {
      cancelled = true;
      subscription?.remove();
    };
  }, [isActive]);

  useEffect(() => {
    if (!isActive || useSimulatorWatchRef.current) return;

    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;

    const startSimulatorFallback = () => {
      if (cancelled || useSimulatorWatchRef.current) return;

      useSimulatorWatchRef.current = true;
      startWatch();
      if (interval) clearInterval(interval);
    };

    const syncNativeHeartRate = async () => {
      const status = await syncNativeWearableSampleWithStatus({
        startAt: sessionStartedAtRef.current,
        requireHeartRate: true,
      }).catch(() => "unavailable" as const);
      if (cancelled) return;

      if (status !== "saved" && status !== "duplicate") {
        nativeSyncMissesRef.current += 1;

        const shouldFallbackImmediately =
          status === "unavailable" ||
          status === "permission_denied" ||
          status === "not_linked";
        const failureLimit = shouldFallbackImmediately
          ? NATIVE_HARD_FAILURES_BEFORE_SIMULATOR
          : NATIVE_NO_DATA_FAILURES_BEFORE_SIMULATOR;

        if (nativeSyncMissesRef.current >= failureLimit) {
          startSimulatorFallback();
        }
        return;
      }

      nativeSyncMissesRef.current = 0;

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
    interval = setInterval(syncNativeHeartRate, 12_000);

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [isActive]);

  const startSession = async () => {
    const canUseSensitiveData = await hasSensitiveDataConsent();

    if (!canUseSensitiveData) {
      setNeedsSensitiveDataConsent(true);
      return false;
    }

    const startedAt = Date.now();
    sessionStartedAtRef.current = startedAt;
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
    nativeSyncMissesRef.current = 0;
    lastGpsLocationRef.current = null;

    const [testingLocationMode, session] = await Promise.all([
      getTestingLocationMode().catch(() => ({ enabled: false, updatedAt: null })),
      getAuthSession().catch(() => null),
    ]);
    const canUseTestingLocation = session?.user.role === "admin";
    useSimulatedMovementRef.current =
      testingLocationMode.enabled && canUseTestingLocation;

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

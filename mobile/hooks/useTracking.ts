import { useEffect, useRef, useState } from "react";
import { calculateFatigue, fatigueToScore, scoreToFatigue } from "../../ai/fatigueEngine";
import {
  createSession,
  finishSession,
  saveHeartRateLog,
} from "../../database/sessionsRepository";
import { bluetoothSimulator } from "../../services/bluetoothSimulator";
import { syncSessions } from "../../services/syncService";
import { getSimulatedTrackingTick } from "../../services/trackingService";
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

  const sessionIdRef = useRef<number | null>(null);
  const lastMovementRef = useRef(Date.now());
  const fatigueSamplesRef = useRef<number[]>([]);

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

  const startSession = async () => {
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
    setIsActive(true);
    startWatch();
  };

  const stopSession = async () => {
    if (!sessionIdRef.current) return;

    stopWatch();
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
    startSession,
    stopSession,
  };
};

import { useCallback, useEffect, useRef, useState } from 'react';

import { evaluateFatigue, fatigueLevelFromScore } from '../../ai/fatigue';
import {
  createSession,
  finishSession,
  getSessionHistory,
  initDatabase,
  saveSample,
} from '../../database/trekkingDb';
import { bluetoothSimulator } from '../../services/bluetoothSimulator';
import { createLocationTracker } from '../../services/locationTracker';
import {
  appendLogEntries,
  appendLogEntry,
  buildLiveSyncMessage,
  buildSessionSyncMessages,
  buildSosMessage,
} from '../../services/syncService';
import {
  LiveSessionMetrics,
  LocationSnapshot,
  PhoneToWatchPayload,
  SessionHistoryItem,
  SyncLogEntry,
  WatchAlert,
  WatchCommand,
} from '../../types';

const INITIAL_LOCATION: LocationSnapshot = {
  distanceMeters: 0,
  durationSec: 0,
  latitude: null,
  longitude: null,
  source: 'simulated',
  speedMps: 0,
  stoppedSeconds: 0,
};

const INITIAL_LIVE_METRICS: LiveSessionMetrics = {
  active: false,
  alerts: [],
  distanceMeters: 0,
  durationSec: 0,
  fatigue: 'bajo',
  gpsMode: 'simulated',
  heartRate: 92,
  lastSyncMessage: 'Listo para guardar todo en SQLite sin internet.',
  samplesStored: 0,
  sessionId: null,
  sosRaised: false,
  speedMps: 0,
  startedAt: null,
};

const INITIAL_WATCH_PAYLOAD: PhoneToWatchPayload = {
  active: false,
  alerts: [],
  distanceMeters: 0,
  durationSec: 0,
  fatigue: 'bajo',
  heartRate: 92,
  lastSyncMessage: 'Reloj conectado. Esperando inicio.',
  speedMps: 0,
  startedAt: null,
};

const STOPPED_ALERT_THRESHOLD_SECONDS = 20;

export function useTrekkingController() {
  const [ready, setReady] = useState(false);
  const [history, setHistory] = useState<SessionHistoryItem[]>([]);
  const [liveMetrics, setLiveMetrics] = useState<LiveSessionMetrics>(INITIAL_LIVE_METRICS);
  const [syncLogs, setSyncLogs] = useState<SyncLogEntry[]>([]);

  const liveMetricsRef = useRef(INITIAL_LIVE_METRICS);
  const locationRef = useRef(INITIAL_LOCATION);
  const trackerRef = useRef<ReturnType<typeof createLocationTracker> | null>(null);
  const fatigueStatsRef = useRef({ samples: 0, scoreTotal: 0 });

  const commitLiveMetrics = useCallback((nextMetrics: LiveSessionMetrics) => {
    liveMetricsRef.current = nextMetrics;
    setLiveMetrics(nextMetrics);
  }, []);

  const refreshHistory = useCallback(async () => {
    const nextHistory = await getSessionHistory();
    setHistory(nextHistory);
  }, []);

  const pushLog = useCallback((message: string) => {
    setSyncLogs((current) => appendLogEntry(current, message));
  }, []);

  const pushLogs = useCallback((messages: string[]) => {
    setSyncLogs((current) => appendLogEntries(current, messages));
  }, []);

  const mapToWatchPayload = useCallback((metrics: LiveSessionMetrics): PhoneToWatchPayload => {
    return {
      active: metrics.active,
      alerts: metrics.alerts,
      distanceMeters: metrics.distanceMeters,
      durationSec: metrics.durationSec,
      fatigue: metrics.fatigue,
      heartRate: metrics.heartRate,
      lastSyncMessage: metrics.lastSyncMessage,
      speedMps: metrics.speedMps,
      startedAt: metrics.startedAt,
    };
  }, []);

  const handleLocationUpdate = useCallback(
    (snapshot: LocationSnapshot) => {
      locationRef.current = snapshot;

      const currentMetrics = liveMetricsRef.current;
      if (!currentMetrics.active) {
        return;
      }

      const nextMetrics: LiveSessionMetrics = {
        ...currentMetrics,
        distanceMeters: snapshot.distanceMeters,
        durationSec: snapshot.durationSec,
        gpsMode: snapshot.source,
        speedMps: snapshot.speedMps,
      };

      commitLiveMetrics(nextMetrics);
    },
    [commitLiveMetrics]
  );

  const startSession = useCallback(async () => {
    if (liveMetricsRef.current.active) {
      return;
    }

    const startedAt = Date.now();
    const sessionId = await createSession(startedAt);

    locationRef.current = INITIAL_LOCATION;
    fatigueStatsRef.current = { samples: 0, scoreTotal: 0 };

    trackerRef.current?.stop();
    trackerRef.current = createLocationTracker();

    const nextMetrics: LiveSessionMetrics = {
      ...INITIAL_LIVE_METRICS,
      active: true,
      lastSyncMessage: buildLiveSyncMessage(0),
      sessionId,
      startedAt,
    };

    commitLiveMetrics(nextMetrics);
    bluetoothSimulator.sendPhoneUpdate(mapToWatchPayload(nextMetrics));
    pushLog(`Sesion ${sessionId} iniciada. Modo offline activo.`);

    void trackerRef.current.start(handleLocationUpdate);
    bluetoothSimulator.startSensorStream();
  }, [commitLiveMetrics, handleLocationUpdate, mapToWatchPayload, pushLog]);

  const stopSession = useCallback(async () => {
    const currentMetrics = liveMetricsRef.current;

    if (!currentMetrics.active || !currentMetrics.sessionId) {
      return;
    }

    bluetoothSimulator.stopSensorStream();
    trackerRef.current?.stop();
    trackerRef.current = null;
    liveMetricsRef.current = {
      ...currentMetrics,
      active: false,
    };

    const endedAt = Date.now();
    const durationSec = currentMetrics.startedAt
      ? Math.max(currentMetrics.durationSec, Math.floor((endedAt - currentMetrics.startedAt) / 1000))
      : currentMetrics.durationSec;

    const averageFatigue = fatigueLevelFromScore(
      fatigueStatsRef.current.samples === 0
        ? 1
        : fatigueStatsRef.current.scoreTotal / fatigueStatsRef.current.samples
    );

    await finishSession({
      averageFatigue,
      distanceMeters: currentMetrics.distanceMeters,
      durationSec,
      endedAt,
      sampleCount: currentMetrics.samplesStored,
      sessionId: currentMetrics.sessionId,
      syncStatus: 'simulated-sync',
    });

    pushLogs(buildSessionSyncMessages(currentMetrics.sessionId, currentMetrics.samplesStored));
    await refreshHistory();

    const idleMetrics: LiveSessionMetrics = {
      ...INITIAL_LIVE_METRICS,
      heartRate: currentMetrics.heartRate,
      lastSyncMessage: `Sesion ${currentMetrics.sessionId} cerrada y disponible en historial.`,
    };

    fatigueStatsRef.current = { samples: 0, scoreTotal: 0 };
    locationRef.current = INITIAL_LOCATION;

    commitLiveMetrics(idleMetrics);
    bluetoothSimulator.sendPhoneUpdate({
      ...INITIAL_WATCH_PAYLOAD,
      heartRate: currentMetrics.heartRate,
      lastSyncMessage: idleMetrics.lastSyncMessage,
    });
  }, [commitLiveMetrics, pushLogs, refreshHistory]);

  const raiseSos = useCallback(() => {
    const currentMetrics = liveMetricsRef.current;

    if (!currentMetrics.active) {
      pushLog('SOS ignorado: no hay trekking activo para reportar.');
      return;
    }

    const nextMetrics: LiveSessionMetrics = {
      ...currentMetrics,
      lastSyncMessage: `SOS de la sesion ${currentMetrics.sessionId} guardado localmente.`,
      sosRaised: true,
    };

    commitLiveMetrics(nextMetrics);
    bluetoothSimulator.sendPhoneUpdate(mapToWatchPayload(nextMetrics));
    pushLog(buildSosMessage(currentMetrics.sessionId));
  }, [commitLiveMetrics, mapToWatchPayload, pushLog]);

  const handleSensorSample = useCallback(
    async (sample: { heartRate: number; timestamp: number }) => {
      const currentMetrics = liveMetricsRef.current;

      if (!currentMetrics.active || !currentMetrics.sessionId) {
        return;
      }

      const currentLocation = locationRef.current;
      const durationSec = currentMetrics.startedAt
        ? Math.max(currentLocation.durationSec, Math.floor((sample.timestamp - currentMetrics.startedAt) / 1000))
        : currentLocation.durationSec;

      const fatigue = evaluateFatigue({
        durationSec,
        heartRate: sample.heartRate,
        speedMps: currentLocation.speedMps,
      });

      const alerts: WatchAlert[] = [];

      if (fatigue.level === 'alto') {
        alerts.push('Fatiga alta');
      }

      if (currentLocation.stoppedSeconds >= STOPPED_ALERT_THRESHOLD_SECONDS) {
        alerts.push('Detenido mucho tiempo');
      }

      await saveSample({
        alertLabel: alerts.length > 0 ? alerts.join(' | ') : null,
        durationSec,
        fatigue: fatigue.level,
        heartRate: sample.heartRate,
        latitude: currentLocation.latitude,
        longitude: currentLocation.longitude,
        sessionId: currentMetrics.sessionId,
        speedMps: currentLocation.speedMps,
        timestamp: sample.timestamp,
      });

      fatigueStatsRef.current = {
        samples: fatigueStatsRef.current.samples + 1,
        scoreTotal: fatigueStatsRef.current.scoreTotal + fatigue.score,
      };

      const nextMetrics: LiveSessionMetrics = {
        ...currentMetrics,
        alerts,
        distanceMeters: currentLocation.distanceMeters,
        durationSec,
        fatigue: fatigue.level,
        gpsMode: currentLocation.source,
        heartRate: sample.heartRate,
        lastSyncMessage: buildLiveSyncMessage(currentMetrics.samplesStored + 1),
        samplesStored: currentMetrics.samplesStored + 1,
        sosRaised: currentMetrics.sosRaised,
        speedMps: currentLocation.speedMps,
      };

      commitLiveMetrics(nextMetrics);
      bluetoothSimulator.sendPhoneUpdate(mapToWatchPayload(nextMetrics));
    },
    [commitLiveMetrics, mapToWatchPayload]
  );

  useEffect(() => {
    const handleCommand = (command: WatchCommand) => {
      void (async () => {
        if (command === 'start') {
          await startSession();
          return;
        }

        if (command === 'stop') {
          await stopSession();
          return;
        }

        raiseSos();
      })();
    };

    const unsubscribeCommands = bluetoothSimulator.subscribeToCommands(handleCommand);
    const unsubscribeWatchData = bluetoothSimulator.subscribeToWatchData((sample) => {
      void handleSensorSample(sample);
    });

    return () => {
      unsubscribeCommands();
      unsubscribeWatchData();
      trackerRef.current?.stop();
      bluetoothSimulator.stopSensorStream();
    };
  }, [handleSensorSample, raiseSos, startSession, stopSession]);

  useEffect(() => {
    void (async () => {
      await initDatabase();
      await refreshHistory();
      bluetoothSimulator.sendPhoneUpdate(INITIAL_WATCH_PAYLOAD);
      pushLog('SQLite lista. Esperando ordenes del reloj.');
      setReady(true);
    })();
  }, [pushLog, refreshHistory]);

  return {
    history,
    liveMetrics,
    ready,
    syncLogs,
  };
}

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
  GpsMode,
  LiveSessionMetrics,
  LocationSnapshot,
  PhoneToWatchPayload,
  SessionHistoryItem,
  StatusTone,
  SyncLogEntry,
  WatchAlert,
  WatchCommand,
} from '../../types';

const INITIAL_HEART_RATE = 92;
const BOOT_MESSAGE = 'Preparando SQLite, historial local, IA y puente reloj-celular...';
const STOPPED_ALERT_THRESHOLD_SECONDS = 20;

const INITIAL_LOCATION: LocationSnapshot = {
  distanceMeters: 0,
  durationSec: 0,
  latitude: null,
  longitude: null,
  source: 'simulated',
  speedMps: 0,
  stoppedSeconds: 0,
};

function createIdleMetrics(overrides: Partial<LiveSessionMetrics> = {}): LiveSessionMetrics {
  return {
    active: false,
    alerts: [],
    distanceMeters: 0,
    durationSec: 0,
    errorMessage: null,
    fatigue: 'bajo',
    gpsMode: 'checking',
    heartRate: INITIAL_HEART_RATE,
    lastSyncMessage: 'Listo para guardar datos locales sin internet.',
    lastUpdatedAt: Date.now(),
    pendingCommand: null,
    phase: 'idle',
    samplesStored: 0,
    sessionId: null,
    sosRaised: false,
    speedMps: 0,
    startedAt: null,
    statusMessage: 'Esperando inicio desde el reloj.',
    statusTone: 'neutral',
    storageLabel: 'SQLite local lista.',
    ...overrides,
  };
}

export function useTrekkingController() {
  const [ready, setReady] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState(BOOT_MESSAGE);
  const [initializationError, setInitializationError] = useState<string | null>(null);
  const [history, setHistory] = useState<SessionHistoryItem[]>([]);
  const [liveMetrics, setLiveMetrics] = useState<LiveSessionMetrics>(() => createIdleMetrics());
  const [syncLogs, setSyncLogs] = useState<SyncLogEntry[]>([]);

  const liveMetricsRef = useRef(createIdleMetrics());
  const locationRef = useRef(INITIAL_LOCATION);
  const trackerRef = useRef<ReturnType<typeof createLocationTracker> | null>(null);
  const fatigueStatsRef = useRef({ samples: 0, scoreTotal: 0 });

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
      errorMessage: metrics.errorMessage,
      fatigue: metrics.fatigue,
      gpsMode: metrics.gpsMode,
      heartRate: metrics.heartRate,
      lastSyncMessage: metrics.lastSyncMessage,
      lastUpdatedAt: metrics.lastUpdatedAt,
      pendingCommand: metrics.pendingCommand,
      phase: metrics.phase,
      speedMps: metrics.speedMps,
      startedAt: metrics.startedAt,
      statusMessage: metrics.statusMessage,
      statusTone: metrics.statusTone,
      storageLabel: metrics.storageLabel,
    };
  }, []);

  const publishMetrics = useCallback(
    (nextMetrics: LiveSessionMetrics) => {
      const stampedMetrics = {
        ...nextMetrics,
        lastUpdatedAt: Date.now(),
      };

      liveMetricsRef.current = stampedMetrics;
      setLiveMetrics(stampedMetrics);
      bluetoothSimulator.sendPhoneUpdate(mapToWatchPayload(stampedMetrics));
    },
    [mapToWatchPayload]
  );

  const refreshHistory = useCallback(async () => {
    const nextHistory = await getSessionHistory();
    setHistory(nextHistory);
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
        errorMessage: null,
        gpsMode: snapshot.source,
        pendingCommand: null,
        phase: 'active',
        speedMps: snapshot.speedMps,
        statusMessage:
          currentMetrics.phase === 'starting'
            ? snapshot.source === 'real'
              ? 'Trekking activo con GPS real.'
              : 'Trekking activo con GPS simulado.'
            : currentMetrics.statusMessage,
        statusTone: currentMetrics.phase === 'starting' ? 'success' : currentMetrics.statusTone,
      };

      publishMetrics(nextMetrics);
    },
    [publishMetrics]
  );

  const startSession = useCallback(async () => {
    const currentMetrics = liveMetricsRef.current;
    if (currentMetrics.active || currentMetrics.pendingCommand) {
      return;
    }

    const startedAt = Date.now();
    const preparingMetrics: LiveSessionMetrics = createIdleMetrics({
      active: true,
      gpsMode: 'checking',
      heartRate: currentMetrics.heartRate,
      lastSyncMessage: 'Creando sesion y preparando sensores...',
      pendingCommand: 'start',
      phase: 'starting',
      startedAt,
      statusMessage: 'Iniciando trekking. Preparando GPS y guardado local...',
      statusTone: 'info',
      storageLabel: 'Creando sesion en SQLite...',
    });

    publishMetrics(preparingMetrics);

    try {
      const sessionId = await createSession(startedAt);

      locationRef.current = INITIAL_LOCATION;
      fatigueStatsRef.current = { samples: 0, scoreTotal: 0 };

      trackerRef.current?.stop();
      trackerRef.current = createLocationTracker();

      const activeMetrics: LiveSessionMetrics = {
        ...preparingMetrics,
        lastSyncMessage: buildLiveSyncMessage(0),
        pendingCommand: null,
        phase: 'active',
        sessionId,
        statusMessage: 'Sesion iniciada. Esperando primera muestra del reloj...',
        statusTone: 'success',
        storageLabel: 'Sesion local creada. Todo quedara offline.',
      };

      publishMetrics(activeMetrics);
      pushLog(`Sesion ${sessionId} iniciada. Modo offline activo.`);

      void trackerRef.current.start(handleLocationUpdate);
      bluetoothSimulator.startSensorStream();
    } catch (error) {
      trackerRef.current?.stop();
      trackerRef.current = null;
      bluetoothSimulator.stopSensorStream();

      const failedMetrics = createIdleMetrics({
        errorMessage: describeError(error, 'No se pudo crear la sesion local.'),
        heartRate: currentMetrics.heartRate,
        lastSyncMessage: 'Inicio fallido. La sesion no se guardo.',
        statusMessage: 'No pudimos iniciar el trekking. Reintenta desde el reloj.',
        statusTone: 'danger',
        storageLabel: 'Error al crear la sesion en SQLite.',
      });

      publishMetrics(failedMetrics);
      pushLog(failedMetrics.errorMessage ?? 'Error al iniciar la sesion.');
    }
  }, [handleLocationUpdate, publishMetrics, pushLog]);

  const stopSession = useCallback(async () => {
    const currentMetrics = liveMetricsRef.current;

    if (!currentMetrics.active || !currentMetrics.sessionId || currentMetrics.pendingCommand) {
      return;
    }

    const stoppingMetrics: LiveSessionMetrics = {
      ...currentMetrics,
      errorMessage: null,
      lastSyncMessage: 'Cerrando sesion y guardando resumen local...',
      pendingCommand: 'stop',
      phase: 'stopping',
      statusMessage: 'Deteniendo trekking. Guardando datos y preparando historial...',
      statusTone: 'info',
      storageLabel: 'Persistiendo cierre de sesion en SQLite...',
    };

    publishMetrics(stoppingMetrics);

    bluetoothSimulator.stopSensorStream();
    trackerRef.current?.stop();
    trackerRef.current = null;

    // Evita que una muestra tardia vuelva a entrar mientras el usuario ve el estado "Guardando...".
    liveMetricsRef.current = {
      ...stoppingMetrics,
      active: false,
    };

    try {
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

      fatigueStatsRef.current = { samples: 0, scoreTotal: 0 };
      locationRef.current = INITIAL_LOCATION;

      publishMetrics(
        createIdleMetrics({
          heartRate: currentMetrics.heartRate,
          lastSyncMessage: `Sesion ${currentMetrics.sessionId} cerrada y disponible en historial.`,
          statusMessage: 'Sesion guardada correctamente. Puedes iniciar otra cuando quieras.',
          statusTone: 'success',
          storageLabel: 'Resumen local listo y visible en historial.',
        })
      );
    } catch (error) {
      const errorMessage = describeError(error, 'No se pudo cerrar la sesion local.');

      publishMetrics({
        ...stoppingMetrics,
        active: false,
        errorMessage,
        lastSyncMessage: 'El cierre fallo y requiere revision local.',
        pendingCommand: null,
        phase: 'idle',
        statusMessage: 'No pudimos guardar el cierre completo. Revisa el log antes de continuar.',
        statusTone: 'danger',
        storageLabel: 'Error al persistir el cierre de sesion.',
      });

      pushLog(errorMessage);
    }
  }, [publishMetrics, pushLogs, refreshHistory]);

  const raiseSos = useCallback(() => {
    const currentMetrics = liveMetricsRef.current;

    if (!currentMetrics.active || currentMetrics.pendingCommand === 'stop') {
      pushLog('SOS ignorado: no hay una sesion activa lista para reportar.');
      return;
    }

    const nextMetrics: LiveSessionMetrics = {
      ...currentMetrics,
      errorMessage: null,
      lastSyncMessage: `SOS de la sesion ${currentMetrics.sessionId} guardado localmente.`,
      sosRaised: true,
      statusMessage: 'SOS registrado en el celular. El seguimiento sigue activo.',
      statusTone: 'warning',
      storageLabel: 'Evento SOS persistido en SQLite local.',
    };

    publishMetrics(nextMetrics);
    pushLog(buildSosMessage(currentMetrics.sessionId));
  }, [publishMetrics, pushLog]);

  const handleSensorSample = useCallback(
    async (sample: { heartRate: number; timestamp: number }) => {
      const currentMetrics = liveMetricsRef.current;

      if (
        !currentMetrics.active ||
        !currentMetrics.sessionId ||
        currentMetrics.pendingCommand === 'stop'
      ) {
        return;
      }

      const currentLocation = locationRef.current;
      const durationSec = currentMetrics.startedAt
        ? Math.max(
            currentLocation.durationSec,
            Math.floor((sample.timestamp - currentMetrics.startedAt) / 1000)
          )
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

      try {
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

        const nextSampleCount = currentMetrics.samplesStored + 1;
        const statusForTelemetry = buildTelemetryStatus(alerts, currentMetrics.sosRaised, currentLocation.source);

        const nextMetrics: LiveSessionMetrics = {
          ...currentMetrics,
          alerts,
          distanceMeters: currentLocation.distanceMeters,
          durationSec,
          errorMessage: null,
          fatigue: fatigue.level,
          gpsMode: currentLocation.source,
          heartRate: sample.heartRate,
          lastSyncMessage: buildLiveSyncMessage(nextSampleCount),
          pendingCommand: null,
          phase: 'active',
          samplesStored: nextSampleCount,
          speedMps: currentLocation.speedMps,
          statusMessage: statusForTelemetry.message,
          statusTone: statusForTelemetry.tone,
          storageLabel: `${nextSampleCount} muestras HR guardadas en SQLite local.`,
        };

        publishMetrics(nextMetrics);
      } catch (error) {
        const errorMessage = describeError(error, 'No se pudo guardar la ultima muestra.');

        publishMetrics({
          ...currentMetrics,
          alerts,
          distanceMeters: currentLocation.distanceMeters,
          durationSec,
          errorMessage,
          fatigue: fatigue.level,
          gpsMode: currentLocation.source,
          heartRate: sample.heartRate,
          lastSyncMessage: 'La ultima muestra no se guardo correctamente.',
          phase: 'active',
          speedMps: currentLocation.speedMps,
          statusMessage: 'Error al persistir la telemetria local. El usuario sigue viendo el estado.',
          statusTone: 'danger',
          storageLabel: 'Fallo el ultimo guardado en SQLite.',
        });

        pushLog(errorMessage);
      }
    },
    [publishMetrics, pushLog]
  );

  const initializeApp = useCallback(async () => {
    setReady(false);
    setInitializationError(null);
    setLoadingMessage(BOOT_MESSAGE);

    try {
      await initDatabase();
      await refreshHistory();

      publishMetrics(
        createIdleMetrics({
          statusMessage: 'Celular listo. Esperando ordenes del smartwatch.',
          statusTone: 'success',
        })
      );

      pushLog('SQLite lista. Esperando ordenes del reloj.');
      setLoadingMessage('Todo listo para iniciar.');
      setReady(true);
    } catch (error) {
      const errorMessage = describeError(
        error,
        'No pudimos inicializar la base local ni el historial.'
      );

      publishMetrics(
        createIdleMetrics({
          errorMessage,
          lastSyncMessage: 'Inicio local fallido. Requiere reintento.',
          statusMessage: 'La app no pudo inicializarse correctamente.',
          statusTone: 'danger',
          storageLabel: 'SQLite no disponible.',
        })
      );

      pushLog(errorMessage);
      setInitializationError(errorMessage);
      setLoadingMessage('No pudimos completar la inicializacion.');
    }
  }, [publishMetrics, pushLog, refreshHistory]);

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
    void initializeApp();
  }, [initializeApp]);

  return {
    history,
    initializationError,
    liveMetrics,
    loadingMessage,
    ready,
    retryInitialization: initializeApp,
    syncLogs,
  };
}

function buildTelemetryStatus(
  alerts: WatchAlert[],
  sosRaised: boolean,
  gpsMode: GpsMode
): { message: string; tone: StatusTone } {
  if (alerts.includes('Fatiga alta') && alerts.includes('Detenido mucho tiempo')) {
    return {
      message: 'Alerta critica: fatiga alta y detencion prolongada.',
      tone: 'warning',
    };
  }

  if (alerts.includes('Fatiga alta')) {
    return {
      message: 'Alerta: fatiga alta detectada. Revisa el esfuerzo.',
      tone: 'warning',
    };
  }

  if (alerts.includes('Detenido mucho tiempo')) {
    return {
      message: 'Alerta: demasiado tiempo detenido en ruta.',
      tone: 'warning',
    };
  }

  if (sosRaised) {
    return {
      message: 'SOS registrado. El monitoreo continuo sigue activo.',
      tone: 'warning',
    };
  }

  return {
    message: gpsMode === 'real' ? 'Seguimiento estable con GPS real.' : 'Seguimiento estable con GPS simulado.',
    tone: 'success',
  };
}

function describeError(error: unknown, fallback: string) {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return fallback;
}

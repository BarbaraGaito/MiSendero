import { useEffect, useState } from 'react';

import { bluetoothSimulator } from '../../services/bluetoothSimulator';
import { PhoneToWatchPayload } from '../../types';

const INITIAL_WATCH_STATE: PhoneToWatchPayload = {
  active: false,
  alerts: [],
  distanceMeters: 0,
  durationSec: 0,
  errorMessage: null,
  fatigue: 'bajo',
  gpsMode: 'checking',
  heartRate: 92,
  lastSyncMessage: 'Reloj en espera.',
  lastUpdatedAt: Date.now(),
  pendingCommand: null,
  phase: 'idle',
  speedMps: 0,
  startedAt: null,
  statusMessage: 'Esperando datos del celular.',
  statusTone: 'neutral',
  storageLabel: 'Sincronizacion local pendiente.',
};

export function useWatchBridge() {
  const [watchState, setWatchState] = useState<PhoneToWatchPayload>(INITIAL_WATCH_STATE);
  const [liveDurationSec, setLiveDurationSec] = useState(0);

  useEffect(() => {
    const unsubscribe = bluetoothSimulator.subscribeToPhoneUpdates((payload) => {
      setWatchState(payload);
      setLiveDurationSec(payload.durationSec);
    });

    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!watchState.active || !watchState.startedAt) {
      setLiveDurationSec(watchState.durationSec);
      return;
    }

    const tick = () => {
      setLiveDurationSec(
        Math.max(watchState.durationSec, Math.floor((Date.now() - watchState.startedAt!) / 1000))
      );
    };

    tick();
    const interval = setInterval(tick, 1000);

    return () => {
      clearInterval(interval);
    };
  }, [watchState.active, watchState.durationSec, watchState.startedAt]);

  return {
    actions: {
      sendSos: () => bluetoothSimulator.sendWatchCommand('sos'),
      startTrekking: () => bluetoothSimulator.sendWatchCommand('start'),
      stopTrekking: () => bluetoothSimulator.sendWatchCommand('stop'),
    },
    watchState: {
      ...watchState,
      durationSec: liveDurationSec,
    },
  };
}

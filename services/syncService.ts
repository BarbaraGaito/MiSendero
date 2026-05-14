import { SyncLogEntry } from '../types';

export function appendLogEntry(current: SyncLogEntry[], message: string): SyncLogEntry[] {
  const nextEntry: SyncLogEntry = {
    id: Date.now() + Math.floor(Math.random() * 1000),
    message,
    timestamp: Date.now(),
  };

  return [nextEntry, ...current].slice(0, 8);
}

export function appendLogEntries(current: SyncLogEntry[], messages: string[]) {
  return messages.reduce((entries, message) => appendLogEntry(entries, message), current);
}

export function buildLiveSyncMessage(samplesStored: number) {
  return `Offline-first activo: ${samplesStored} muestras guardadas localmente.`;
}

export function buildSessionSyncMessages(sessionId: number, sampleCount: number) {
  return [
    `Sesion ${sessionId} cerrada y persistida en SQLite.`,
    `Sync simulado: ${sampleCount} eventos quedaron listos para enviarse cuando vuelva la conectividad.`,
  ];
}

export function buildSosMessage(sessionId: number | null) {
  return `SOS activado${sessionId ? ` para la sesion ${sessionId}` : ''}. Evento guardado en modo local.`;
}


import { FatigueLevel } from '../types';

export function formatDuration(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;

  if (hours > 0) {
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds
      .toString()
      .padStart(2, '0')}`;
  }

  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

export function formatDistance(distanceMeters: number) {
  if (distanceMeters < 1000) {
    return `${distanceMeters.toFixed(0)} m`;
  }

  return `${(distanceMeters / 1000).toFixed(2)} km`;
}

export function formatSpeed(speedMps: number) {
  return `${(speedMps * 3.6).toFixed(1)} km/h`;
}

export function formatDateTime(timestamp: number | null) {
  if (!timestamp) {
    return 'En curso';
  }

  return new Intl.DateTimeFormat('es-AR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(timestamp));
}

export function titleCaseFatigue(level: FatigueLevel) {
  return level.charAt(0).toUpperCase() + level.slice(1);
}

export function formatClockTime(timestamp: number | null) {
  if (!timestamp) {
    return 'Sin datos';
  }

  return new Intl.DateTimeFormat('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp));
}

import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { LiveSessionMetrics, SyncLogEntry } from '../../types';
import {
  formatClockTime,
  formatDistance,
  formatDuration,
  formatSpeed,
  titleCaseFatigue,
} from '../../utils/format';

interface PhoneDashboardProps {
  metrics: LiveSessionMetrics;
  syncLogs: SyncLogEntry[];
}

export function PhoneDashboard({ metrics, syncLogs }: PhoneDashboardProps) {
  return (
    <ScrollView
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
      style={styles.container}
    >
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Celular: estado operativo</Text>
        <Text style={styles.cardSubtitle}>
          El telefono procesa telemetria, calcula fatiga y confirma en todo momento si la app
          esta lista, guardando, en alerta o con error local.
        </Text>

        <View
          style={[
            styles.statusBanner,
            metrics.statusTone === 'info' && styles.statusBannerInfo,
            metrics.statusTone === 'success' && styles.statusBannerSuccess,
            metrics.statusTone === 'warning' && styles.statusBannerWarning,
            metrics.statusTone === 'danger' && styles.statusBannerDanger,
          ]}
        >
          <Text style={styles.statusText}>{metrics.statusMessage}</Text>
          <Text style={styles.statusMeta}>{phaseLabel(metrics)}</Text>
        </View>

        <View style={styles.metaRow}>
          <MetaPill label={gpsLabel(metrics)} />
          <MetaPill label={storageLabel(metrics)} />
          <MetaPill label={`Actualizado ${formatClockTime(metrics.lastUpdatedAt)}`} />
        </View>

        {metrics.errorMessage ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorTitle}>Atencion</Text>
            <Text style={styles.errorText}>{metrics.errorMessage}</Text>
          </View>
        ) : null}

        <View style={styles.metricsRow}>
          <Metric label="Duracion" value={formatDuration(metrics.durationSec)} />
          <Metric label="Distancia" value={formatDistance(metrics.distanceMeters)} />
        </View>

        <View style={styles.metricsRow}>
          <Metric label="Velocidad" value={formatSpeed(metrics.speedMps)} />
          <Metric label="Fatiga" value={titleCaseFatigue(metrics.fatigue)} />
        </View>

        <View style={styles.metricsRow}>
          <Metric label="HR guardadas" value={String(metrics.samplesStored)} />
          <Metric label="SOS" value={metrics.sosRaised ? 'Registrado' : 'Sin evento'} />
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Alertas visibles</Text>
        <Text style={styles.cardSubtitle}>
          El smartwatch recibe alertas de seguridad y el celular deja trazabilidad del motivo.
        </Text>

        {metrics.alerts.length === 0 ? (
          <Text style={styles.neutralText}>Sin alertas activas. El sistema sigue monitoreando.</Text>
        ) : (
          <View style={styles.alertRow}>
            {metrics.alerts.map((alert) => (
              <View key={alert} style={styles.alertPill}>
                <Text style={styles.alertText}>{alert}</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Persistencia offline-first</Text>
        <Text style={styles.liveSyncText}>{metrics.lastSyncMessage}</Text>
        <Text style={styles.neutralText}>{metrics.storageLabel}</Text>
        <Text style={styles.footnote}>
          Todo el flujo se mantiene local: sin APIs externas, sin dependencia de internet y con
          sincronizacion solo simulada por logs.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Log de eventos</Text>
        {syncLogs.length === 0 ? (
          <Text style={styles.neutralText}>Aun no hay eventos para mostrar.</Text>
        ) : (
          syncLogs.map((entry) => (
            <View key={entry.id} style={styles.logRow}>
              <Text style={styles.logTime}>{formatClockTime(entry.timestamp)}</Text>
              <Text style={styles.logText}>{entry.message}</Text>
            </View>
          ))
        )}
      </View>
    </ScrollView>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function MetaPill({ label }: { label: string }) {
  return (
    <View style={styles.metaPill}>
      <Text style={styles.metaPillText}>{label}</Text>
    </View>
  );
}

function phaseLabel(metrics: LiveSessionMetrics) {
  if (metrics.phase === 'starting') {
    return 'Estado: iniciando sesion';
  }

  if (metrics.phase === 'stopping') {
    return 'Estado: guardando cierre';
  }

  if (metrics.active) {
    return `Estado: sesion activa #${metrics.sessionId ?? '-'}`;
  }

  return 'Estado: listo para iniciar';
}

function gpsLabel(metrics: LiveSessionMetrics) {
  if (!metrics.active && metrics.phase === 'idle') {
    return 'GPS en espera';
  }

  if (metrics.gpsMode === 'checking') {
    return 'GPS comprobando...';
  }

  return metrics.gpsMode === 'real' ? 'GPS real' : 'GPS simulado';
}

function storageLabel(metrics: LiveSessionMetrics) {
  return metrics.pendingCommand === 'stop'
    ? 'Persistiendo resumen...'
    : metrics.pendingCommand === 'start'
      ? 'Preparando guardado...'
      : 'SQLite local';
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingBottom: 32,
    gap: 12,
  },
  card: {
    backgroundColor: '#F6F1E1',
    borderRadius: 28,
    padding: 18,
  },
  cardTitle: {
    color: '#28352C',
    fontSize: 20,
    fontWeight: '800',
    marginBottom: 6,
  },
  cardSubtitle: {
    color: '#536056',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 14,
  },
  statusBanner: {
    backgroundColor: '#E8E0C6',
    borderRadius: 20,
    marginBottom: 14,
    padding: 14,
  },
  statusBannerInfo: {
    backgroundColor: '#D7E8EE',
  },
  statusBannerSuccess: {
    backgroundColor: '#DDE8D8',
  },
  statusBannerWarning: {
    backgroundColor: '#F0E1BF',
  },
  statusBannerDanger: {
    backgroundColor: '#F0D3CB',
  },
  statusText: {
    color: '#26352A',
    fontSize: 16,
    fontWeight: '800',
    marginBottom: 4,
  },
  statusMeta: {
    color: '#607163',
    fontSize: 13,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 14,
  },
  metaPill: {
    backgroundColor: '#ECE3C7',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  metaPillText: {
    color: '#4A5A4D',
    fontSize: 12,
    fontWeight: '700',
  },
  errorBox: {
    backgroundColor: '#F3D2CA',
    borderRadius: 18,
    marginBottom: 14,
    padding: 12,
  },
  errorTitle: {
    color: '#6A2618',
    fontSize: 13,
    fontWeight: '800',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  errorText: {
    color: '#7B3423',
    fontSize: 14,
    lineHeight: 20,
  },
  metricsRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 10,
  },
  metricCard: {
    backgroundColor: '#EEF2E6',
    borderRadius: 18,
    flex: 1,
    padding: 12,
  },
  metricLabel: {
    color: '#6A776D',
    fontSize: 12,
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  metricValue: {
    color: '#1F2E24',
    fontSize: 17,
    fontWeight: '800',
  },
  alertRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  alertPill: {
    backgroundColor: '#B54F2F',
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  alertText: {
    color: '#FFF8F2',
    fontSize: 13,
    fontWeight: '700',
  },
  neutralText: {
    color: '#5D695F',
    fontSize: 14,
    lineHeight: 20,
  },
  liveSyncText: {
    color: '#223126',
    fontSize: 15,
    fontWeight: '700',
    marginBottom: 8,
  },
  footnote: {
    color: '#718075',
    fontSize: 12,
    lineHeight: 18,
    marginTop: 8,
  },
  logRow: {
    borderTopColor: '#E2D8BC',
    borderTopWidth: 1,
    paddingVertical: 10,
  },
  logTime: {
    color: '#8A6B36',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 3,
  },
  logText: {
    color: '#334238',
    fontSize: 14,
    lineHeight: 20,
  },
});

import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { LiveSessionMetrics, SyncLogEntry } from '../../types';
import { formatDistance, formatDuration, formatSpeed, titleCaseFatigue } from '../../utils/format';

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
        <Text style={styles.cardTitle}>Celular: motor del trekking</Text>
        <Text style={styles.cardSubtitle}>
          Recibe datos del reloj, ejecuta la IA de fatiga, calcula tracking y guarda todo en
          SQLite.
        </Text>

        <View style={styles.statusBanner}>
          <Text style={styles.statusText}>
            {metrics.active
              ? `Sesion activa #${metrics.sessionId ?? '-'}`
              : 'Esperando inicio desde el smartwatch'}
          </Text>
          <Text style={styles.statusMeta}>GPS: {metrics.gpsMode === 'real' ? 'real' : 'simulado'}</Text>
        </View>

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
          <Metric label="SOS" value={metrics.sosRaised ? 'Activado' : 'Sin evento'} />
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Alertas al reloj</Text>
        {metrics.alerts.length === 0 ? (
          <Text style={styles.neutralText}>Sin alertas visuales en este momento.</Text>
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
        <Text style={styles.cardTitle}>Offline-first</Text>
        <Text style={styles.liveSyncText}>{metrics.lastSyncMessage}</Text>
        <Text style={styles.neutralText}>
          La sincronizacion se simula con logs: no depende de internet ni de APIs externas.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Log de sincronizacion</Text>
        {syncLogs.length === 0 ? (
          <Text style={styles.neutralText}>Aun no hay eventos para mostrar.</Text>
        ) : (
          syncLogs.map((entry) => (
            <View key={entry.id} style={styles.logRow}>
              <Text style={styles.logTime}>
                {new Date(entry.timestamp).toLocaleTimeString('es-AR', {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </Text>
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


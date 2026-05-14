import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { SessionHistoryItem } from '../../types';
import { formatDateTime, formatDistance, formatDuration, titleCaseFatigue } from '../../utils/format';

interface HistoryListProps {
  sessions: SessionHistoryItem[];
}

export function HistoryList({ sessions }: HistoryListProps) {
  return (
    <ScrollView
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
      style={styles.container}
    >
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Sesiones guardadas localmente</Text>
        <Text style={styles.cardSubtitle}>
          Cada trekking queda persistido en SQLite aunque no haya conectividad.
        </Text>

        {sessions.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyTitle}>Todavia no hay sesiones</Text>
            <Text style={styles.emptyText}>
              Inicia un trekking desde el reloj y el historial aparecera aqui.
            </Text>
          </View>
        ) : (
          sessions.map((session) => (
            <View key={session.id} style={styles.sessionCard}>
              <View style={styles.sessionHeader}>
                <Text style={styles.sessionTitle}>Sesion #{session.id}</Text>
                <Text style={styles.sessionDate}>{formatDateTime(session.startedAt)}</Text>
              </View>

              <View style={styles.metricsRow}>
                <Metric label="Duracion" value={formatDuration(session.durationSec)} />
                <Metric label="Distancia" value={formatDistance(session.distanceMeters)} />
              </View>

              <View style={styles.metricsRow}>
                <Metric label="Fatiga promedio" value={titleCaseFatigue(session.averageFatigue)} />
                <Metric label="Muestras HR" value={String(session.sampleCount)} />
              </View>

              <Text style={styles.syncTag}>Sync: {session.syncStatus}</Text>
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
    color: '#546157',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 16,
  },
  emptyState: {
    backgroundColor: '#ECE3C7',
    borderRadius: 22,
    padding: 18,
  },
  emptyTitle: {
    color: '#314035',
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 6,
  },
  emptyText: {
    color: '#5F6C62',
    fontSize: 14,
    lineHeight: 20,
  },
  sessionCard: {
    backgroundColor: '#FFF9EA',
    borderColor: '#E2D5B1',
    borderRadius: 22,
    borderWidth: 1,
    marginBottom: 14,
    padding: 16,
  },
  sessionHeader: {
    marginBottom: 12,
  },
  sessionTitle: {
    color: '#2C3B2E',
    fontSize: 17,
    fontWeight: '800',
    marginBottom: 4,
  },
  sessionDate: {
    color: '#6B7569',
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
    color: '#627263',
    fontSize: 12,
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  metricValue: {
    color: '#223126',
    fontSize: 16,
    fontWeight: '800',
  },
  syncTag: {
    color: '#7A5D33',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 4,
  },
});


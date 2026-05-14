import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { PhoneToWatchPayload } from '../../types';
import { formatDuration, titleCaseFatigue } from '../../utils/format';

interface WatchFaceProps {
  onSos: () => void;
  onStart: () => void;
  onStop: () => void;
  state: PhoneToWatchPayload;
}

export function WatchFace({ onSos, onStart, onStop, state }: WatchFaceProps) {
  const fatigueStyle =
    state.fatigue === 'alto'
      ? styles.fatigueHigh
      : state.fatigue === 'medio'
        ? styles.fatigueMedium
        : styles.fatigueLow;

  return (
    <View style={styles.shell}>
      <Text style={styles.kicker}>Wear OS simulado</Text>

      <View style={styles.face}>
        <View style={styles.metricHero}>
          <Text style={styles.metricLabel}>HR</Text>
          <Text style={styles.metricValue}>{state.heartRate}</Text>
          <Text style={styles.metricUnit}>bpm</Text>
        </View>

        <View style={styles.sideMetrics}>
          <View style={styles.sideCard}>
            <Text style={styles.sideLabel}>Tiempo</Text>
            <Text style={styles.sideValue}>{formatDuration(state.durationSec)}</Text>
          </View>

          <View style={[styles.sideCard, fatigueStyle]}>
            <Text style={styles.sideLabel}>Fatiga</Text>
            <Text style={styles.sideValue}>{titleCaseFatigue(state.fatigue)}</Text>
          </View>
        </View>
      </View>

      <View style={styles.alertContainer}>
        {state.alerts.length === 0 ? (
          <Text style={styles.alertIdle}>Sin alertas visuales</Text>
        ) : (
          state.alerts.map((alert) => (
            <View key={alert} style={styles.alertBadge}>
              <Text style={styles.alertBadgeText}>{alert}</Text>
            </View>
          ))
        )}
      </View>

      <View style={styles.buttonRow}>
        <ActionButton
          disabled={state.active}
          label="Iniciar"
          onPress={onStart}
          tone="primary"
        />
        <ActionButton disabled={!state.active} label="Detener" onPress={onStop} tone="muted" />
        <ActionButton label="SOS" onPress={onSos} tone="danger" />
      </View>
    </View>
  );
}

function ActionButton({
  disabled = false,
  label,
  onPress,
  tone,
}: {
  disabled?: boolean;
  label: string;
  onPress: () => void;
  tone: 'danger' | 'muted' | 'primary';
}) {
  return (
    <TouchableOpacity
      activeOpacity={0.88}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.actionButton,
        tone === 'primary' && styles.actionPrimary,
        tone === 'muted' && styles.actionMuted,
        tone === 'danger' && styles.actionDanger,
        disabled && styles.actionDisabled,
      ]}
    >
      <Text style={[styles.actionText, disabled && styles.actionTextDisabled]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  shell: {
    backgroundColor: '#101714',
    borderColor: '#2F4337',
    borderRadius: 34,
    borderWidth: 1,
    padding: 18,
  },
  kicker: {
    color: '#AFC7A1',
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 1.1,
    marginBottom: 14,
    textTransform: 'uppercase',
  },
  face: {
    alignItems: 'center',
    backgroundColor: '#18231D',
    borderColor: '#314438',
    borderRadius: 32,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    padding: 16,
  },
  metricHero: {
    alignItems: 'center',
    backgroundColor: '#223126',
    borderRadius: 26,
    flex: 1,
    paddingVertical: 22,
  },
  metricLabel: {
    color: '#A2B99D',
    fontSize: 13,
    fontWeight: '700',
    marginBottom: 6,
  },
  metricValue: {
    color: '#FFF8E8',
    fontSize: 42,
    fontWeight: '900',
    lineHeight: 48,
  },
  metricUnit: {
    color: '#D7DFC8',
    fontSize: 14,
    marginTop: 4,
  },
  sideMetrics: {
    flex: 1,
    gap: 10,
  },
  sideCard: {
    backgroundColor: '#23322A',
    borderRadius: 22,
    padding: 14,
  },
  sideLabel: {
    color: '#ACC0AF',
    fontSize: 12,
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  sideValue: {
    color: '#FFF8E8',
    fontSize: 18,
    fontWeight: '800',
  },
  fatigueLow: {
    backgroundColor: '#2E4B32',
  },
  fatigueMedium: {
    backgroundColor: '#6C5924',
  },
  fatigueHigh: {
    backgroundColor: '#743421',
  },
  alertContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 14,
    minHeight: 32,
  },
  alertIdle: {
    color: '#8FA08F',
    fontSize: 13,
  },
  alertBadge: {
    backgroundColor: '#D35A32',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  alertBadgeText: {
    color: '#FFF7F0',
    fontSize: 12,
    fontWeight: '700',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
  },
  actionButton: {
    borderRadius: 18,
    flex: 1,
    paddingVertical: 13,
  },
  actionPrimary: {
    backgroundColor: '#DCC98D',
  },
  actionMuted: {
    backgroundColor: '#2C3C33',
  },
  actionDanger: {
    backgroundColor: '#B4492D',
  },
  actionDisabled: {
    opacity: 0.45,
  },
  actionText: {
    color: '#132119',
    fontSize: 14,
    fontWeight: '800',
    textAlign: 'center',
  },
  actionTextDisabled: {
    color: '#E6E7DE',
  },
});


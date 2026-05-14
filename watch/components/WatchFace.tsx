import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { PhoneToWatchPayload } from '../../types';
import { formatClockTime, formatDuration, titleCaseFatigue } from '../../utils/format';

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

  const actionInProgress = state.pendingCommand !== null;

  return (
    <View style={styles.shell}>
      <View style={styles.headerRow}>
        <Text style={styles.kicker}>Wear OS simulado</Text>
        <View
          style={[
            styles.statusBadge,
            state.statusTone === 'info' && styles.statusBadgeInfo,
            state.statusTone === 'success' && styles.statusBadgeSuccess,
            state.statusTone === 'warning' && styles.statusBadgeWarning,
            state.statusTone === 'danger' && styles.statusBadgeDanger,
          ]}
        >
          <Text style={styles.statusBadgeText}>{phaseLabel(state)}</Text>
        </View>
      </View>

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

      <View style={styles.statusPanel}>
        <Text style={styles.statusPanelTitle}>{state.statusMessage}</Text>
        <Text style={styles.statusPanelText}>{state.lastSyncMessage}</Text>
        <Text style={styles.statusPanelMeta}>
          {gpsLabel(state)} - {state.storageLabel}
        </Text>
        <Text style={styles.statusPanelMeta}>
          Ultima actualizacion: {formatClockTime(state.lastUpdatedAt)}
        </Text>
      </View>

      {state.errorMessage ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{state.errorMessage}</Text>
        </View>
      ) : null}

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
          disabled={state.active || actionInProgress}
          label={state.pendingCommand === 'start' ? 'Iniciando' : 'Iniciar'}
          onPress={onStart}
          tone="primary"
        />
        <ActionButton
          disabled={!state.active || actionInProgress}
          label={state.pendingCommand === 'stop' ? 'Guardando' : 'Detener'}
          onPress={onStop}
          tone="muted"
        />
        <ActionButton
          disabled={!state.active || state.pendingCommand === 'stop'}
          label="SOS"
          onPress={onSos}
          tone="danger"
        />
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

function phaseLabel(state: PhoneToWatchPayload) {
  if (state.pendingCommand === 'start' || state.phase === 'starting') {
    return 'Iniciando';
  }

  if (state.pendingCommand === 'stop' || state.phase === 'stopping') {
    return 'Guardando';
  }

  if (state.active) {
    return 'Activo';
  }

  return 'En espera';
}

function gpsLabel(state: PhoneToWatchPayload) {
  if (!state.active && state.phase === 'idle') {
    return 'GPS en espera';
  }

  if (state.gpsMode === 'checking') {
    return 'GPS comprobando';
  }

  return state.gpsMode === 'real' ? 'GPS real' : 'GPS simulado';
}

const styles = StyleSheet.create({
  shell: {
    backgroundColor: '#101714',
    borderColor: '#2F4337',
    borderRadius: 34,
    borderWidth: 1,
    padding: 18,
  },
  headerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  kicker: {
    color: '#AFC7A1',
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  statusBadge: {
    backgroundColor: '#2A3732',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  statusBadgeInfo: {
    backgroundColor: '#21414D',
  },
  statusBadgeSuccess: {
    backgroundColor: '#294032',
  },
  statusBadgeWarning: {
    backgroundColor: '#624C20',
  },
  statusBadgeDanger: {
    backgroundColor: '#6B3226',
  },
  statusBadgeText: {
    color: '#F8F5E8',
    fontSize: 12,
    fontWeight: '800',
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
  statusPanel: {
    backgroundColor: '#1A2520',
    borderRadius: 20,
    marginTop: 14,
    padding: 14,
  },
  statusPanelTitle: {
    color: '#FFF8E8',
    fontSize: 14,
    fontWeight: '800',
    marginBottom: 4,
  },
  statusPanelText: {
    color: '#D3DDCB',
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 6,
  },
  statusPanelMeta: {
    color: '#9FB2A3',
    fontSize: 12,
    lineHeight: 17,
  },
  errorBox: {
    backgroundColor: '#542B24',
    borderRadius: 18,
    marginTop: 12,
    padding: 12,
  },
  errorText: {
    color: '#FFD8CF',
    fontSize: 13,
    lineHeight: 18,
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

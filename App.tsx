import { useState } from 'react';
import {
  ActivityIndicator,
  SafeAreaView,
  StatusBar,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

import { HistoryList } from './mobile/components/HistoryList';
import { PhoneDashboard } from './mobile/components/PhoneDashboard';
import { useTrekkingController } from './mobile/hooks/useTrekkingController';
import { WatchFace } from './watch/components/WatchFace';
import { useWatchBridge } from './watch/hooks/useWatchBridge';

type AppTab = 'live' | 'history';

export default function App() {
  const [activeTab, setActiveTab] = useState<AppTab>('live');
  const {
    ready,
    loadingMessage,
    initializationError,
    retryInitialization,
    history,
    liveMetrics,
    syncLogs,
  } = useTrekkingController();
  const { actions, watchState } = useWatchBridge();

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" />
      <View pointerEvents="none" style={styles.glowLarge} />
      <View pointerEvents="none" style={styles.glowSmall} />

      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.eyebrow}>MiSendero</Text>
          <Text style={styles.title}>MVP wearable-first para trekking offline</Text>
          <Text style={styles.subtitle}>
            El reloj manda, el celular procesa y todo queda guardado localmente.
          </Text>
        </View>

        {!ready && initializationError ? (
          <View style={styles.errorCard}>
            <Text style={styles.errorTitle}>La app necesita recuperarse</Text>
            <Text style={styles.errorText}>{initializationError}</Text>
            <TouchableOpacity
              activeOpacity={0.9}
              onPress={() => {
                void retryInitialization();
              }}
              style={styles.retryButton}
            >
              <Text style={styles.retryButtonText}>Reintentar inicializacion</Text>
            </TouchableOpacity>
          </View>
        ) : !ready ? (
          <View style={styles.loadingCard}>
            <ActivityIndicator color="#F4E7C6" size="large" />
            <Text style={styles.loadingText}>{loadingMessage}</Text>
            <Text style={styles.loadingSubtext}>
              La interfaz se habilita cuando la persistencia local y el puente con el reloj quedan
              listos.
            </Text>
          </View>
        ) : (
          <>
            <View
              style={[
                styles.globalBanner,
                liveMetrics.statusTone === 'success' && styles.globalBannerSuccess,
                liveMetrics.statusTone === 'warning' && styles.globalBannerWarning,
                liveMetrics.statusTone === 'danger' && styles.globalBannerDanger,
                liveMetrics.statusTone === 'info' && styles.globalBannerInfo,
              ]}
            >
              <Text style={styles.globalBannerTitle}>{liveMetrics.statusMessage}</Text>
              <Text style={styles.globalBannerText}>{liveMetrics.storageLabel}</Text>
            </View>

            <WatchFace
              state={watchState}
              onSos={actions.sendSos}
              onStart={actions.startTrekking}
              onStop={actions.stopTrekking}
            />

            <View style={styles.tabRow}>
              <TouchableOpacity
                activeOpacity={0.9}
                onPress={() => setActiveTab('live')}
                style={[styles.tabButton, activeTab === 'live' && styles.tabButtonActive]}
              >
                <Text
                  style={[styles.tabButtonText, activeTab === 'live' && styles.tabButtonTextActive]}
                >
                  Celular
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                activeOpacity={0.9}
                onPress={() => setActiveTab('history')}
                style={[styles.tabButton, activeTab === 'history' && styles.tabButtonActive]}
              >
                <Text
                  style={[
                    styles.tabButtonText,
                    activeTab === 'history' && styles.tabButtonTextActive,
                  ]}
                >
                  Historial
                </Text>
              </TouchableOpacity>
            </View>

            {activeTab === 'live' ? (
              <PhoneDashboard metrics={liveMetrics} syncLogs={syncLogs} />
            ) : (
              <HistoryList sessions={history} />
            )}
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#1B2A22',
  },
  container: {
    flex: 1,
    paddingHorizontal: 18,
    paddingTop: 10,
    paddingBottom: 18,
  },
  header: {
    marginBottom: 18,
  },
  eyebrow: {
    color: '#DCC98D',
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 1.2,
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  title: {
    color: '#FFF8E7',
    fontSize: 28,
    fontWeight: '800',
    lineHeight: 34,
    marginBottom: 8,
  },
  subtitle: {
    color: '#C8D4CC',
    fontSize: 15,
    lineHeight: 22,
  },
  tabRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 18,
    marginBottom: 12,
  },
  tabButton: {
    backgroundColor: '#25382C',
    borderColor: '#345341',
    borderRadius: 16,
    borderWidth: 1,
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
  },
  tabButtonActive: {
    backgroundColor: '#DCC98D',
    borderColor: '#DCC98D',
  },
  tabButtonText: {
    color: '#DBE4DA',
    fontSize: 15,
    fontWeight: '700',
  },
  tabButtonTextActive: {
    color: '#223126',
  },
  loadingCard: {
    backgroundColor: '#24372C',
    borderColor: '#38513F',
    borderRadius: 28,
    borderWidth: 1,
    padding: 28,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  loadingText: {
    color: '#E6EBD9',
    fontSize: 15,
    fontWeight: '700',
    textAlign: 'center',
  },
  loadingSubtext: {
    color: '#C5D1C6',
    fontSize: 13,
    lineHeight: 19,
    textAlign: 'center',
  },
  errorCard: {
    backgroundColor: '#432520',
    borderColor: '#80473D',
    borderRadius: 28,
    borderWidth: 1,
    padding: 24,
    gap: 12,
  },
  errorTitle: {
    color: '#FFF4EE',
    fontSize: 22,
    fontWeight: '800',
  },
  errorText: {
    color: '#F3D0C5',
    fontSize: 14,
    lineHeight: 21,
  },
  retryButton: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#F2D7A8',
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  retryButtonText: {
    color: '#2E2417',
    fontSize: 14,
    fontWeight: '800',
  },
  globalBanner: {
    backgroundColor: '#27382E',
    borderColor: '#3A5344',
    borderRadius: 22,
    borderWidth: 1,
    marginBottom: 14,
    padding: 14,
  },
  globalBannerInfo: {
    backgroundColor: '#1F3944',
    borderColor: '#3E6572',
  },
  globalBannerSuccess: {
    backgroundColor: '#243B2C',
    borderColor: '#41614D',
  },
  globalBannerWarning: {
    backgroundColor: '#4A371E',
    borderColor: '#8B6A35',
  },
  globalBannerDanger: {
    backgroundColor: '#482621',
    borderColor: '#8A4B40',
  },
  globalBannerTitle: {
    color: '#FFF8E7',
    fontSize: 15,
    fontWeight: '800',
    marginBottom: 4,
  },
  globalBannerText: {
    color: '#D5DFD3',
    fontSize: 13,
    lineHeight: 18,
  },
  glowLarge: {
    position: 'absolute',
    top: -70,
    right: -20,
    width: 220,
    height: 220,
    borderRadius: 110,
    backgroundColor: '#5C7A4F',
    opacity: 0.15,
  },
  glowSmall: {
    position: 'absolute',
    bottom: 120,
    left: -40,
    width: 180,
    height: 180,
    borderRadius: 90,
    backgroundColor: '#C46B3D',
    opacity: 0.12,
  },
});

import { useCallback, useEffect, useState } from "react";
import { router, useFocusEffect } from "expo-router";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
  SettingRow,
  StatusNotice,
  colors,
} from "../components/MiSenderoUI";
import { getProfile } from "../../services/api";
import { formatKilometers } from "../../services/geoUtils";
import {
  clearAuthSession,
  getAuthSession,
  saveAuthSession,
} from "../../services/authSession";
import { EmergencyContact, Profile, WearableRuntimeStatus } from "../../types";
import {
  getPrivacyPreferences,
  PrivacyPreferences,
  savePrivacyPreferences,
} from "../../services/privacyConsent";
import {
  getTestingLocationMode,
  saveTestingLocationMode,
  TestingLocationMode,
} from "../../services/testingMode";
import {
  AppPreferences,
  getAppPreferences,
  saveAppPreferences,
} from "../../services/appPreferences";
import {
  ExperienceProfile,
  getExperienceProfile,
} from "../../services/experienceProfile";
import { getEmergencyContact } from "../../services/emergencyContact";
import {
  getOfflineMapsSummary,
  OfflineMapsSummary,
} from "../../services/offlineMaps";
import {
  getSessionsSummary,
  SessionsSummary,
} from "../../database/sessionsRepository";
import { getWearableRuntimeStatus } from "../../services/wearableMetrics";
import {
  discardExhaustedOperations,
  getSyncSummary,
  runSync,
  SyncSummary,
} from "../../services/syncQueue";
import {
  adminAiModelMetrics,
  AiTrainingMetrics,
} from "../../ai/modelMetrics";

const emptySessionsSummary: SessionsSummary = {
  totalDistance: 0,
  completedCount: 0,
  currentMonthCount: 0,
};

const emptyOfflineMapsSummary: OfflineMapsSummary = {
  count: 0,
  totalSizeMb: 0,
};

const emptySyncSummary: SyncSummary = {
  pending: 0,
  syncing: 0,
  synced: 0,
  failed: 0,
  abandoned: 0,
  exhausted: 0,
};

const formatDistance = (meters: number) => formatKilometers(meters / 1000);

const formatStorage = (sizeMb: number) => {
  if (sizeMb >= 1024) {
    return `${(sizeMb / 1024).toLocaleString("es-AR", {
      maximumFractionDigits: 1,
    })} GB`;
  }

  return `${sizeMb.toLocaleString("es-AR", {
    maximumFractionDigits: 0,
  })} MB`;
};

const formatPercent = (value: number) => `${Math.round(value * 100)}%`;

const formatDate = (value: string) =>
  new Date(value).toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });

const loadProfileData = async () => {
  const session = await getAuthSession();

  if (!session) return null;

  const profile = await getProfile(session.token);
  const [
    privacy,
    testingMode,
    appPreferences,
    experienceProfile,
    emergencyContact,
    sessionsSummary,
    offlineMapsSummary,
    wearableRuntime,
    syncSummary,
  ] = await Promise.all([
    getPrivacyPreferences(),
    getTestingLocationMode(),
    getAppPreferences(),
    getExperienceProfile(),
    getEmergencyContact(),
    getSessionsSummary(),
    getOfflineMapsSummary(),
    getWearableRuntimeStatus(),
    getSyncSummary(),
  ]);

  return {
    session,
    profile,
    privacy,
    testingMode,
    appPreferences,
    experienceProfile,
    emergencyContact,
    sessionsSummary,
    offlineMapsSummary,
    wearableRuntime,
    syncSummary,
  };
};

export default function ProfileScreen() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [privacy, setPrivacy] = useState<PrivacyPreferences>({
    sensitiveDataConsent: false,
    analyticsTrainingConsent: false,
    updatedAt: null,
  });
  const [testingLocationMode, setTestingLocationMode] =
    useState<TestingLocationMode>({
      enabled: false,
      updatedAt: null,
    });
  const [appPreferences, setAppPreferences] = useState<AppPreferences>({
    notificationsEnabled: true,
    distanceUnit: "km",
    batterySaverEnabled: true,
    externalSensorLinked: false,
    updatedAt: null,
  });
  const [experienceProfile, setExperienceProfile] =
    useState<ExperienceProfile>({
      completed: false,
      skipped: false,
      level: null,
      answers: {},
      completedAt: null,
      skippedAt: null,
      updatedAt: null,
    });
  const [emergencyContact, setEmergencyContact] =
    useState<EmergencyContact | null>(null);
  const [sessionsSummary, setSessionsSummary] =
    useState<SessionsSummary>(emptySessionsSummary);
  const [offlineMapsSummary, setOfflineMapsSummary] =
    useState<OfflineMapsSummary>(emptyOfflineMapsSummary);
  const [wearableRuntime, setWearableRuntime] =
    useState<WearableRuntimeStatus | null>(null);
  const [syncSummary, setSyncSummary] = useState<SyncSummary>(emptySyncSummary);
  const [isSyncing, setIsSyncing] = useState(false);

  const refreshWearableRuntime = useCallback(async () => {
    setWearableRuntime(await getWearableRuntimeStatus());
  }, []);

  const refreshSyncSummary = useCallback(async () => {
    setSyncSummary(await getSyncSummary());
  }, []);

  const triggerSync = useCallback(async () => {
    if (isSyncing) return;

    setIsSyncing(true);
    try {
      await runSync();
    } finally {
      await refreshSyncSummary();
      setIsSyncing(false);
    }
  }, [isSyncing, refreshSyncSummary]);

  const discardExhausted = useCallback(() => {
    Alert.alert(
      "Descartar pendientes con error",
      "Estos reportes, actividades o alertas no se pudieron enviar despues de varios intentos. Si los descartas, no se van a volver a intentar.",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Descartar",
          style: "destructive",
          onPress: async () => {
            await discardExhaustedOperations();
            await refreshSyncSummary();
          },
        },
      ]
    );
  }, [refreshSyncSummary]);

  const loadProfile = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const data = await loadProfileData();

      if (!data) {
        router.replace("/");
        return;
      }

      runSync()
        .catch(() => null)
        .finally(refreshSyncSummary);

      if (data.profile.user) {
        await saveAuthSession({
          token: data.session.token,
          user: data.profile.user,
        });
      }

      if (data.profile.user?.role !== "admin" && data.testingMode.enabled) {
        await saveTestingLocationMode(false);
      }

      setProfile(data.profile);
      setPrivacy(data.privacy);
      setAppPreferences(data.appPreferences);
      setExperienceProfile(data.experienceProfile);
      setEmergencyContact(data.emergencyContact);
      setSessionsSummary(data.sessionsSummary);
      setOfflineMapsSummary(data.offlineMapsSummary);
      setWearableRuntime(data.wearableRuntime);
      setSyncSummary(data.syncSummary);
      setTestingLocationMode(
        data.profile.user?.role === "admin"
          ? data.testingMode
          : { enabled: false, updatedAt: null }
      );
    } catch {
      setError("No pudimos cargar tu perfil en este momento.");
    } finally {
      setIsLoading(false);
    }
  }, [refreshSyncSummary]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  useFocusEffect(
    useCallback(() => {
      refreshWearableRuntime();
      refreshSyncSummary();
    }, [refreshWearableRuntime, refreshSyncSummary])
  );

  const logout = async () => {
    Alert.alert(
      "Cerrar sesion",
      "Vas a salir de MiSendero en este dispositivo.",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Cerrar sesion",
          style: "destructive",
          onPress: async () => {
            await clearAuthSession();
            router.replace("/");
          },
        },
      ]
    );
  };

  const updatePrivacy = async (nextPrivacy: Omit<PrivacyPreferences, "updatedAt">) => {
    await savePrivacyPreferences(nextPrivacy);
    const [privacyPreferences, wearable] = await Promise.all([
      getPrivacyPreferences(),
      getWearableRuntimeStatus(),
    ]);
    setPrivacy(privacyPreferences);
    setWearableRuntime(wearable);
  };

  const updateTestingLocationMode = async (enabled: boolean) => {
    if (profile?.user?.role !== "admin") return;

    await saveTestingLocationMode(enabled);
    setTestingLocationMode(await getTestingLocationMode());
  };

  const updateAppPreferences = async (
    nextPreferences: Omit<AppPreferences, "updatedAt">
  ) => {
    await saveAppPreferences(nextPreferences);
    setAppPreferences(await getAppPreferences());
  };

  const user = profile?.user;
  const displayName = user?.name || "Invitado";
  const email = user?.email || "Inicia sesion para ver tu cuenta";
  const initial = displayName.trim().charAt(0).toUpperCase() || "U";
  const isAdmin = user?.role === "admin";

  return (
    <AppScreen activeTab="perfil">
      <ScrollView showsVerticalScrollIndicator={false}>
        <ScreenTitle
          eyebrow="Perfil y ajustes"
          title={displayName}
          subtitle="Tu cuenta y preferencias de seguridad."
        />

        <ProfileNotices
          error={error}
          isLoading={isLoading}
          onRetry={loadProfile}
        />
        <ProfileHeaderCard
          displayName={displayName}
          email={email}
          initial={initial}
          sessionsSummary={sessionsSummary}
        />
        <SyncCard
          discardExhausted={discardExhausted}
          isSyncing={isSyncing}
          syncSummary={syncSummary}
          triggerSync={triggerSync}
        />
        <OfflineMapsCard offlineMapsSummary={offlineMapsSummary} />
        <DevicesCard
          appPreferences={appPreferences}
          emergencyContact={emergencyContact}
          updateAppPreferences={updateAppPreferences}
          wearableRuntime={wearableRuntime}
        />
        <PreferencesCard
          appPreferences={appPreferences}
          experienceProfile={experienceProfile}
          updateAppPreferences={updateAppPreferences}
        />
        <PrivacyCard privacy={privacy} updatePrivacy={updatePrivacy} />
        <AdminAiMetricsCard isAdmin={isAdmin} />
        <AdminTestingCard
          isAdmin={isAdmin}
          testingLocationMode={testingLocationMode}
          updateTestingLocationMode={updateTestingLocationMode}
          wearableRuntime={wearableRuntime}
        />
        <PrimaryButton
          label="Cerrar sesion"
          icon="log-out-outline"
          tone="secondary"
          onPress={logout}
        />
      </ScrollView>
    </AppScreen>
  );
}

function ProfileNotices({
  error,
  isLoading,
  onRetry,
}: {
  error: string | null;
  isLoading: boolean;
  onRetry: () => void;
}) {
  return (
    <>
      {isLoading ? (
        <StatusNotice
          isLoading
          message="Cargando cuenta, mapas, seguridad y sincronizacion."
          title="Cargando perfil"
        />
      ) : null}
      {error ? (
        <StatusNotice
          actionLabel="Reintentar"
          message={error}
          onAction={onRetry}
          title="No se pudo cargar"
          tone="error"
        />
      ) : null}
    </>
  );
}

function ProfileHeaderCard({
  displayName,
  email,
  initial,
  sessionsSummary,
}: {
  displayName: string;
  email: string;
  initial: string;
  sessionsSummary: SessionsSummary;
}) {
  return (
    <Card tone="green">
      <View style={styles.profileRow}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initial}</Text>
        </View>
        <View style={styles.profileText}>
          <Text style={styles.profileName}>{displayName}</Text>
          <Text style={styles.profileEmail}>{email}</Text>
          <Text style={styles.profileMeta}>
            {sessionsSummary.completedCount} rutas completadas -{" "}
            {formatDistance(sessionsSummary.totalDistance)}
          </Text>
        </View>
      </View>
    </Card>
  );
}

function SyncCard({
  discardExhausted,
  isSyncing,
  syncSummary,
  triggerSync,
}: {
  discardExhausted: () => void;
  isSyncing: boolean;
  syncSummary: SyncSummary;
  triggerSync: () => void;
}) {
  const pendingCount = syncSummary.pending + syncSummary.syncing;

  return (
    <Card>
      <Text style={styles.cardTitle}>Sincronizacion</Text>
      <Text style={styles.privacyText}>
        Reportes, actividades y alertas creados sin senal quedan en cola local
        hasta recuperar conectividad.
      </Text>
      <SettingRow
        label="Pendientes de enviar"
        value={pendingCount > 0 ? `${pendingCount}` : "Al dia"}
        onPress={triggerSync}
      />
      <View style={styles.syncGrid}>
        <SyncMetric label="Pendientes" value={pendingCount} />
        <SyncMetric label="Enviados" value={syncSummary.synced} />
        <SyncMetric label="Con error" value={syncSummary.failed} />
        <SyncMetric label="Descartados" value={syncSummary.abandoned} />
      </View>
      <SyncWarnings
        discardExhausted={discardExhausted}
        syncSummary={syncSummary}
        triggerSync={triggerSync}
      />
      {isSyncing ? <Text style={styles.privacyText}>Sincronizando...</Text> : null}
    </Card>
  );
}

function SyncWarnings({
  discardExhausted,
  syncSummary,
  triggerSync,
}: {
  discardExhausted: () => void;
  syncSummary: SyncSummary;
  triggerSync: () => void;
}) {
  return (
    <>
      {syncSummary.failed > 0 ? (
        <>
          <Text style={styles.warningText}>
            Hay actividades con error. Podes reintentar la sincronizacion.
          </Text>
          <SettingRow
            label="Con error, reintentar"
            value={`${syncSummary.failed}`}
            onPress={triggerSync}
          />
        </>
      ) : null}
      {syncSummary.exhausted > 0 ? (
        <>
          <Text style={styles.warningText}>
            {syncSummary.exhausted} no se pudieron enviar tras varios intentos.
            Podes seguir esperando senal o descartarlos.
          </Text>
          <SettingRow
            label="Descartar pendientes con error"
            value={`${syncSummary.exhausted}`}
            onPress={discardExhausted}
          />
        </>
      ) : null}
    </>
  );
}

function OfflineMapsCard({
  offlineMapsSummary,
}: {
  offlineMapsSummary: OfflineMapsSummary;
}) {
  const value =
    offlineMapsSummary.count > 0
      ? `${offlineMapsSummary.count} - ${formatStorage(offlineMapsSummary.totalSizeMb)}`
      : "Sin descargas";

  return (
    <Card>
      <Text style={styles.cardTitle}>Mapas sin conexion</Text>
      <SettingRow
        label="Mapas descargados"
        value={value}
        onPress={() => router.push("/offline-mapas-descargados")}
      />
    </Card>
  );
}

function DevicesCard({
  appPreferences,
  emergencyContact,
  updateAppPreferences,
  wearableRuntime,
}: {
  appPreferences: AppPreferences;
  emergencyContact: EmergencyContact | null;
  updateAppPreferences: (preferences: Omit<AppPreferences, "updatedAt">) => void;
  wearableRuntime: WearableRuntimeStatus | null;
}) {
  return (
    <Card>
      <Text style={styles.cardTitle}>Seguridad y dispositivos</Text>
      <SettingRow
        label="Contacto de emergencia"
        value={emergencyContact ? emergencyContact.name : "No configurado"}
        onPress={() => router.push("/contacto-seguridad")}
      />
      <SettingRow
        label="Reloj o sensor externo"
        value={getWearableLabel(wearableRuntime)}
        onPress={() => router.push("/reloj-salud")}
      />
      <SettingRow
        label="Modo ahorro de bateria"
        value={appPreferences.batterySaverEnabled ? "Activo" : "Desactivado"}
        onPress={() =>
          updateAppPreferences({
            notificationsEnabled: appPreferences.notificationsEnabled,
            distanceUnit: appPreferences.distanceUnit,
            batterySaverEnabled: !appPreferences.batterySaverEnabled,
            externalSensorLinked: appPreferences.externalSensorLinked,
          })
        }
      />
    </Card>
  );
}

function PreferencesCard({
  appPreferences,
  experienceProfile,
  updateAppPreferences,
}: {
  appPreferences: AppPreferences;
  experienceProfile: ExperienceProfile;
  updateAppPreferences: (preferences: Omit<AppPreferences, "updatedAt">) => void;
}) {
  return (
    <Card>
      <Text style={styles.cardTitle}>Preferencias</Text>
      <SettingRow
        label="Perfil de experiencia"
        value={getExperienceProfileLabel(experienceProfile)}
        onPress={() =>
          router.push({
            pathname: "/onboarding-experiencia",
            params: { mode: "edit" },
          })
        }
      />
      <SettingRow
        label="Notificaciones"
        value={appPreferences.notificationsEnabled ? "Activadas" : "Desactivadas"}
        onPress={() =>
          updateAppPreferences({
            notificationsEnabled: !appPreferences.notificationsEnabled,
            distanceUnit: appPreferences.distanceUnit,
            batterySaverEnabled: appPreferences.batterySaverEnabled,
            externalSensorLinked: appPreferences.externalSensorLinked,
          })
        }
      />
      <SettingRow
        label="Unidades"
        value={appPreferences.distanceUnit === "km" ? "Kilometros" : "Millas"}
        onPress={() =>
          updateAppPreferences({
            notificationsEnabled: appPreferences.notificationsEnabled,
            distanceUnit: appPreferences.distanceUnit === "km" ? "mi" : "km",
            batterySaverEnabled: appPreferences.batterySaverEnabled,
            externalSensorLinked: appPreferences.externalSensorLinked,
          })
        }
      />
    </Card>
  );
}

function PrivacyCard({
  privacy,
  updatePrivacy,
}: {
  privacy: PrivacyPreferences;
  updatePrivacy: (privacy: Omit<PrivacyPreferences, "updatedAt">) => void;
}) {
  return (
    <Card>
      <Text style={styles.cardTitle}>Privacidad e IA</Text>
      <Text style={styles.privacyText}>
        Los datos fisiologicos se guardan localmente. Si aceptas colaborar con
        mejoras del servicio, se usan datos anonimizados y sin ubicacion exacta.
      </Text>
      <SettingRow
        label="Usar datos sensibles"
        value={privacy.sensitiveDataConsent ? "Permitido" : "Requiere aceptar"}
        onPress={() => updatePrivacy(getNextSensitivePrivacy(privacy))}
      />
      <SettingRow
        label="Mejorar recomendaciones"
        value={privacy.analyticsTrainingConsent ? "Anonimizado" : "Desactivado"}
        onPress={() => updatePrivacy(getNextAnalyticsPrivacy(privacy))}
      />
      <SettingRow
        label="Terminos y disclaimers"
        value="Ver"
        onPress={() => router.push("/terminos-condiciones")}
      />
    </Card>
  );
}

function AdminAiMetricsCard({ isAdmin }: { isAdmin: boolean }) {
  if (!isAdmin) return null;

  return (
    <Card tone="secondary">
      <Text style={styles.cardTitle}>Metricas IA</Text>
      <Text style={styles.privacyText}>
        Prototipos experimentales con etiquetas derivadas de reglas y variables
        simuladas. Estas métricas describen el conjunto de evaluación; no
        demuestran capacidad para detectar emergencias reales. Falta validar
        con personas y salidas independientes y calibrar las probabilidades.
      </Text>
      {adminAiModelMetrics.map((metrics) => (
        <AiModelMetricBlock key={metrics.dataset.name} metrics={metrics} />
      ))}
    </Card>
  );
}

function AdminTestingCard({
  isAdmin,
  testingLocationMode,
  updateTestingLocationMode,
  wearableRuntime,
}: {
  isAdmin: boolean;
  testingLocationMode: TestingLocationMode;
  updateTestingLocationMode: (enabled: boolean) => void;
  wearableRuntime: WearableRuntimeStatus | null;
}) {
  if (!isAdmin) return null;

  return (
    <Card tone="orange">
      <Text style={styles.cardTitle}>Simular situaciones de ruta</Text>
      <Text style={styles.privacyText}>
        Solo administradores. Al activar este modo, la app usa ubicacion y
        movimiento simulados para probar inicio, mapas y alertas sin estar
        fisicamente en el lugar.
      </Text>
      <SettingRow
        label="Simular ubicacion en ruta"
        value={testingLocationMode.enabled ? "Activa" : "Desactivada"}
        onPress={() => updateTestingLocationMode(!testingLocationMode.enabled)}
      />
      <SettingRow
        label="Laboratorio wearable"
        value={getWearableLabel(wearableRuntime)}
        onPress={() => router.push("/reloj-salud")}
      />
    </Card>
  );
}

function SyncMetric({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.syncMetric}>
      <Text style={styles.syncMetricValue}>{value}</Text>
      <Text style={styles.syncMetricLabel}>{label}</Text>
    </View>
  );
}

function AiModelMetricBlock({ metrics }: { metrics: AiTrainingMetrics }) {
  const test = metrics.metrics.test;
  const cv = metrics.metrics.cross_validation;

  return (
    <View style={styles.aiModelBlock}>
      <View style={styles.aiModelHeader}>
        <View style={styles.aiModelTitleGroup}>
          <Text style={styles.aiModelTitle}>{metrics.dataset.name}</Text>
          <Text style={styles.aiModelMeta}>
            {metrics.dataset.declared_source}
          </Text>
          <Text style={styles.aiModelMeta}>
            {metrics.dataset.rows_total} filas base - {metrics.augmentation.synthetic_rows} sinteticas - {formatDate(metrics.trained_at)}
          </Text>
        </View>
        <Text
          style={[
            styles.aiStatus,
            metrics.guardrails.status === "ok" && styles.aiStatusOk,
            metrics.guardrails.status === "review_recommended" && styles.aiStatusWarning,
          ]}
        >
          {getAiStatusLabel(metrics.guardrails.status)}
        </Text>
      </View>

      <View style={styles.aiMetricGrid}>
        <AiMetric label="Accuracy" value={formatPercent(test.accuracy)} />
        <AiMetric label="Precision" value={formatPercent(test.precision_macro)} />
        <AiMetric label="Recall" value={formatPercent(test.recall_macro)} />
        <AiMetric label="F1 macro" value={formatPercent(test.f1_macro)} />
        <AiMetric
          label="CV F1"
          value={cv ? `${formatPercent(cv.f1_macro_mean)} +/- ${formatPercent(cv.f1_macro_std)}` : "N/D"}
        />
        <AiMetric
          label="Gap F1"
          value={formatPercent(metrics.guardrails.train_test_f1_gap)}
        />
        <AiMetric
          label="Test interno"
          value={`${metrics.dataset.rows_test} filas`}
        />
      </View>

      <Text style={styles.aiWarningText}>
        {metrics.guardrails.warnings[0] || "Evaluación interna; falta validación independiente."}
      </Text>
    </View>
  );
}

function AiMetric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.aiMetric}>
      <Text style={styles.aiMetricValue}>{value}</Text>
      <Text style={styles.aiMetricLabel}>{label}</Text>
    </View>
  );
}

function getAiStatusLabel(status: AiTrainingMetrics["guardrails"]["status"]) {
  if (status === "ok") return "Chequeo interno";
  if (status === "review_recommended") return "Revisar";
  return "Mas datos";
}

function getWearableLabel(runtime: WearableRuntimeStatus | null) {
  if (!runtime) return "Revisar";
  if (runtime.status === "requires_consent") return "Requiere permiso";
  if (runtime.status === "not_linked") return "No vinculado";
  if (runtime.status === "waiting_for_native_data") return "Preparado";
  return "Vinculado";
}

function getExperienceProfileLabel(profile: ExperienceProfile) {
  return profile.completed && profile.level ? profile.level : "Completar";
}

function getNextSensitivePrivacy(privacy: PrivacyPreferences) {
  const sensitiveDataConsent = !privacy.sensitiveDataConsent;

  return {
    sensitiveDataConsent,
    analyticsTrainingConsent: sensitiveDataConsent
      ? privacy.analyticsTrainingConsent
      : false,
  };
}

function getNextAnalyticsPrivacy(privacy: PrivacyPreferences) {
  return {
    sensitiveDataConsent:
      privacy.sensitiveDataConsent || !privacy.analyticsTrainingConsent,
    analyticsTrainingConsent: !privacy.analyticsTrainingConsent,
  };
}

const styles = StyleSheet.create({
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 14,
  },
  profileRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
  },
  profileText: {
    flex: 1,
  },
  avatar: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 999,
    height: 52,
    justifyContent: "center",
    width: 52,
  },
  avatarText: {
    color: colors.primary,
    fontSize: 22,
    fontWeight: "900",
  },
  profileName: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  profileEmail: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 3,
  },
  profileMeta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 3,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
    marginBottom: 2,
  },
  privacyText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
    marginBottom: 6,
  },
  warningText: {
    color: colors.orange,
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 18,
    marginTop: 8,
  },
  syncGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
  },
  syncMetric: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    flexBasis: "47%",
    flexGrow: 1,
    minWidth: 118,
    padding: 10,
  },
  syncMetricValue: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  syncMetricLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
    marginTop: 2,
  },
  aiModelBlock: {
    borderTopColor: colors.line,
    borderTopWidth: 1,
    marginTop: 12,
    paddingTop: 12,
  },
  aiModelHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  aiModelTitleGroup: {
    flex: 1,
    minWidth: 0,
  },
  aiModelTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  aiModelMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    marginTop: 2,
  },
  aiStatus: {
    backgroundColor: colors.orangeSoft,
    borderRadius: 12,
    color: colors.orange,
    fontSize: 11,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  aiStatusOk: {
    backgroundColor: colors.mint,
    color: colors.greenDark,
  },
  aiStatusWarning: {
    backgroundColor: colors.orangeSoft,
    color: colors.orange,
  },
  aiMetricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
  },
  aiMetric: {
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    flexBasis: "30%",
    flexGrow: 1,
    minWidth: 94,
    padding: 9,
  },
  aiMetricValue: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  aiMetricLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: "800",
    marginTop: 2,
  },
  aiWarningText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 17,
    marginTop: 9,
  },
});

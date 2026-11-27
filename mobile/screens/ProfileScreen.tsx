import { useCallback, useEffect, useRef, useState } from "react";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { Alert, ScrollView, StyleSheet, Text, View, TextInput } from "react-native";
import { deleteCurrentAccount } from "../../services/deleteAccount";
import { logoutSession } from "../../services/logoutSession";
import * as Linking from "expo-linking";
import { accountDataPageUrl } from "../../services/api";
import { userMessage } from "../../services/userMessages";
import { isAccountDeletionPending } from "../../services/accountLifecycle";
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
  privacyNotices,
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
import fatigueFieldEvaluation from "../../training/data/field-ai/v1/fatigue/evaluation/metrics.json";
import amsFieldEvaluation from "../../training/data/field-ai/v1/ams/evaluation/metrics.json";
import fieldDelivery from "../../training/data/field-ai/v1/delivery.json";

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
  const { section, returnTo } = useLocalSearchParams<{ section?: string; returnTo?: string }>();
  const showWearableConsent = section === "privacy" && returnTo === "wearable";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showAdminTools, setShowAdminTools] = useState(false);
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
  const [deletePassword, setDeletePassword] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [isSavingPrivacy, setIsSavingPrivacy] = useState(false);
  const privacySaving = useRef(false);
  const confirmDeletion = () => Alert.alert("Eliminar cuenta", "Se eliminarán la cuenta, actividades, reportes, planes y avisos pendientes del servidor. También se borrarán los datos locales de esta cuenta. Requiere conexión y no se puede deshacer. Los mensajes ya enviados a contactos no se pueden retirar.", [
    { text: "Cancelar", style: "cancel" },
    { text: "Eliminar definitivamente", style: "destructive", onPress: async () => {
      setIsDeleting(true);
      try { await deleteCurrentAccount(deletePassword); setDeletePassword(""); router.replace("/"); }
      catch (cause) { setError(`${userMessage(cause, "No se pudo completar la baja.")} Reintentá la baja. Si se perdió la respuesta, los envíos quedan suspendidos hasta confirmar su resultado.`); }
      finally { setIsDeleting(false); }
    } },
  ]);

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
      if (showWearableConsent) {
        // Reading and deciding local consent must not depend on an AWS request.
        const session = await getAuthSession();
        if (!session) { router.replace("/"); return; }
        const preferences = await getPrivacyPreferences();
        setPrivacy(preferences);
        return;
      }
      const data = await loadProfileData();

      if (!data) {
        router.replace("/");
        return;
      }

      runSync()
        .catch(() => null)
        .finally(refreshSyncSummary);

      const current = await getAuthSession();
      if (current?.token !== data.session.token) return;
      if (data.profile.user && !(await isAccountDeletionPending(data.session.user.id))) {
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
  }, [refreshSyncSummary, showWearableConsent]);

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
            try {
              const result = await logoutSession();
              if (!result.remoteRevoked) Alert.alert("Sesión local cerrada", "La revocación remota quedó pendiente. Se reintentará cuando la app tenga conexión.");
            } catch (cause) {
              Alert.alert("Revisá el cierre de sesión", userMessage(cause, "No se pudo completar la limpieza. Reintentá con el equipo desbloqueado."));
            } finally { router.replace("/"); }
          },
        },
      ]
    );
  };

  const updatePrivacy = async (nextPrivacy: Omit<PrivacyPreferences, "updatedAt">) => {
    if (privacySaving.current) return;
    privacySaving.current = true;
    setIsSavingPrivacy(true);
    setError(null);
    try {
      await savePrivacyPreferences(nextPrivacy);
      setPrivacy(await getPrivacyPreferences());
      // A sensor refresh failure must not undo or hide the saved decision.
      setWearableRuntime(await getWearableRuntimeStatus().catch(() => null));
    } catch (cause) { setError(userMessage(cause, "No se pudo guardar la decisión. Intentá nuevamente.")); }
    finally { privacySaving.current = false; setIsSavingPrivacy(false); }
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

  if (showWearableConsent) return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle eyebrow="Reloj y salud" title="Consentimiento del reloj" subtitle="Revisá la autorización y elegí si querés usar las lecturas de tu reloj." />
      <ProfileNotices error={error} isLoading={isLoading} onRetry={loadProfile} />
      <PrivacyCard privacy={privacy} updatePrivacy={updatePrivacy} saving={isSavingPrivacy || isLoading} />
      {privacy.sensitiveDataConsent ? <StatusNotice tone="success" message="Consentimiento activado. Ya podés volver al reloj y autorizar el acceso en Salud o Health Connect." /> : null}
      <PrimaryButton label="Volver al reloj" disabled={isSavingPrivacy} onPress={() => {
        if (router.canGoBack()) router.back();
        else router.replace("/reloj-salud");
      }} />
    </AppScreen>
  );

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
        <PrivacyCard privacy={privacy} updatePrivacy={updatePrivacy} saving={isSavingPrivacy || isLoading} />
        <PrimaryButton label="Fuentes y licencias" tone="secondary" href="/atribuciones" />
        <Card>
          <Text style={styles.cardTitle}>Eliminar mi cuenta</Text>
          <Text style={styles.privacyText}>La baja incluye actividades, reportes, contactos enviados y planes. Los otros dispositivos actualizarán la cuenta cuando vuelvan a conectarse. Revisá también las copias y mensajes que compartiste fuera de MiSendero.</Text>
          <TextInput accessibilityLabel="Contraseña para eliminar la cuenta" placeholder="Tu contraseña actual" secureTextEntry autoCapitalize="none" value={deletePassword} onChangeText={setDeletePassword} />
          <PrimaryButton label="Eliminar cuenta" tone="danger" disabled={!deletePassword} isLoading={isDeleting} onPress={confirmDeletion} />
          <PrimaryButton label="Acceder o actualizar mis datos en la web" tone="secondary" onPress={() => { void Linking.openURL(accountDataPageUrl); }} />
        </Card>
        {isAdmin ? <PrimaryButton label={showAdminTools ? "Ocultar herramientas de administración" : "Herramientas de administración"} tone="secondary" onPress={() => setShowAdminTools(value => !value)} /> : null}
        {showAdminTools ? <>
        <AdminAiMetricsCard isAdmin={isAdmin} />
        <AdminTestingCard
          isAdmin={isAdmin}
          testingLocationMode={testingLocationMode}
          updateTestingLocationMode={updateTestingLocationMode}
          wearableRuntime={wearableRuntime}
        />
        </> : null}
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
        Tus reportes, actividades y pedidos de ayuda se guardan en el teléfono
        y se envían cuando recuperás la conexión.
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
  saving = false,
}: {
  privacy: PrivacyPreferences;
  updatePrivacy: (privacy: Omit<PrivacyPreferences, "updatedAt">) => void;
  saving?: boolean;
}) {
  return (
    <Card>
      <Text style={styles.cardTitle}>Privacidad e IA</Text>
      <Text style={styles.privacyText}>
        Elegí cómo querés usar tus datos. Podés cambiar cada permiso cuando quieras. El análisis de actividad es orientativo y no reemplaza la atención médica.
      </Text>
      <SettingRow
        label="Usar datos sensibles"
        value={saving ? "Guardando..." : privacy.sensitiveDataConsent ? "Permitido" : "Requiere aceptar"}
        onPress={saving ? undefined : () => updatePrivacy(getNextSensitivePrivacy(privacy))}
      />
      <Text style={styles.privacyText}>{privacyNotices.sensitiveDataConsent}</Text>
      <SettingRow
        label="Mejorar recomendaciones"
        value={saving ? "Guardando..." : privacy.analyticsTrainingConsent ? "Autorizado" : "Desactivado"}
        onPress={saving ? undefined : () => updatePrivacy(getNextAnalyticsPrivacy(privacy))}
      />
      <Text style={styles.privacyText}>{privacyNotices.analyticsTrainingConsent}</Text>
      <SettingRow
        label="Términos y condiciones"
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
        Evaluaciones experimentales con datos públicos y etiquetas publicadas
        u observadas. El test contiene datos reales separados por personas,
        parques o regiones. Estas métricas describen cada tarea y población;
        falta validar el uso durante salidas y calibrar las probabilidades.
      </Text>
      <View style={styles.aiModelBlock}>
        <Text style={styles.aiModelTitle}>Prototipo Borg · fatigue-v1</Text>
        <Text style={styles.privacyText}>MAE {fatigueFieldEvaluation.model.mae.toFixed(3)} frente a {fatigueFieldEvaluation.baseline.mae.toFixed(3)} al repetir el Borg previo. Test: {fatigueFieldEvaluation.observations} observaciones, {fatigueFieldEvaluation.people} personas; test histórico reutilizado.</Text>
        <Text style={styles.privacyText}>Mejora de MAE, IC 95 % por participante: {fatigueFieldEvaluation.paired_improvement_95ci.lower.toFixed(3)} a {fatigueFieldEvaluation.paired_improvement_95ci.upper.toFixed(3)}. Entradas dentro del rango: {fieldDelivery.fatigue.within_training_ranges}/{fieldDelivery.fatigue.fixed_test_rows}.</Text>
        <Text style={styles.aiWarningText}>Estimación orientativa con pulso y Borg anterior. No acredita transferencia general a trekking.</Text>
      </View>
      <View style={styles.aiModelBlock}>
        <Text style={styles.aiModelTitle}>Prototipo altura · ams-v1</Text>
        <Text style={styles.privacyText}>Average precision {amsFieldEvaluation.model.average_precision.toFixed(3)} frente a {amsFieldEvaluation.baseline.average_precision.toFixed(3)}. Brier {amsFieldEvaluation.model.brier.toFixed(3)} frente a {amsFieldEvaluation.baseline.brier.toFixed(3)}. Test: {amsFieldEvaluation.observations} observaciones, {amsFieldEvaluation.people} personas; equipos separados.</Text>
        <Text style={styles.privacyText}>Mejora de average precision, IC 95 % por participante: {amsFieldEvaluation.paired_improvement_95ci.lower.toFixed(3)} a {amsFieldEvaluation.paired_improvement_95ci.upper.toFixed(3)}. Entradas dentro del rango: {fieldDelivery.ams.within_training_ranges}/{fieldDelivery.ams.fixed_test_rows}.</Text>
        <Text style={styles.aiWarningText}>Umbral fijado: 18 verdaderos positivos y 121 falsos positivos, sin decisiones negativas. Clasificación binaria deshabilitada; solo puntuación orientativa del control matutino. Sin aprobación clínica ni general de campo.</Text>
      </View>
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
  if (metrics.evaluation_validity?.real_public_ground_truth !== true) {
    return (
      <View style={styles.aiModelBlock}>
        <Text style={styles.aiModelTitle}>{metrics.dataset.name}</Text>
        <Text style={styles.aiStatus}>Evaluación real no disponible</Text>
        <Text style={styles.aiWarningText}>
          {metrics.evaluation_validity?.reason ||
            "Falta verificar la procedencia pública de las mediciones y etiquetas."}
        </Text>
      </View>
    );
  }
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
            {metrics.dataset.source_note}
          </Text>
          <Text style={styles.aiModelMeta}>
            {metrics.dataset.rows_total} filas reales - {metrics.evaluation_validity.synthetic_rows} sinteticas - {formatDate(metrics.trained_at)}
          </Text>
        </View>
        <Text
          style={[
            styles.aiStatus,
            metrics.guardrails.status === "ok" && styles.aiStatusOk,
            metrics.guardrails.status === "review_recommended" && styles.aiStatusWarning,
          ]}
        >
          {metrics.evaluation_validity?.deployment_approved === false
            ? "Evaluación de investigación"
            : getAiStatusLabel(metrics.guardrails.status)}
        </Text>
      </View>

      <View style={styles.aiMetricGrid}>
        <AiMetric label="Accuracy" value={formatPercent(test.accuracy)} />
        <AiMetric label="Precision" value={formatPercent(test.precision_macro)} />
        <AiMetric label="Recall" value={formatPercent(test.recall_macro)} />
        <AiMetric label="F1 macro" value={formatPercent(test.f1_macro)} />
        {metrics.evaluation_details && (
          <>
            <AiMetric label="F1 de referencia" value={formatPercent(metrics.evaluation_details.baseline.f1_macro)} />
            <AiMetric label="Accuracy balanceada" value={formatPercent(metrics.evaluation_details.model.balanced_accuracy)} />
            <AiMetric label="Clases evaluadas" value={`${metrics.evaluation_details.class_coverage.labels_in_test}/${metrics.evaluation_details.class_coverage.labels_total}`} />
          </>
        )}
        {metrics.baseline && (
          <AiMetric
            label="Accuracy de referencia"
            value={formatBaselineAccuracy(metrics.baseline)}
          />
        )}
        {metrics.previous_borg_baseline && (
          <>
            <AiMetric label="Accuracy de Borg previa" value={formatPercent(metrics.previous_borg_baseline.accuracy)} />
            <AiMetric label="F1 de Borg previa" value={formatPercent(metrics.previous_borg_baseline.f1_macro)} />
          </>
        )}
        <AiMetric
          label="CV F1"
          value={cv ? `${formatPercent(cv.f1_macro_mean)} +/- ${formatPercent(cv.f1_macro_std)}` : "N/D"}
        />
        <AiMetric
          label="Gap F1"
          value={formatPercent(metrics.guardrails.train_test_f1_gap)}
        />
        <AiMetric
          label="Test reservado"
          value={metrics.evaluation_protocol
            ? `${metrics.dataset.rows_test} filas / ${metrics.evaluation_protocol.test_groups.length} grupos`
            : `${metrics.dataset.rows_test} filas`}
        />
      </View>

      {metrics.previous_borg_baseline && (
        <Text style={styles.aiWarningText}>
          Requiere Borg previa y contexto de actividad. Benchmark reutilizado; falta evaluación prospectiva independiente.
        </Text>
      )}
      <Text style={styles.aiWarningText}>
        {metrics.guardrails.warnings[0] || "Evaluación interna; falta validación independiente."}
      </Text>
      {metrics.evaluation_details && (
        <Text style={styles.aiWarningText}>
          {metrics.evaluation_details.class_coverage.missing_in_training.length > 0
            ? `Sin ejemplos de entrenamiento: ${metrics.evaluation_details.class_coverage.missing_in_training.join(", ")}. ` : ""}
          {metrics.evaluation_details.class_coverage.missing_in_test.length > 0
            ? `Sin observaciones en test: ${metrics.evaluation_details.class_coverage.missing_in_test.join(", ")}. ` : ""}
          {metrics.evaluation_details.group_support.test < 2
            ? "El test contiene un solo grupo; falta evaluar otros grupos independientes. " : ""}
          Comparación descriptiva con una referencia simple; no acredita validación para uso en campo.
        </Text>
      )}
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

function formatBaselineAccuracy(baseline: NonNullable<AiTrainingMetrics["baseline"]>) {
  const alternatives = Object.values(baseline.tied_labels_test_accuracy || {});
  if (alternatives.length > 1) {
    return `${formatPercent(Math.min(...alternatives))}–${formatPercent(Math.max(...alternatives))} (empate)`;
  }
  return formatPercent(baseline.test_accuracy);
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
  if (runtime.latestSample?.simulated || runtime.connection.provider === "development_simulator") {
    return "Simulador (pruebas)";
  }
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
    analyticsTrainingConsent: privacy.analyticsTrainingConsent,
  };
}

function getNextAnalyticsPrivacy(privacy: PrivacyPreferences) {
  return {
    sensitiveDataConsent: privacy.sensitiveDataConsent,
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
    backgroundColor: colors.soft,
    borderRadius: 12,
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
    backgroundColor: colors.soft,
    borderRadius: 12,
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

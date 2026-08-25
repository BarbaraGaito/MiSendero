import React, { useCallback, useEffect, useState } from "react";
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
import {
  clearAuthSession,
  getAuthSession,
  saveAuthSession,
} from "../../services/authSession";
import { Profile, WearableRuntimeStatus } from "../../types";
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
import {
  discardExhaustedOperations,
  getSyncSummary,
  runSync,
  SyncSummary,
} from "../../services/syncQueue";
import { EmergencyContact } from "../../types";

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

const formatDistance = (meters: number) =>
  `${(meters / 1000).toLocaleString("es-AR", {
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  })} km`;

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
import { getWearableRuntimeStatus } from "../../services/wearableMetrics";

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
      const session = await getAuthSession();

      if (!session) {
        router.replace("/");
        return;
      }

      const data = await getProfile(session.token);
      const [
        privacyPreferences,
        testingPreferences,
        preferences,
        experience,
        contact,
        localSessionsSummary,
        mapsSummary,
        wearable,
        initialSyncSummary,
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

      runSync()
        .catch(() => null)
        .finally(refreshSyncSummary);

      if (data.user) {
        await saveAuthSession({
          token: session.token,
          user: data.user,
        });
      }

      if (data.user?.role !== "admin" && testingPreferences.enabled) {
        await saveTestingLocationMode(false);
      }

      setProfile(data);
      setPrivacy(privacyPreferences);
      setAppPreferences(preferences);
      setExperienceProfile(experience);
      setEmergencyContact(contact);
      setSessionsSummary(localSessionsSummary);
      setOfflineMapsSummary(mapsSummary);
      setWearableRuntime(wearable);
      setSyncSummary(initialSyncSummary);
      setTestingLocationMode(
        data.user?.role === "admin"
          ? await getTestingLocationMode()
          : { enabled: false, updatedAt: null }
      );
    } catch (loadError) {
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
    setPrivacy(await getPrivacyPreferences());
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
            onAction={loadProfile}
            title="No se pudo cargar"
            tone="error"
          />
        ) : null}

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

        <Card>
          <Text style={styles.cardTitle}>Sincronizacion</Text>
          <SettingRow
            label="Pendientes de enviar"
            value={
              syncSummary.pending + syncSummary.syncing > 0
                ? `${syncSummary.pending + syncSummary.syncing}`
                : "Al dia"
            }
            onPress={triggerSync}
          />
          {syncSummary.failed > 0 ? (
            <Text style={styles.warningText}>
              Hay actividades con error. Podes reintentar la sincronizacion.
            </Text>
          ) : null}
          {syncSummary.failed > 0 ? (
            <SettingRow
              label="Con error, reintentar"
              value={`${syncSummary.failed}`}
              onPress={triggerSync}
            />
          ) : null}
          {syncSummary.exhausted > 0 ? (
            <>
              <Text style={styles.warningText}>
                {syncSummary.exhausted} no se pudieron enviar tras varios intentos. Podes
                seguir esperando señal o descartarlos.
              </Text>
              <SettingRow
                label="Descartar pendientes con error"
                value={`${syncSummary.exhausted}`}
                onPress={discardExhausted}
              />
            </>
          ) : null}
          {isSyncing ? <Text style={styles.privacyText}>Sincronizando...</Text> : null}
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Mapas sin conexion</Text>
          <SettingRow
            label="Mapas descargados"
            value={
              offlineMapsSummary.count > 0
                ? `${offlineMapsSummary.count} - ${formatStorage(offlineMapsSummary.totalSizeMb)}`
                : "Sin descargas"
            }
            onPress={() => router.push("/offline-mapas-descargados")}
          />
        </Card>

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

        <Card>
          <Text style={styles.cardTitle}>Preferencias</Text>
          <SettingRow
            label="Perfil de experiencia"
            value={
              experienceProfile.completed && experienceProfile.level
                ? experienceProfile.level
                : "Completar"
            }
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

      <Card>
        <Text style={styles.cardTitle}>Privacidad e IA</Text>
        <Text style={styles.privacyText}>
          Los datos fisiologicos se guardan localmente. Si aceptas colaborar con
          mejoras del servicio, se usan datos anonimizados y sin ubicacion exacta.
        </Text>
          <SettingRow
            label="Usar datos sensibles"
            value={privacy.sensitiveDataConsent ? "Permitido" : "Requiere aceptar"}
            onPress={() => {
              const nextSensitiveConsent = !privacy.sensitiveDataConsent;

              updatePrivacy({
                sensitiveDataConsent: nextSensitiveConsent,
                analyticsTrainingConsent: nextSensitiveConsent
                  ? privacy.analyticsTrainingConsent
                  : false,
              });
            }}
          />
        <SettingRow
          label="Mejorar recomendaciones"
          value={privacy.analyticsTrainingConsent ? "Anonimizado" : "Desactivado"}
            onPress={() =>
              updatePrivacy({
                sensitiveDataConsent:
                  privacy.sensitiveDataConsent || !privacy.analyticsTrainingConsent,
                analyticsTrainingConsent: !privacy.analyticsTrainingConsent,
              })
            }
          />
          <SettingRow
            label="Terminos y disclaimers"
            value="Ver"
            onPress={() => router.push("/terminos-condiciones")}
        />
      </Card>

      {isAdmin ? (
        <Card tone="orange">
          <Text style={styles.cardTitle}>Herramientas de testing</Text>
          <Text style={styles.privacyText}>
            Solo administradores. Simula la ubicacion del dispositivo en el
            inicio de la ruta para probar inicio, mapas y alertas sin estar
            fisicamente en el lugar.
          </Text>
          <SettingRow
            label="Ubicacion simulada"
            value={testingLocationMode.enabled ? "Activa" : "Desactivada"}
            onPress={() =>
              updateTestingLocationMode(!testingLocationMode.enabled)
            }
          />
        </Card>
      ) : null}

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

function getWearableLabel(runtime: WearableRuntimeStatus | null) {
  if (!runtime) return "Revisar";
  if (runtime.status === "requires_consent") return "Requiere permiso";
  if (runtime.status === "not_linked") return "No vinculado";
  if (runtime.status === "waiting_for_native_data") return "Preparado";
  return "Vinculado";
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
});

import React, { useEffect, useState } from "react";
import { router } from "expo-router";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, SettingRow, colors } from "../components/MiSenderoUI";
import { getProfile } from "../../services/api";
import {
  clearAuthSession,
  getAuthSession,
  saveAuthSession,
} from "../../services/authSession";
import { Profile } from "../../types";
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

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const session = await getAuthSession();

        if (!session) {
          router.replace("/");
          return;
        }

        const data = await getProfile(session.token);
        const [privacyPreferences, testingPreferences] = await Promise.all([
          getPrivacyPreferences(),
          getTestingLocationMode(),
        ]);

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
        setTestingLocationMode(
          data.user?.role === "admin"
            ? await getTestingLocationMode()
            : { enabled: false, updatedAt: null }
        );
        setError(null);
      } catch (loadError) {
        setError("No pudimos cargar tu perfil en este momento.");
      } finally {
        setIsLoading(false);
      }
    };

    loadProfile();
  }, []);

  const logout = async () => {
    await clearAuthSession();
    router.replace("/");
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

  const user = profile?.user;
  const displayName = user?.name || "Invitado";
  const email = user?.email || "Inicia sesion para ver tu cuenta";
  const initial = displayName.trim().charAt(0).toUpperCase() || "U";
  const completedRoutes = profile?.stats.completed_routes ?? 0;
  const totalDistance = profile?.stats.total_distance_km ?? 0;
  const isAdmin = user?.role === "admin";

  return (
    <AppScreen activeTab="perfil">
      <ScrollView showsVerticalScrollIndicator={false}>
        <ScreenTitle
          eyebrow="Perfil y ajustes"
          title={displayName}
          subtitle="Tu cuenta y preferencias de seguridad."
        />

        {isLoading ? <Text style={styles.statusText}>Cargando perfil...</Text> : null}
        {error ? <Text style={styles.statusText}>{error}</Text> : null}

        <Card tone="green">
          <View style={styles.profileRow}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{initial}</Text>
            </View>
            <View style={styles.profileText}>
              <Text style={styles.profileName}>{displayName}</Text>
              <Text style={styles.profileEmail}>{email}</Text>
              <Text style={styles.profileMeta}>
                {completedRoutes} rutas completadas - {totalDistance} km
              </Text>
            </View>
          </View>
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Mapas sin conexion</Text>
          <SettingRow
            label="Sendero Laguna Esmeralda"
            value="Actualizado"
            onPress={() => router.push("/offline-mapas-descargados")}
          />
          <SettingRow
            label="Villa La Angostura"
            value="Descargar"
            onPress={() => router.push("/offline-buscar")}
          />
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Seguridad y dispositivos</Text>
          <SettingRow
            label="Contacto de emergencia"
            value="Configurar"
            onPress={() => router.push("/contacto-seguridad")}
          />
          <SettingRow label="Reloj o sensor externo" value="No vinculado" />
          <SettingRow label="Modo ahorro de bateria" value="Activo" />
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Preferencias</Text>
          <SettingRow label="Notificaciones" value="Activadas" />
          <SettingRow label="Unidades" value="Kilometros" />
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
          tone="secondary"
          onPress={logout}
        />
      </ScrollView>
    </AppScreen>
  );
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
});

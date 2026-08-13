import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import React, { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import {
  createDevelopmentMetricSample,
  getRecentWearableMetricSamples,
  getWearableProviderName,
  getWearableRuntimeStatus,
  saveWearableConnection,
  syncNativeWearableSample,
  unlinkWearableConnection,
} from "../../services/wearableMetrics";
import {
  WearableMetricSample,
  WearableProvider,
  WearableRuntimeStatus,
} from "../../types";
import {
  Card,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";

const providerOptions: Array<{
  provider: WearableProvider;
  title: string;
  body: string;
  icon: keyof typeof Ionicons.glyphMap;
}> = [
  {
    provider: "apple_healthkit",
    title: "Apple Watch",
    body: "Usa Salud/HealthKit en iPhone y una extension watchOS para datos en vivo.",
    icon: "watch-outline",
  },
  {
    provider: "android_health_connect",
    title: "Android",
    body: "Lee datos sincronizados desde Health Connect cuando el usuario da permisos.",
    icon: "logo-android",
  },
  {
    provider: "wear_os_health_services",
    title: "Wear OS",
    body: "Obtiene frecuencia cardiaca en vivo desde Health Services en el reloj.",
    icon: "fitness-outline",
  },
  {
    provider: "development_simulator",
    title: "Simulador",
    body: "Genera muestras locales para probar predicciones sin reloj fisico.",
    icon: "flask-outline",
  },
];

export default function WearableSettingsScreen() {
  const [runtime, setRuntime] = useState<WearableRuntimeStatus | null>(null);
  const [samples, setSamples] = useState<WearableMetricSample[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    const [status, recentSamples] = await Promise.all([
      getWearableRuntimeStatus(),
      getRecentWearableMetricSamples(5),
    ]);
    setRuntime(status);
    setSamples(recentSamples);
    setIsLoading(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const connectProvider = async (provider: WearableProvider) => {
    if (runtime?.status === "requires_consent") {
      setMessage("Primero activa el consentimiento de datos sensibles en Privacidad e IA.");
      return;
    }

    await saveWearableConnection(provider, true, true);
    setMessage(`${getWearableProviderName(provider)} preparado.`);
    await load();
  };

  const disconnect = async () => {
    await unlinkWearableConnection();
    setMessage("Reloj o sensor desvinculado para este usuario.");
    await load();
  };

  const simulateSample = async () => {
    if (runtime?.status === "requires_consent") {
      setMessage("Primero activa el consentimiento de datos sensibles en Privacidad e IA.");
      return;
    }

    if (!runtime?.connection.linked) {
      await saveWearableConnection("development_simulator", true, true);
    }

    await createDevelopmentMetricSample();
    setMessage("Muestra local guardada para probar predicciones offline.");
    await load();
  };

  const syncNativeSample = async () => {
    const synced = await syncNativeWearableSample();

    setMessage(
      synced
        ? "Metricas sincronizadas desde el dispositivo."
        : "El puente nativo todavia no esta disponible en esta build."
    );
    await load();
  };

  const latest = runtime?.latestSample ?? null;

  return (
    <ScreenShell>
      <TopBar title="Reloj y salud" onBack={() => router.back()} />

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Card tone={runtime?.status === "requires_consent" ? "orange" : "green"}>
          <View style={styles.statusHeader}>
            <View style={styles.statusIcon}>
              <Ionicons name="pulse-outline" size={24} color={colors.green} />
            </View>
            <View style={styles.statusText}>
              <Text style={styles.cardTitle}>{getStatusTitle(runtime, isLoading)}</Text>
              <Text style={styles.cardText}>{getStatusMessage(runtime)}</Text>
            </View>
          </View>
        </Card>

        {message ? <Text style={styles.message}>{message}</Text> : null}

        <Card>
          <Text style={styles.cardTitle}>Proveedor</Text>
          <Text style={styles.cardText}>
            Elegi la fuente de metricas. Los permisos reales se solicitan en iOS
            con HealthKit y en Android con Health Connect o Wear OS Health Services.
          </Text>

          <View style={styles.providerList}>
            {providerOptions.map((option) => {
              const selected = runtime?.connection.provider === option.provider;
              return (
                <Pressable
                  key={option.provider}
                  style={[styles.providerItem, selected && styles.providerItemSelected]}
                  onPress={() => connectProvider(option.provider)}
                >
                  <Ionicons
                    name={option.icon}
                    size={22}
                    color={selected ? colors.white : colors.green}
                  />
                  <View style={styles.providerText}>
                    <Text style={[styles.providerTitle, selected && styles.providerTitleSelected]}>
                      {option.title}
                    </Text>
                    <Text style={[styles.providerBody, selected && styles.providerBodySelected]}>
                      {option.body}
                    </Text>
                  </View>
                </Pressable>
              );
            })}
          </View>
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Ultima metrica</Text>
          {latest ? (
            <>
              <View style={styles.metricGrid}>
                <MetricBox label="FC" value={`${latest.heartRateBpm ?? "--"} bpm`} />
                <MetricBox label="Velocidad" value={`${latest.speedKmh ?? "--"} km/h`} />
                <MetricBox label="Pasos" value={latest.steps ? String(latest.steps) : "--"} />
                <MetricBox
                  label="Oxigeno"
                  value={
                    latest.oxygenSaturation !== null
                      ? `${latest.oxygenSaturation}%`
                      : "--"
                  }
                />
              </View>
              <Text style={styles.sampleDate}>{formatDate(latest.recordedAt)}</Text>
            </>
          ) : (
            <Text style={styles.cardText}>
              Todavia no hay muestras guardadas para este usuario.
            </Text>
          )}
        </Card>

        {runtime?.prediction ? (
          <Card tone={runtime.prediction.level === "high" ? "red" : runtime.prediction.level === "caution" ? "orange" : "white"}>
            <Text style={styles.cardTitle}>{runtime.prediction.title}</Text>
            <Text style={styles.cardText}>{runtime.prediction.message}</Text>
            <Text style={styles.disclaimer}>
              Prediccion local orientativa. No diagnostica condiciones medicas.
            </Text>
          </Card>
        ) : null}

        <Card>
          <Text style={styles.cardTitle}>Historial local</Text>
          {samples.length > 0 ? (
            <View style={styles.sampleList}>
              {samples.map((sample) => (
                <View key={sample.id} style={styles.sampleRow}>
                  <Text style={styles.sampleMetric}>
                    {sample.heartRateBpm ?? "--"} bpm
                  </Text>
                  <Text style={styles.sampleMeta}>
                    {getWearableProviderName(sample.provider)} - {formatTime(sample.recordedAt)}
                  </Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.cardText}>Sin historial de reloj guardado.</Text>
          )}
        </Card>

        <View style={styles.actions}>
          <PrimaryButton
            label="Sincronizar dispositivo"
            icon="sync-outline"
            tone="secondary"
            onPress={syncNativeSample}
          />
          <PrimaryButton
            label="Generar muestra de prueba"
            icon="flask-outline"
            onPress={simulateSample}
          />
          <PrimaryButton
            label="Desvincular"
            tone="secondary"
            onPress={disconnect}
          />
        </View>
      </ScrollView>
    </ScreenShell>
  );
}

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricBox}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function getStatusTitle(runtime: WearableRuntimeStatus | null, isLoading: boolean) {
  if (isLoading) return "Cargando conexion";
  if (!runtime || runtime.status === "not_linked") return "Sin reloj vinculado";
  if (runtime.status === "requires_consent") return "Consentimiento requerido";
  if (runtime.status === "waiting_for_native_data") return "Esperando metricas";
  return runtime.displayName;
}

function getStatusMessage(runtime: WearableRuntimeStatus | null) {
  if (!runtime) return "Estamos revisando el estado del dispositivo.";
  if (runtime.status === "requires_consent") {
    return "Para usar frecuencia cardiaca y actividad fisica tenes que aceptar el uso de datos sensibles.";
  }
  if (runtime.status === "not_linked") {
    return "Vincula Apple Watch, Android o Wear OS para usar metricas en ruta.";
  }
  if (runtime.status === "waiting_for_native_data") {
    return "La conexion esta preparada. En produccion el modulo nativo escribe aqui las mediciones.";
  }
  return "Metricas disponibles localmente para predicciones sin conexion.";
}

function formatDate(timestamp: number) {
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function formatTime(timestamp: number) {
  return new Intl.DateTimeFormat("es-AR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: 28,
  },
  statusHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
  },
  statusIcon: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 18,
    height: 48,
    justifyContent: "center",
    width: 48,
  },
  statusText: {
    flex: 1,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 21,
    marginTop: 6,
  },
  message: {
    color: colors.greenDark,
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 19,
    marginBottom: 12,
  },
  providerList: {
    gap: 10,
    marginTop: 14,
  },
  providerItem: {
    alignItems: "flex-start",
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    padding: 12,
  },
  providerItemSelected: {
    backgroundColor: colors.green,
    borderColor: colors.green,
  },
  providerText: {
    flex: 1,
  },
  providerTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  providerTitleSelected: {
    color: colors.white,
  },
  providerBody: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 17,
    marginTop: 3,
  },
  providerBodySelected: {
    color: "rgba(255,255,255,0.86)",
  },
  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 12,
  },
  metricBox: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    flexBasis: "47%",
    flexGrow: 1,
    minWidth: 120,
    padding: 12,
  },
  metricLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
  },
  metricValue: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "900",
    marginTop: 4,
  },
  sampleDate: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
    marginTop: 10,
  },
  disclaimer: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 17,
    marginTop: 10,
  },
  sampleList: {
    gap: 8,
    marginTop: 10,
  },
  sampleRow: {
    borderTopColor: colors.line,
    borderTopWidth: 1,
    paddingTop: 10,
  },
  sampleMetric: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  sampleMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    marginTop: 3,
  },
  actions: {
    gap: 10,
  },
});

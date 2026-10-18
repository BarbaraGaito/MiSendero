import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { getAuthSession } from "../../services/authSession";
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import {
  createDevelopmentMetricSample,
  createDevelopmentMetricSequence,
  getRecentWearableMetricSamples,
  getSimulatedWearableMetricSamples,
  getWearableProviderName,
  getWearableRuntimeStatus,
  linkNativeWearable,
  linkNativeWearableProvider,
  syncNativeWearableSampleWithStatus,
  unlinkWearableConnection,
} from "../../services/wearableMetrics";
import {
  WearableMetricSample,
  WearableProvider,
  WearableRuntimeStatus,
  WearableSimulationScenario,
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
    body: "Consultá las lecturas que tu Apple Watch comparte con Salud en el iPhone.",
    icon: "watch-outline",
  },
  {
    provider: "android_health_connect",
    title: "Android",
    body: "Lee metricas sincronizadas desde Health Connect cuando das permisos.",
    icon: "logo-android",
  },
  {
    provider: "wear_os_health_services",
    title: "Wear OS",
    body: "Usa los datos que tu reloj Wear OS publica en Health Connect.",
    icon: "fitness-outline",
  },
  {
    provider: "development_simulator",
    title: "Simulador (pruebas)",
    body: "Genera lecturas simuladas solo en memoria para probar alertas. No se vincula ni se guarda.",
    icon: "flask-outline",
  },
];

const openWearableConsent = () => router.push({ pathname: "/perfil", params: { section: "privacy", returnTo: "wearable" } });

const scenarioOptions: Array<{
  id: WearableSimulationScenario;
  title: string;
  body: string;
  range: string;
  icon: keyof typeof Ionicons.glyphMap;
}> = [
  {
    id: "normal",
    title: "Ritmo normal",
    body: "FC y oxigeno estables, esfuerzo bajo.",
    range: "78-98 bpm - SpO2 97-99%",
    icon: "walk-outline",
  },
  {
    id: "esfuerzo_moderado",
    title: "Esfuerzo moderado",
    body: "FC elevada por pendiente o ritmo sostenido.",
    range: "138-152 bpm - SpO2 94-96%",
    icon: "trending-up-outline",
  },
  {
    id: "fatiga_alta",
    title: "Fatiga alta",
    body: "FC muy elevada y ritmo cayendo por cansancio.",
    range: "160-176 bpm - SpO2 90-93%",
    icon: "battery-dead-outline",
  },
  {
    id: "riesgo_fisiologico",
    title: "Riesgo fisiologico",
    body: "FC critica y oxigeno bajo: dispara alerta inmediata.",
    range: "178-197 bpm - SpO2 82-89%",
    icon: "alert-circle-outline",
  },
];

export default function WearableSettingsScreen() {
  const [runtime, setRuntime] = useState<WearableRuntimeStatus | null>(null);
  const [samples, setSamples] = useState<WearableMetricSample[]>([]);
  const [simulatedSamples, setSimulatedSamples] = useState<WearableMetricSample[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [showTestTools, setShowTestTools] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [scenario, setScenario] = useState<WearableSimulationScenario>("normal");

  const load = useCallback(async () => {
    setIsLoading(true);
    const [status, recentSamples, sessionSamples, session] = await Promise.all([
      getWearableRuntimeStatus(),
      getRecentWearableMetricSamples(5),
      getSimulatedWearableMetricSamples(),
      getAuthSession().catch(() => null),
    ]);
    setRuntime(status);
    setIsAdmin(session?.user.role === "admin");
    setSamples(recentSamples);
    setSimulatedSamples(sessionSamples.slice(0, 5));
    setIsLoading(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const connectProvider = async (provider: WearableProvider) => {
    if (runtime?.status === "requires_consent") {
      openWearableConsent();
      return;
    }

    if (provider === "apple_healthkit") {
      const linked = await linkNativeWearable();
      setMessage(
        linked
          ? "Salud de Apple autorizada. Sincroniza para guardar la primera lectura disponible."
          : "No pudimos vincular Salud de Apple. Revisá los permisos de Salud en tu iPhone e intentá nuevamente."
      );
      await load();
      return;
    }

    if (provider === "android_health_connect" || provider === "wear_os_health_services") {
      const linked = await linkNativeWearableProvider(provider);
      setMessage(
        linked
          ? `${getWearableProviderName(provider)} autorizado. Sincroniza para guardar la primera lectura disponible.`
          : Platform.OS === "android"
            ? "No pudimos vincular Health Connect. Comprobá que esté instalado y que tenga permiso para compartir tus lecturas."
            : "Para vincular este reloj, abrí MiSendero en tu teléfono Android."
      );
      await load();
      return;
    }

    // The simulator is not a linked device: it only generates in-memory readings.
    await simulateSingleSample(scenario);
  };

  const disconnect = async () => {
    await unlinkWearableConnection();
    setMessage("Reloj o sensor desvinculado para este usuario.");
    await load();
  };

  const simulateSample = async () => {
    if (!isAdmin || !showTestTools) return;
    if (runtime?.status === "requires_consent") {
      setMessage("Primero activa el consentimiento de datos sensibles en Privacidad e IA.");
      return;
    }

    setIsSimulating(true);
    try {
      await createDevelopmentMetricSequence(scenario);
      setMessage(
        `Ventana simulada generada (solo en memoria, no se guarda): ${scenarioOptions.find((option) => option.id === scenario)?.title.toLowerCase()}.`
      );
      await load();
    } catch {
      setMessage("No pudimos generar la ventana simulada.");
    } finally {
      setIsSimulating(false);
    }
  };

  const simulateSingleSample = async (nextScenario: WearableSimulationScenario) => {
    if (!isAdmin || !showTestTools) return;
    if (runtime?.status === "requires_consent") {
      setMessage("Primero activa el consentimiento de datos sensibles en Privacidad e IA.");
      return;
    }

    try {
      await createDevelopmentMetricSample(nextScenario);
      setScenario(nextScenario);
      setMessage(
        `Muestra simulada generada (solo en memoria, no se guarda): ${scenarioOptions.find((option) => option.id === nextScenario)?.title.toLowerCase()}.`
      );
      await load();
    } catch {
      setMessage("No pudimos generar la muestra simulada.");
    }
  };

  const syncNativeSample = async () => {
    const status = await syncNativeWearableSampleWithStatus();

    setMessage(getSyncStatusMessage(status, runtime));
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
          {runtime?.status === "requires_consent" ? <PrimaryButton
            label="Revisar consentimiento del reloj"
            icon="shield-checkmark-outline"
            onPress={openWearableConsent}
          /> : null}
        </Card>

        {message ? <Text style={styles.message}>{message}</Text> : null}

        {isAdmin ? <PrimaryButton label={showTestTools ? "Ocultar pruebas del dispositivo" : "Pruebas del dispositivo"} tone="secondary" onPress={() => setShowTestTools(value => !value)} /> : null}
        {isAdmin && showTestTools ? <>
        <Card tone="orange">
          <View style={styles.labHeader}>
            <View style={styles.labIcon}>
              <Ionicons name="flask-outline" size={22} color={colors.orange} />
            </View>
            <View style={styles.providerText}>
              <Text style={styles.cardTitle}>Pruebas con lecturas simuladas</Text>
              <Text style={styles.cardText}>
                Crea una ventana de 8 lecturas simuladas para probar alertas, fatiga y riesgo fisiologico.
                Parten de estos rangos y se intensifican lectura a lectura. Quedan solo en memoria: no se
                guardan ni se sincronizan.
              </Text>
            </View>
          </View>

          <View style={styles.scenarioGrid}>
            {scenarioOptions.map((option) => {
              const selected = scenario === option.id;
              return (
                <Pressable
                  accessibilityRole="button"
                  key={option.id}
                  onPress={() => setScenario(option.id)}
                  style={[styles.scenarioButton, selected && styles.scenarioButtonSelected]}
                >
                  <Ionicons
                    name={option.icon}
                    size={18}
                    color={selected ? colors.white : colors.greenDark}
                  />
                  <Text style={[styles.scenarioTitle, selected && styles.scenarioTitleSelected]}>
                    {option.title}
                  </Text>
                  <Text style={[styles.scenarioRange, selected && styles.scenarioRangeSelected]}>
                    {option.range}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <PrimaryButton
            label="Generar ventana simulada"
            loadingLabel="Simulando ventana"
            icon="analytics-outline"
            isLoading={isSimulating}
            onPress={simulateSample}
          />
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Accesos rapidos</Text>
          <Text style={styles.cardText}>
            Genera una lectura simulada puntual (no se guarda) sin configurar una ventana completa.
          </Text>
          <View style={styles.quickScenarioRow}>
            {scenarioOptions.map((option) => (
              <Pressable
                accessibilityRole="button"
                key={option.id}
                onPress={() => simulateSingleSample(option.id)}
                style={styles.quickScenarioButton}
              >
                <Ionicons name={option.icon} size={17} color={colors.greenDark} />
                <Text style={styles.quickScenarioText}>{option.title}</Text>
              </Pressable>
            ))}
          </View>
        </Card>

        </> : null}
        {runtime?.prediction ? (
          <Card tone={runtime.prediction.level === "high" ? "red" : runtime.prediction.level === "caution" ? "orange" : "white"}>
            <View style={styles.aiHeader}>
              <View style={styles.aiIcon}>
                <Ionicons name="sparkles-outline" size={21} color={colors.green} />
              </View>
              <View style={styles.providerText}>
                <Text style={styles.cardTitle}>
                  {latest?.simulated ? "Resumen de actividad (datos de prueba)" : "Resumen de actividad"}
                </Text>
                <Text style={styles.cardText}>{runtime.prediction.analysisSummary}</Text>
              </View>
            </View>
            <View style={styles.metricGrid}>
              <MetricBox label="Riesgo" value={runtime.prediction.riskLabel === "sin_datos" ? "Sin datos" : runtime.prediction.riskLabel} />
              <MetricBox label="Fatiga" value={runtime.prediction.fatigue === "sin_datos" ? "Sin datos" : runtime.prediction.fatigue} />
              <MetricBox label="Uso" value="Orientativo" />
            </View>
            <Text style={styles.aiAction}>{runtime.prediction.recommendedAction}</Text>
            <View style={styles.factorList}>
              {runtime.prediction.factors.map((factor) => (
                <View key={factor} style={styles.factorPill}>
                  <Ionicons name="checkmark-circle-outline" size={14} color={colors.greenDark} />
                  <Text style={styles.factorText}>{factor}</Text>
                </View>
              ))}
            </View>
            <Text style={styles.disclaimer}>
              Prediccion local orientativa. No diagnostica condiciones medicas.
            </Text>
          </Card>
        ) : null}

        <Card>
          <Text style={styles.cardTitle}>Conectá tu reloj</Text>
          <Text style={styles.cardText}>
            Elegí tu dispositivo y autorizá el acceso a sus lecturas desde Salud o Health Connect.
          </Text>

          <View style={styles.providerList}>
            {providerOptions.filter(option => option.provider !== "development_simulator" || (isAdmin && showTestTools)).map((option) => {
              const selected =
                option.provider === "development_simulator"
                  ? Boolean(latest?.simulated)
                  : runtime?.connection.provider === option.provider;
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
          <Text style={styles.cardTitle}>
            {latest?.simulated ? "Ultima metrica (simulada)" : "Ultima metrica"}
          </Text>
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
              <Text style={styles.sampleDate}>
                {latest.simulated
                  ? `Simulador (pruebas) - ${formatDate(latest.recordedAt)} - no se guarda`
                  : formatDate(latest.recordedAt)}
              </Text>
            </>
          ) : (
            <Text style={styles.cardText}>
              Todavía no hay lecturas. Vinculá tu reloj y tocá Sincronizar dispositivo.
            </Text>
          )}
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Últimas lecturas</Text>
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

        {isAdmin && showTestTools && simulatedSamples.length > 0 ? (
          <Card tone="orange">
            <Text style={styles.cardTitle}>Lecturas simuladas de esta sesion</Text>
            <Text style={styles.cardText}>
              Solo para pruebas: viven en memoria, no se guardan ni forman parte del historial.
            </Text>
            <View style={styles.sampleList}>
              {simulatedSamples.map((sample) => (
                <View key={sample.recordedAt} style={styles.sampleRow}>
                  <Text style={styles.sampleMetric}>
                    {sample.heartRateBpm ?? "--"} bpm
                  </Text>
                  <Text style={styles.sampleMeta}>
                    {getWearableProviderName(sample.provider)} - {formatTime(sample.recordedAt)}
                  </Text>
                </View>
              ))}
            </View>
          </Card>
        ) : null}

        <View style={styles.actions}>
          <PrimaryButton
            label="Sincronizar dispositivo"
            icon="sync-outline"
            tone="secondary"
            onPress={syncNativeSample}
          />
          {isAdmin && showTestTools ? <PrimaryButton
            label="Generar muestra simulada"
            icon="flask-outline"
            onPress={() => simulateSingleSample(scenario)}
          /> : null}
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
    return "La conexion esta autorizada. Sincroniza una lectura disponible desde el reloj o la app de salud.";
  }
  return "Podés consultar tus últimas lecturas también sin conexión.";
}

function getSyncStatusMessage(
  status: Awaited<ReturnType<typeof syncNativeWearableSampleWithStatus>>,
  runtime: WearableRuntimeStatus | null
) {
  if (status === "saved") return "Metricas sincronizadas desde el dispositivo.";
  if (status === "duplicate") return "No hay lecturas nuevas para guardar.";
  if (status === "permission_denied") {
    return "Revisá tu autorización de datos fisiológicos en Perfil y los permisos de Salud o Health Connect.";
  }
  if (status === "not_linked") return "Primero vincula un reloj o app de salud.";
  if (status === "unavailable") {
    return runtime?.connection.provider === "apple_healthkit"
      ? "No pudimos acceder a Salud de Apple. Revisá sus permisos e intentá nuevamente."
      : "No pudimos acceder a las lecturas del reloj. Revisá su conexión con la app de salud e intentá nuevamente.";
  }

  return runtime?.connection.provider === "android_health_connect" ||
    runtime?.connection.provider === "wear_os_health_services"
    ? "Health Connect esta vinculado, pero todavia no hay lecturas nuevas del reloj."
    : "Salud esta vinculada, pero todavia no hay una lectura autorizada disponible.";
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
  labHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    marginBottom: 14,
  },
  labIcon: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 16,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  scenarioGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 9,
    marginBottom: 14,
  },
  scenarioButton: {
    backgroundColor: "rgba(255,255,255,0.74)",
    borderColor: "rgba(217,119,6,0.22)",
    borderRadius: 16,
    borderWidth: 1,
    flexBasis: "47%",
    flexGrow: 1,
    minHeight: 116,
    minWidth: 130,
    padding: 12,
  },
  scenarioButtonSelected: {
    backgroundColor: colors.green,
    borderColor: colors.green,
  },
  scenarioTitle: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
    lineHeight: 17,
    marginTop: 8,
  },
  scenarioTitleSelected: {
    color: colors.white,
  },
  scenarioRange: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
    lineHeight: 15,
    marginTop: 5,
  },
  scenarioRangeSelected: {
    color: "rgba(255,255,255,0.84)",
  },
  quickScenarioRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 12,
  },
  quickScenarioButton: {
    alignItems: "center",
    backgroundColor: colors.primarySoft,
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: "row",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  quickScenarioText: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "900",
  },
  aiHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 10,
  },
  aiIcon: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 16,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  aiAction: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
    lineHeight: 20,
    marginTop: 12,
  },
  factorList: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 7,
    marginTop: 12,
  },
  factorPill: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.72)",
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    paddingHorizontal: 9,
    paddingVertical: 6,
  },
  factorText: {
    color: colors.greenDark,
    fontSize: 11,
    fontWeight: "900",
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

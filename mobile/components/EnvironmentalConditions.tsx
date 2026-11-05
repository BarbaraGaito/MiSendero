import { useEffect, useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import * as Network from "expo-network";
import { InfoCard, colors } from "./MiSenderoUI";
import { getTrailEnvironmental, EnvironmentalContext } from "../../services/environmental";
import { MODEL_TYPES, visibleSnapshots, EnvironmentalSnapshot } from "../../backend/src/contracts/environmental";
import type { Trail } from "../../types";

const titles = { snow: "Cobertura nival", river_level: "Nivel de ríos", fire_detection: "Actividad de fuego" };
const statusLabels = { available: "Predicción vigente", experimental: "Predicción experimental", no_data: "Sin estimación para este sector",
  not_approved: "Estimación inhabilitada", expired: "Información vencida", error: "No se pudo actualizar" };
const time = (value: string | null) => value ? new Date(value).toLocaleString("es-AR") : "";

export function EnvironmentalValue({ snapshot: s }: { snapshot: EnvironmentalSnapshot }) {
  const value = s.prediction;
  if (!value) return null;
  return <View>
    {s.status === "expired" ? <Text style={styles.body}>Última estimación guardada · valor histórico</Text> : null}
    {"level_m" in value ? <>
      <Text style={styles.value}>{value.level_m.toFixed(2)} m · {value.station_name}</Text>
      <Text style={styles.body}>{value.river_name} · horizonte de {value.horizon_hours} horas desde la emisión</Text>
      <Text style={styles.body}>Último nivel observado: {value.latest_level_m.toFixed(2)} m</Text>
      <Text style={styles.body}>Error medio en evaluación: {value.historical_mae_m.toFixed(2)} m. No es un límite garantizado del error.</Text>
    </> : <Text style={styles.value}>{Math.round(value.probability * 100)} % de probabilidad de {s.model_type === "snow" ? "nieve observada" : "detección satelital de fuego"}</Text>}
    <Text style={styles.body}>Predicción para: {time(s.target_at)}</Text>
    <Text style={styles.body}>Observaciones: {time(s.observed_at)}</Text>
    <Text style={styles.body}>Emitida: {time(s.issued_at)} · Vence: {time(s.valid_until)}</Text>
    <Text style={styles.body}>Modelo {s.model_version}</Text>
  </View>;
}

export default function EnvironmentalConditions({ trail, offlineOnly = false }: { trail: Trail; offlineOnly?: boolean }) {
  const [context, setContext] = useState<EnvironmentalContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    let active = true, inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const result = await getTrailEnvironmental(trail, offlineOnly);
        if (active) { setContext(result); setNow(Date.now()); }
      } catch { if (active) setContext({ batch: null, mode: offlineOnly ? "offline" : "cached", error: true }); }
      finally { inFlight = false; if (active) setLoading(false); }
    };
    setContext(null); setLoading(true); void load();
    const subscription = !offlineOnly && typeof Network.addNetworkStateListener === "function"
      ? Network.addNetworkStateListener((state) => { if (state.isConnected && state.isInternetReachable !== false) void load(); }) : null;
    return () => { active = false; subscription?.remove?.(); };
  }, [trail.id, trail.route_coordinates, trail.center_lat, trail.center_lng, offlineOnly]);

  useEffect(() => {
    const deadlines = context?.batch?.snapshots.map((s) => Date.parse(s.valid_until || "")).filter((t) => t > now) || [];
    if (!deadlines.length) return;
    const timer = setTimeout(() => setNow(Date.now()), Math.min(Math.min(...deadlines) - now + 20, 2147483647));
    return () => clearTimeout(timer);
  }, [context, now]);

  const snapshots = context?.batch ? visibleSnapshots(context.batch, now) : [];
  return <InfoCard style={styles.card}>
    <Text style={styles.title}>Condiciones ambientales</Text>
    {loading ? <Text style={styles.body}>Consultando información ambiental…</Text> : null}
    {context?.mode === "offline" ? <Text style={styles.body}>{context.batch ? "Información guardada para consultar sin conexión." : "No guardaste información ambiental de esta ruta."}</Text> : null}
    {context?.error && context.mode !== "offline" ? <Text style={styles.body}>{context.batch ? "No se pudo actualizar. Se muestra la última información guardada." : "No se pudo consultar la información ambiental."}</Text> : null}
    {MODEL_TYPES.map((type) => <View key={type} style={styles.section}>
      <Text style={styles.subtitle}>{titles[type]}</Text>
      {!loading && !snapshots.some((s) => s.model_type === type) ? <Text style={styles.body}>Sin información guardada</Text> : null}
      {snapshots.filter((s) => s.model_type === type).map((s) => <View key={s.model_id || type} style={styles.result}>
        <Text style={styles.status}>{statusLabels[s.status]}</Text>
        <Text style={styles.body}>{s.geographic_scope.description}</Text>
        <EnvironmentalValue snapshot={s} />
        {s.limitations.map((line) => <Text key={line} style={styles.body}>{line}</Text>)}
        <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(s.source.url).catch(() => undefined); }}>
          <Text style={styles.link}>Fuente: {s.source.name}</Text>
        </Pressable>
      </View>)}
    </View>)}
    <Text style={styles.note}>Estas estimaciones no determinan la transitabilidad ni reemplazan avisos o cierres oficiales.</Text>
  </InfoCard>;
}

const styles = StyleSheet.create({
  card: { marginVertical: 12 }, title: { fontSize: 19, fontWeight: "700", color: colors.ink },
  subtitle: { fontSize: 16, fontWeight: "700", color: colors.ink }, status: { fontSize: 13, fontWeight: "600", color: colors.muted },
  section: { marginTop: 16, gap: 5 }, result: { gap: 5 }, body: { fontSize: 13, lineHeight: 19, color: colors.muted },
  value: { fontSize: 16, fontWeight: "600", color: colors.ink }, link: { color: colors.greenDark, fontSize: 13, marginTop: 5 },
  note: { fontSize: 12, lineHeight: 18, color: colors.muted, marginTop: 16 },
});

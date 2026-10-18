import { useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import Svg, { Circle, Line, Polygon, Polyline } from "react-native-svg";
import { Ionicons } from "@expo/vector-icons";
import { TrailElevation } from "../../types";
import { formatKilometers } from "../../services/geoUtils";
import { colors } from "./MiSenderoUI";

export default function ElevationProfile({ elevation, onRetry }: {
  elevation?: TrailElevation | null;
  onRetry: () => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const points = elevation?.points || [];
  const complete = elevation && points.length >= 2;
  if (!complete) {
    return (
      <View style={styles.section}>
        <Text style={styles.title}>Altimetria</Text>
        <Text style={styles.meta}>Perfil no disponible. Conectate para consultar la elevacion de esta ruta.</Text>
        <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retry}>
          <Ionicons name="refresh-outline" size={18} color={colors.green} />
          <Text style={styles.link}>Reintentar</Text>
        </Pressable>
      </View>
    );
  }

  const width = 320;
  const height = 140;
  const padding = 12;
  const range = Math.max(20, elevation.max_m - elevation.min_m);
  const x = (distance: number) => padding + distance / points[points.length - 1].distance_m * (width - padding * 2);
  const y = (altitude: number) => height - padding - (altitude - elevation.min_m) / range * (height - padding * 2);
  const line = points.map((point) => `${x(point.distance_m)},${y(point.elevation_m)}`).join(" ");
  const active = points[Math.min(selected ?? 0, points.length - 1)];

  return (
    <View style={styles.section}>
      <Text style={styles.title}>Altimetria</Text>
      <View style={styles.metrics}>
        <Metric icon="trending-up-outline" label="Subida acumulada" value={`${elevation.ascent_m} m`} />
        <Metric icon="trending-down-outline" label="Bajada acumulada" value={`${elevation.descent_m} m`} />
        <Metric icon="arrow-down-outline" label="Altura minima" value={`${Math.round(elevation.min_m)} m`} />
        <Metric icon="arrow-up-outline" label="Altura maxima" value={`${Math.round(elevation.max_m)} m`} />
      </View>
      <View style={styles.axis}>
        <Text style={styles.meta}>{Math.round(elevation.max_m)} m</Text>
        <Text style={styles.meta}>Sobre el nivel del mar</Text>
      </View>
      <View
        accessibilityLabel={`Perfil de elevacion. Subida ${elevation.ascent_m} metros, bajada ${elevation.descent_m} metros.`}
        accessible
        accessibilityRole="adjustable"
        accessibilityValue={{ min: 0, max: points.length - 1, now: Math.min(selected ?? 0, points.length - 1),
          text: `${formatKilometers(active.distance_m / 1000)}, ${Math.round(active.elevation_m)} metros` }}
        accessibilityActions={[{ name: "increment", label: "Siguiente punto" }, { name: "decrement", label: "Punto anterior" }]}
        onAccessibilityAction={(event) => setSelected(Math.max(0, Math.min(points.length - 1,
          (selected ?? 0) + (event.nativeEvent.actionName === "increment" ? 1 : -1)
        )))}
        style={styles.chart}
      >
        <ProfileChart
          width={width} height={height} padding={padding} line={line}
          activeX={x(active.distance_m)} activeY={y(active.elevation_m)}
          onSelect={(fraction) => setSelected(Math.round(fraction * (points.length - 1)))}
        />
      </View>
      <View style={styles.axis}>
        <Text style={styles.meta}>{Math.round(elevation.min_m)} m</Text>
        <Text style={styles.meta}>{formatKilometers(elevation.distance_m / 1000)} de trazado</Text>
      </View>
      <Text accessibilityLiveRegion="polite" style={styles.readout}>
        {formatKilometers(active.distance_m / 1000)} - {Math.round(active.elevation_m)} m
      </Text>
      <Text style={styles.meta}>Las alturas y el desnivel son aproximados.</Text>
      <Pressable accessibilityRole="link" onPress={() => Linking.openURL(elevation.source_url)} style={styles.source}>
        <Text style={styles.link}>{elevation.source}</Text>
        <Ionicons name="open-outline" size={14} color={colors.green} />
      </Pressable>
    </View>
  );
}

function ProfileChart({ width, height, padding, line, activeX, activeY, onSelect }: {
  width: number; height: number; padding: number; line: string;
  activeX: number; activeY: number; onSelect: (fraction: number) => void;
}) {
  const [layoutWidth, setLayoutWidth] = useState(width);
  const select = (locationX: number) => onSelect(Math.max(0, Math.min(1,
    (locationX / layoutWidth * width - padding) / (width - padding * 2)
  )));
  return (
    <View style={styles.chartSurface} onLayout={(event) => setLayoutWidth(event.nativeEvent.layout.width)}
      onStartShouldSetResponder={() => true} onMoveShouldSetResponder={() => true}
      onResponderGrant={(event) => select(event.nativeEvent.locationX)}
      onResponderMove={(event) => select(event.nativeEvent.locationX)}>
      <Svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" pointerEvents="none">
        {[0, 0.5, 1].map((fraction) => (
          <Line key={fraction} x1={padding} x2={width - padding}
            y1={padding + fraction * (height - padding * 2)} y2={padding + fraction * (height - padding * 2)}
            stroke={colors.line} />
        ))}
        <Polygon points={`${padding},${height - padding} ${line} ${width - padding},${height - padding}`} fill={colors.mint} />
        <Polyline points={line} fill="none" stroke={colors.green} strokeWidth={2} />
        <Line x1={activeX} x2={activeX} y1={padding} y2={height - padding} stroke={colors.muted} strokeDasharray="3 3" />
        <Circle cx={activeX} cy={activeY} r={4} fill={colors.greenDark} stroke={colors.white} strokeWidth={2} />
      </Svg>
    </View>
  );
}

function Metric({ icon, label, value }: {
  icon: "trending-up-outline" | "trending-down-outline" | "arrow-up-outline" | "arrow-down-outline";
  label: string; value: string;
}) {
  return (
    <View style={styles.metric}>
      <View style={styles.metricValue}><Ionicons name={icon} size={18} color={colors.green} /><Text style={styles.value}>{value}</Text></View>
      <Text style={styles.meta}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { marginTop: 22, paddingVertical: 18, borderTopWidth: 1, borderBottomWidth: 1, borderColor: colors.line },
  title: { fontSize: 18, fontWeight: "900", color: colors.ink, marginBottom: 14 },
  metrics: { flexDirection: "row", flexWrap: "wrap", rowGap: 16, marginBottom: 16 },
  metric: { width: "50%", paddingRight: 8 },
  metricValue: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 4 },
  value: { fontSize: 20, fontWeight: "800", color: colors.ink },
  meta: { fontSize: 12, lineHeight: 18, color: colors.muted, flexShrink: 1 },
  axis: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  chart: { height: 150, width: "100%" },
  chartSurface: { width: "100%", height: "100%" },
  readout: { fontSize: 14, fontWeight: "700", color: colors.ink, marginVertical: 12, minHeight: 20 },
  link: { fontSize: 12, lineHeight: 18, color: colors.green, flexShrink: 1 },
  source: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8 },
  retry: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 12, alignSelf: "flex-start" },
});

import { useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { Card, PrimaryButton, colors, typography } from "./MiSenderoUI";
import { ExpandableSection } from "./ExpandableSection";
import { TrailMetrics } from "./TrailMetrics";
import type { TrailRecommendation } from "../../services/trailAssistant";

export function TrailRecommendationCard({ trail, onRestart }: { trail: TrailRecommendation; onRestart: () => void }) {
  const [imageFailed, setImageFailed] = useState(false);
  const difficulty = { facil: "Fácil", moderada: "Moderada", dificil: "Difícil" }[trail.difficulty];
  const durationScope = trail.durationMinutes === null ? "La fuente no publica el tiempo total."
    : trail.durationScopeVerified === false ? "Tiempo de referencia: confirmar si incluye el regreso."
    : trail.routeType === "out_and_back" ? "Tiempo estimado de ida y vuelta."
    : trail.routeType === "loop" ? "Tiempo estimado del circuito completo."
    : trail.routeType === "point_to_point" ? "Tiempo estimado de solo ida." : "Tiempo estimado del recorrido.";
  return <Card style={styles.card}>
    {trail.imageUrl && !imageFailed ? <Image accessibilityLabel={`Paisaje de ${trail.name}`} source={{ uri: trail.imageUrl }} style={styles.image} onError={() => setImageFailed(true)} /> : null}
    <View style={styles.badge}><Ionicons name={trail.exceedsExperience ? "warning-outline" : "compass-outline"} size={15} color={trail.exceedsExperience ? colors.warning : colors.greenDark} /><Text style={[styles.badgeText, trail.exceedsExperience && styles.outsideProfile]}>{trail.exceedsExperience ? "SUPERA TU NIVEL" : trail.preferenceAdjustments?.length ? "ALTERNATIVA EN EL DESTINO" : "TU PRÓXIMA CAMINATA"}</Text></View>
    <Text accessibilityRole="header" style={styles.title}>{trail.name}</Text>
    <View style={styles.locationRow}><Ionicons name="location-outline" size={16} color={colors.muted} /><Text style={styles.location}>{trail.location}</Text></View>
    <TrailMetrics items={[
      { label: "Distancia", value: `${trail.distanceKm.toLocaleString("es-AR", { maximumFractionDigits: 1 })} km`, icon: "walk-outline" },
      { label: "Duración", value: trail.duration, icon: "time-outline" },
      { label: "Dificultad", value: difficulty, icon: "trail-sign-outline" },
    ]} />
    <Text style={styles.note}>{durationScope}</Text>
    {trail.preferenceAdjustments?.length ? <View accessibilityRole="alert" style={styles.alternative}>
      <Text style={styles.subtitle}>{trail.exceedsExperience ? "Esta ficha es solo para consultar" : "Te sugerimos una alternativa en este destino"}</Text>
      {!trail.exceedsExperience && <Text style={styles.body}>No encontramos un sendero que coincida con todo lo que elegiste.</Text>}
      {trail.preferenceAdjustments.map((adjustment) => <Text key={adjustment} style={styles.body}>• {adjustment}</Text>)}
    </View> : null}
    {trail.routeType === "point_to_point" || trail.dataWarnings?.length ? <View style={styles.warning}>
      <Ionicons name="information-circle-outline" size={19} color={colors.warning} />
      <View style={styles.warningText}>
        {trail.routeType === "point_to_point" ? <Text style={styles.note}>El recorrido termina en otro punto. Coordiná el transporte de regreso.</Text> : null}
        {trail.dataWarnings?.map(warning => <Text key={warning} style={styles.note}>{warning}</Text>)}
      </View>
    </View> : null}
    <PrimaryButton label={trail.exceedsExperience ? "Ver ficha" : "Ver sendero"} icon="trail-sign-outline" onPress={() => router.push({ pathname: "/trail-detail", params: { id: String(trail.trailId) } })} />
    <View style={styles.details}>
      <ExpandableSection title="¿Por qué este sendero?" icon="sparkles-outline" tone="info">
        <Text style={styles.body}>{trail.explanation}</Text>
      </ExpandableSection>
      <ExpandableSection title="Sobre el recorrido" summary={trail.trailTypes.join(" · ")} icon="leaf-outline">
        <Text style={styles.body}>{trail.description}</Text>
      </ExpandableSection>
      <ExpandableSection title="Datos del recorrido" summary="Desnivel y revisión del catálogo" icon="information-circle-outline">
        <Text style={styles.body}>{trail.ascentM == null ? "Desnivel de ascenso: no documentado" : `Desnivel de ascenso estimado: ${trail.ascentM.toLocaleString("es-AR")} m`}</Text>
        {trail.ascentM != null ? <Text style={styles.note}>Estimación del modelo de elevación sobre la traza disponible; no es una medición de campo.</Text> : null}
        {trail.checkedAt ? <Text style={styles.note}>Datos del catálogo revisados el {trail.checkedAt.split("-").reverse().join("/")}.</Text> : null}
      </ExpandableSection>
    </View>
    <Text style={styles.note}>Consultá el estado y la habilitación antes de salir.</Text>
    <Pressable accessibilityRole="button" accessibilityLabel="Buscar otro sendero" onPress={onRestart} style={({ pressed }) => [styles.restart, pressed && styles.pressed]}>
      <Ionicons name="refresh-outline" size={17} color={colors.greenDark} /><Text style={styles.restartText}>Buscar otro sendero</Text>
    </Pressable>
  </Card>;
}
const styles = StyleSheet.create({
  card: { padding: 20 },
  image: { width: "100%", height: 190, borderRadius: 18, marginBottom: 18 },
  badge: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 10 },
  badgeText: { fontFamily: typography.medium, color: colors.greenDark, fontSize: 11, letterSpacing: 1 },
  outsideProfile: { color: colors.warning },
  title: { fontFamily: typography.extraBold, fontSize: 26, lineHeight: 32, color: colors.ink },
  subtitle: { fontFamily: typography.bold, fontSize: 16, lineHeight: 22, color: colors.greenDark },
  locationRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 8 },
  location: { fontFamily: typography.regular, color: colors.muted, fontSize: 14, lineHeight: 20, flex: 1 },
  body: { fontFamily: typography.regular, fontSize: 15, lineHeight: 23, color: colors.ink },
  alternative: { backgroundColor: colors.orangeSoft, borderRadius: 14, padding: 14, marginBottom: 16, gap: 8 },
  note: { fontFamily: typography.regular, color: colors.muted, fontSize: 13, lineHeight: 20, marginBottom: 12 },
  warning: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginBottom: 4 },
  warningText: { flex: 1 },
  details: { marginTop: 20, marginBottom: 12, gap: 4 },
  restart: { minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
  restartText: { fontFamily: typography.medium, fontSize: 14, color: colors.greenDark },
  pressed: { opacity: 0.72 },
});

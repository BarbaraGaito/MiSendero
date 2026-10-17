import { useState } from "react";
import { Image, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { Card, PrimaryButton, colors } from "./MiSenderoUI";
import type { TrailRecommendation } from "../../services/trailAssistant";

export function TrailRecommendationCard({ trail, onRestart }: { trail: TrailRecommendation; onRestart: () => void }) {
  const [imageFailed, setImageFailed] = useState(false);
  const difficulty = { facil: "Fácil", moderada: "Moderada", dificil: "Difícil" }[trail.difficulty];
  return <Card>
    {trail.imageUrl && !imageFailed ? <Image accessibilityLabel={`Paisaje de ${trail.name}`} source={{ uri: trail.imageUrl }} style={styles.image} onError={() => setImageFailed(true)} /> : null}
    <Text style={styles.title}>{trail.name}</Text>
    <Text style={styles.location}>📍 {trail.location}</Text>
    <View style={styles.metrics}>
      <Text style={styles.body}>🌿 {trail.trailTypes.join(" · ")}</Text>
      <Text style={styles.body}>🥾 Dificultad: {difficulty}</Text>
      <Text style={styles.body}>⏱️ Aproximadamente {trail.duration} {trail.routeType === "out_and_back" ? "(ida y vuelta)" : trail.routeType === "loop" ? "(circuito completo)" : "(solo ida)"}</Text>
      <Text style={styles.body}>📏 Aproximadamente {trail.distanceKm.toLocaleString("es-AR", { maximumFractionDigits: 1 })} km</Text>
    </View>
    {trail.routeType === "point_to_point" ? <Text style={styles.note}>El recorrido termina en otro punto. Coordiná el transporte de regreso.</Text> : null}
    <Text style={styles.body}>{trail.description}</Text>
    <View style={styles.reason}>
      <Text style={styles.subtitle}>¿Por qué te recomendamos este sendero?</Text>
      <Text style={styles.body}>{trail.explanation}</Text>
    </View>
    <Text style={styles.note}>Datos del catálogo verificados el {trail.checkedAt.split("-").reverse().join("/")}. Consultá el estado y la habilitación antes de salir.</Text>
    <PrimaryButton label="Ver sendero" icon="trail-sign-outline" onPress={() => router.push({ pathname: "/trail-detail", params: { id: String(trail.trailId) } })} />
    <View style={styles.spacer} />
    <PrimaryButton label="Buscar otro sendero" tone="secondary" onPress={onRestart} />
  </Card>;
}
const styles = StyleSheet.create({
  image: { width: "100%", height: 190, borderRadius: 18, marginBottom: 18 },
  title: { fontFamily: "BricolageGrotesque_800ExtraBold", fontSize: 26, color: colors.ink },
  subtitle: { fontFamily: "BricolageGrotesque_700Bold", fontSize: 18, color: colors.greenDark, marginBottom: 8 },
  location: { color: colors.muted, fontSize: 15, marginTop: 6 },
  metrics: { gap: 8, marginVertical: 18 }, body: { fontSize: 15, lineHeight: 23, color: colors.ink },
  reason: { backgroundColor: colors.mint, borderRadius: 18, padding: 16, marginVertical: 18 },
  note: { color: colors.muted, fontSize: 12, lineHeight: 19, marginBottom: 16 }, spacer: { height: 10 },
});

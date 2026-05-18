import { Link } from "expo-router";
import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import WatchScreen from "../../watch/WatchScreen";
import StatsCard from "../components/StatsCard";
import { useTracking } from "../hooks/useTracking";

const formatDistance = (meters: number) => `${(meters / 1000).toFixed(2)} km`;

export default function HomeScreen() {
  const tracking = useTracking();

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.hero}>
        <Text style={styles.kicker}>Wearable-first trekking</Text>
        <Text style={styles.title}>Tu ruta, aun sin conexión</Text>
        <Text style={styles.subtitle}>
          El reloj captura señales. El celular procesa, guarda y responde localmente.
        </Text>
      </View>

      <WatchScreen
        hr={tracking.hr}
        fatigue={tracking.fatigue}
        elapsedSeconds={tracking.elapsedSeconds}
        inactiveTooLong={tracking.inactiveTooLong}
        isActive={tracking.isActive}
        onStart={tracking.startSession}
        onStop={tracking.stopSession}
      />

      <View style={styles.grid}>
        <StatsCard title="Distancia" value={formatDistance(tracking.distanceMeters)} />
        <StatsCard title="Velocidad" value={`${tracking.speedKmh.toFixed(1)} km/h`} />
      </View>

      <View style={styles.infoCard}>
        <Text style={styles.infoTitle}>Estado del sistema</Text>
        <Text style={styles.infoText}>• Bluetooth simulado activo cada 5 segundos</Text>
        <Text style={styles.infoText}>• SQLite local para sesiones y frecuencia cardíaca</Text>
        <Text style={styles.infoText}>• IA simple calculada en el celular, sin APIs externas</Text>
      </View>

      <Link href="/history" style={styles.historyLink}>
        Ver historial de sesiones
      </Link>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#0B110E",
    padding: 20,
    paddingTop: 28,
    gap: 16,
  },
  hero: { gap: 6 },
  kicker: { color: "#64D38C", fontWeight: "700", textTransform: "uppercase", fontSize: 12 },
  title: { color: "#F6FFF8", fontSize: 28, fontWeight: "800" },
  subtitle: { color: "#A7B8AE", lineHeight: 20 },
  grid: { flexDirection: "row", gap: 12 },
  infoCard: {
    backgroundColor: "#121A16",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#223128",
    padding: 16,
    gap: 6,
  },
  infoTitle: { color: "#F6FFF8", fontWeight: "700", fontSize: 16, marginBottom: 4 },
  infoText: { color: "#A7B8AE" },
  historyLink: {
    color: "#0B110E",
    backgroundColor: "#C8F0D5",
    paddingVertical: 14,
    textAlign: "center",
    borderRadius: 18,
    fontWeight: "700",
    overflow: "hidden",
    marginBottom: 16,
  },
});

import { useEffect, useState } from "react";
import { router } from "expo-router";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import {
  BottomNav,
  InfoCard,
  ScreenShell,
  TopBar,
  TrailCard,
  colors,
  trailImages,
} from "../components/MiSenderoUI";
import { getTrails } from "../../services/trailRepository";
import { Trail } from "../../types";

export default function Screen02Explore() {
  const [trails, setTrails] = useState<Trail[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTrails()
      .then((data) => {
        setTrails(data.slice(0, 2));
        setError(null);
      })
      .catch(() => {
        setError("No pudimos cargar los senderos en este momento.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  return (
    <ScreenShell footer={<BottomNav active="explorar" />}>
      <TopBar title="Explorar senderos" subtitle="Elegi una ruta cerca tuyo" />

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        <InfoCard style={styles.hero}>
          <Text style={styles.eyebrow}>RECOMENDADO PARA HOY</Text>
          <Text style={styles.heroTitle}>Respira aire libre en tu proximo sendero</Text>
          <Text style={styles.heroText}>
            Rutas verificadas, nivel de dificultad y datos clave antes de salir.
          </Text>
        </InfoCard>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Cerca de vos</Text>
          <Text
            style={styles.sectionLink}
            onPress={() => router.push("/explorar-rutas")}
          >
            Ver todos
          </Text>
        </View>

        {isLoading ? <Text style={styles.statusText}>Cargando senderos...</Text> : null}
        {error ? <Text style={styles.statusText}>{error}</Text> : null}

        {trails.map((trail, index) => (
          <TrailCard
            key={trail.id}
            title={trail.name}
            location={trail.location}
            image={trail.image_url || (index % 2 === 0 ? trailImages.mountain : trailImages.lake)}
            difficulty={trail.difficulty}
            distance={trail.distance_km ? `${trail.distance_km} km` : "Distancia a confirmar"}
            duration={trail.duration || "Duracion a confirmar"}
            onPress={() =>
              router.push({
                pathname: "/trail-detail",
                params: { id: String(trail.id) },
              })
            }
          />
        ))}
      </ScrollView>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: 118,
  },
  hero: {
    backgroundColor: colors.mint,
    marginBottom: 22,
  },
  eyebrow: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "900",
    letterSpacing: 0,
    marginBottom: 10,
  },
  heroTitle: {
    color: colors.ink,
    fontSize: 28,
    fontWeight: "900",
    lineHeight: 34,
  },
  heroText: {
    color: colors.muted,
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
  },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 20,
    fontWeight: "900",
  },
  sectionLink: {
    color: colors.green,
    fontSize: 14,
    fontWeight: "800",
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 14,
  },
});

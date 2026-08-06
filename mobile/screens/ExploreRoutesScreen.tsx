import { router } from "expo-router";
import React, { useEffect, useState } from "react";
import { ImageBackground, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, ScreenTitle, colors, trailImages } from "../components/MiSenderoUI";
import { getTrails } from "../../services/api";
import { Trail } from "../../types";

export default function ExploreRoutesScreen() {
  const [trails, setTrails] = useState<Trail[]>([]);
  const [activeFilter, setActiveFilter] = useState("Todas");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filters = ["Todas", "Baja", "Media", "Alta"];
  const filteredTrails =
    activeFilter === "Todas"
      ? trails
      : trails.filter((trail) =>
          trail.difficulty.toLowerCase().includes(activeFilter.toLowerCase())
        );

  useEffect(() => {
    getTrails()
      .then((data) => {
        setTrails(data);
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
    <AppScreen activeTab="explorar">
      <ScreenTitle
        eyebrow="Explorar rutas"
        title="Encontra tu proxima ruta"
        subtitle="Filtra por dificultad, distancia y disponibilidad."
      />

      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.filterRow}>
          {filters.map((filter) => {
            const isActive = activeFilter === filter;

            return (
              <Pressable key={filter} onPress={() => setActiveFilter(filter)}>
                <Text style={isActive ? styles.filterActive : styles.filter}>
                  {filter}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text style={styles.sectionTitle}>Senderos disponibles</Text>

        {isLoading ? <Text style={styles.statusText}>Cargando senderos...</Text> : null}
        {error ? <Text style={styles.statusText}>{error}</Text> : null}
        {!isLoading && !error && filteredTrails.length === 0 ? (
          <Text style={styles.statusText}>No hay senderos disponibles por ahora.</Text>
        ) : null}

        {filteredTrails.map((trail, index) => (
          <RouteCard
            key={trail.id}
            trail={trail}
            image={trail.image_url || (index % 2 === 0 ? trailImages.mountain : trailImages.forest)}
          />
        ))}

        <Card tone="green">
          <Text style={styles.cardTitle}>Tip de seguridad</Text>
          <Text style={styles.cardText}>Descarga el mapa antes de salir si la zona tiene poca senal.</Text>
        </Card>
      </ScrollView>
    </AppScreen>
  );
}

function RouteCard({ trail, image }: { trail: Trail; image: string }) {
  const distance = trail.distance_km ? `${trail.distance_km} km` : "Distancia a confirmar";

  return (
    <Pressable
      style={styles.routeCard}
      onPress={() =>
        router.push({
          pathname: "/trail-detail",
          params: { id: String(trail.id) },
        })
      }
    >
      <ImageBackground source={{ uri: image }} imageStyle={styles.image} style={styles.imageBox}>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{trail.difficulty}</Text>
        </View>
      </ImageBackground>
      <View style={styles.routeBody}>
        <Text style={styles.routeTitle}>{trail.name}</Text>
        <Text style={styles.routePlace}>{trail.location}</Text>
        <Text style={styles.routeMeta}>
          {distance} - {trail.duration || "Duracion a confirmar"}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  filterRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 18,
  },
  filter: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  filterActive: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    color: colors.surface,
    fontSize: 13,
    fontWeight: "800",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
    marginBottom: 12,
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 14,
  },
  routeCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 22,
    borderWidth: 1,
    marginBottom: 14,
    overflow: "hidden",
  },
  imageBox: {
    height: 126,
    padding: 12,
  },
  image: {
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
  },
  badge: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.9)",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  badgeText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
  },
  routeBody: {
    gap: 3,
    padding: 14,
  },
  routeTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  routePlace: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "500",
  },
  routeMeta: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
    marginTop: 6,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
});

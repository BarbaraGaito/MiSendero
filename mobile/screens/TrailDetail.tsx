import React, { useEffect, useState } from "react";
import { router, useLocalSearchParams } from "expo-router";
import { ImageBackground, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  StatPill,
  TopBar,
  colors,
  trailImages,
} from "../components/MiSenderoUI";
import { getTrailById } from "../../services/api";
import { Trail } from "../../types";

export default function Screen03TrailDetail() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const [trail, setTrail] = useState<Trail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const trailId = Number(id);

    if (!trailId) {
      setError("No se encontro el sendero seleccionado.");
      setIsLoading(false);
      return;
    }

    getTrailById(trailId)
      .then((data) => {
        setTrail(data);
        setError(null);
      })
      .catch(() => {
        setError("No pudimos cargar este sendero en este momento.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [id]);

  const distance = trail?.distance_km ? `${trail.distance_km} km` : "Distancia a confirmar";
  const duration = trail?.duration || "Duracion a confirmar";

  return (
    <ScreenShell>
      <TopBar title="Detalle del sendero" onBack={() => router.back()} />

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        {isLoading ? <Text style={styles.statusText}>Cargando sendero...</Text> : null}
        {error ? <Text style={styles.statusText}>{error}</Text> : null}

        {trail ? (
          <>
            <ImageBackground
              source={{ uri: trail.image_url || trailImages.mountain }}
              style={styles.cover}
              imageStyle={styles.coverImage}
            >
              <View style={styles.coverBadge}>
                <Ionicons name="star" size={15} color={colors.warning} />
                <Text style={styles.coverBadgeText}>4.8</Text>
              </View>
            </ImageBackground>

            <Text style={styles.title}>{trail.name}</Text>
            <Text style={styles.location}>{trail.location}</Text>

            <View style={styles.stats}>
              <StatPill icon="walk-outline" label={distance} />
              <StatPill icon="time-outline" label={duration} />
              <StatPill icon="leaf-outline" label={trail.difficulty} />
            </View>

            <InfoCard style={styles.card}>
              <Text style={styles.cardTitle}>Descripcion</Text>
              <Text style={styles.body}>
                {trail.description || "Pronto vas a encontrar mas informacion sobre este recorrido."}
              </Text>
            </InfoCard>

            <InfoCard style={styles.card}>
              <Text style={styles.cardTitle}>Antes de salir</Text>
              <View style={styles.checkRow}>
                <Ionicons name="checkmark-circle" size={20} color={colors.green} />
                <Text style={styles.checkText}>Lleva agua, abrigo y calzado apto para trekking.</Text>
              </View>
              <View style={styles.checkRow}>
                <Ionicons name="checkmark-circle" size={20} color={colors.green} />
                <Text style={styles.checkText}>Consulta el estado del sendero antes de iniciar la actividad.</Text>
              </View>
            </InfoCard>
          </>
        ) : null}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: Math.max(20, insets.bottom + 14) }]}>
        <PrimaryButton
          label="Ver ruta"
          icon="map-outline"
          href="/descargar-mapa"
        />
      </View>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: 108,
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 14,
  },
  cover: {
    height: 230,
    justifyContent: "flex-start",
    marginBottom: 22,
    padding: 16,
  },
  coverImage: {
    borderRadius: 28,
  },
  coverBadge: {
    alignItems: "center",
    alignSelf: "flex-end",
    backgroundColor: colors.white,
    borderRadius: 17,
    flexDirection: "row",
    gap: 5,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },
  coverBadgeText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  title: {
    color: colors.ink,
    fontSize: 30,
    fontWeight: "900",
    lineHeight: 36,
  },
  location: {
    color: colors.muted,
    fontSize: 15,
    marginTop: 6,
  },
  stats: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 9,
    marginTop: 18,
  },
  card: {
    marginTop: 16,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
    marginBottom: 10,
  },
  body: {
    color: colors.muted,
    fontSize: 15,
    lineHeight: 23,
  },
  checkRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 9,
    marginTop: 9,
  },
  checkText: {
    color: colors.muted,
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    backgroundColor: colors.softer,
    bottom: 0,
    left: 0,
    padding: 22,
    paddingBottom: 28,
    position: "absolute",
    right: 0,
  },
});

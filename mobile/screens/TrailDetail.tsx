import React from "react";
import { router } from "expo-router";
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

export default function Screen03TrailDetail() {
  const insets = useSafeAreaInsets();

  return (
    <ScreenShell>
      <TopBar title="Detalle del sendero" onBack={() => router.back()} />

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        <ImageBackground
          source={{ uri: trailImages.mountain }}
          style={styles.cover}
          imageStyle={styles.coverImage}
        >
          <View style={styles.coverBadge}>
            <Ionicons name="star" size={15} color={colors.warning} />
            <Text style={styles.coverBadgeText}>4.8</Text>
          </View>
        </ImageBackground>

        <Text style={styles.title}>Sendero del Bosque</Text>
        <Text style={styles.location}>Reserva Natural - Circuito Norte</Text>

        <View style={styles.stats}>
          <StatPill icon="walk-outline" label="4,2 km" />
          <StatPill icon="time-outline" label="1h 35m" />
          <StatPill icon="trending-up-outline" label="120 m" />
          <StatPill icon="leaf-outline" label="Fácil" />
        </View>

        <InfoCard style={styles.card}>
          <Text style={styles.cardTitle}>Descripción</Text>
          <Text style={styles.body}>
            Recorrido tranquilo entre árboles nativos, miradores bajos y zonas de descanso.
            Ideal para salir por la mañana y volver antes del mediodía.
          </Text>
        </InfoCard>

        <InfoCard style={styles.card}>
          <Text style={styles.cardTitle}>Antes de salir</Text>
          <View style={styles.checkRow}>
            <Ionicons name="checkmark-circle" size={20} color={colors.green} />
            <Text style={styles.checkText}>Llevá agua, gorra y calzado con agarre.</Text>
          </View>
          <View style={styles.checkRow}>
            <Ionicons name="checkmark-circle" size={20} color={colors.green} />
            <Text style={styles.checkText}>Descargá el mapa por si perdés señal.</Text>
          </View>
        </InfoCard>
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

import React from "react";
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

export default function Screen02Explore() {
  return (
    <ScreenShell footer={<BottomNav active="explorar" />}>
      <TopBar title="Explorar senderos" subtitle="Elegí una ruta cerca tuyo" />

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        <InfoCard style={styles.hero}>
          <Text style={styles.eyebrow}>RECOMENDADO PARA HOY</Text>
          <Text style={styles.heroTitle}>Respirá aire libre en tu próximo sendero</Text>
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

        <TrailCard
          title="Sendero del Bosque"
          location="Reserva Natural, 2.4 km"
          image={trailImages.forest}
          difficulty="Fácil"
          onPress={() => router.push("/trail-detail")}
        />
        <TrailCard
          title="Mirador del Lago"
          location="Parque Serrano, 6.8 km"
          image={trailImages.lake}
          difficulty="Media"
          onPress={() => router.push("/trail-detail")}
        />
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
});

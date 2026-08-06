import React from "react";
import { router } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";

export default function Screen04RouteMap() {
  const insets = useSafeAreaInsets();

  return (
    <ScreenShell>
      <TopBar title="Mapa del recorrido" onBack={() => router.back()} />

      <View style={styles.map}>
        <View style={[styles.pathDot, styles.startDot]}>
          <Ionicons name="flag-outline" size={18} color={colors.white} />
        </View>
        <View style={[styles.segment, styles.segmentOne]} />
        <View style={[styles.segment, styles.segmentTwo]} />
        <View style={[styles.segment, styles.segmentThree]} />
        <View style={[styles.pathDot, styles.endDot]}>
          <Ionicons name="location" size={18} color={colors.white} />
        </View>
        <View style={styles.mapCard}>
          <Text style={styles.mapLabel}>Sendero del Bosque</Text>
          <Text style={styles.mapMeta}>4,2 km - dificultad fácil</Text>
        </View>
      </View>

      <InfoCard style={styles.progressCard}>
        <View>
          <Text style={styles.cardTitle}>Ruta lista</Text>
          <Text style={styles.cardText}>El mapa está disponible para usar sin conexión.</Text>
        </View>
        <View style={styles.downloadBadge}>
          <Ionicons name="cloud-done-outline" size={24} color={colors.green} />
        </View>
      </InfoCard>

      <View style={[styles.footer, { paddingBottom: Math.max(20, insets.bottom + 14) }]}>
        <PrimaryButton
          label="Iniciar recorrido"
          icon="navigate-outline"
          href="/trail-start"
        />
        <PrimaryButton
          label="Tomar descanso"
          icon="pause-circle-outline"
          href="/descanso"
          tone="secondary"
        />
        <PrimaryButton
          label="Reportar terreno"
          icon="warning-outline"
          href="/reportar-terreno"
          tone="secondary"
        />
        <PrimaryButton
          label="Alerta de ruta"
          icon="trail-sign-outline"
          href="/alerta-ruta"
          tone="secondary"
        />
        <PrimaryButton
          label="SOS"
          icon="alert-circle-outline"
          href="/confirmar-sos"
          tone="danger"
        />
      </View>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  map: {
    backgroundColor: "#E8F2E9",
    borderRadius: 30,
    flex: 1,
    marginBottom: 18,
    overflow: "hidden",
    position: "relative",
  },
  segment: {
    backgroundColor: colors.green,
    borderRadius: 10,
    height: 10,
    position: "absolute",
  },
  segmentOne: {
    left: 76,
    top: 210,
    transform: [{ rotate: "-28deg" }],
    width: 128,
  },
  segmentTwo: {
    left: 158,
    top: 160,
    transform: [{ rotate: "18deg" }],
    width: 120,
  },
  segmentThree: {
    left: 236,
    top: 210,
    transform: [{ rotate: "-42deg" }],
    width: 112,
  },
  pathDot: {
    alignItems: "center",
    backgroundColor: colors.green,
    borderRadius: 22,
    height: 44,
    justifyContent: "center",
    position: "absolute",
    width: 44,
    zIndex: 2,
  },
  startDot: {
    left: 58,
    top: 213,
  },
  endDot: {
    right: 50,
    top: 148,
  },
  mapCard: {
    backgroundColor: colors.white,
    borderRadius: 20,
    bottom: 20,
    left: 20,
    padding: 16,
    position: "absolute",
    right: 20,
  },
  mapLabel: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "900",
  },
  mapMeta: {
    color: colors.muted,
    fontSize: 13,
    marginTop: 4,
  },
  progressCard: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 350,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    marginTop: 4,
    maxWidth: 230,
  },
  downloadBadge: {
    alignItems: "center",
    backgroundColor: colors.soft,
    borderRadius: 20,
    height: 48,
    justifyContent: "center",
    width: 48,
  },
  footer: {
    backgroundColor: colors.softer,
    bottom: 0,
    gap: 10,
    left: 0,
    padding: 22,
    paddingBottom: 28,
    position: "absolute",
    right: 0,
  },
});

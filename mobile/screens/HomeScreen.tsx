import { Link } from "expo-router";
import { StatusBar } from "expo-status-bar";
import React from "react";
import {
  ImageBackground,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { BottomNav } from "../components/MiSenderoUI";

const routeMapPreview = require("../../assets/route-map-preview.png");

type TagProps = {
  label: string;
  tone: "green" | "orange";
};

type RouteMetricProps = {
  icon: string;
  label: string;
  accent?: boolean;
};

export default function HomeScreen() {
  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <StatusBar style="dark" />
      <View style={styles.screen}>
        <View style={styles.statusBar}>
          <Text style={styles.statusTime}>9:41</Text>
          <Text style={styles.statusMeta}>GPS • 82%</Text>
        </View>

        <View style={styles.content}>
          <View style={styles.hero}>
            <Text style={styles.title}>Buen día, Bárbara</Text>
            <Text style={styles.subtitle}>
              Prepará tu próxima salida y llevá la ruta sin depender de la señal.
            </Text>
          </View>

          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Recomendada para vos</Text>
              <Link href="/explorar-rutas" style={styles.sectionAction}>
              Ver rutas
              </Link>
          </View>

          <Link href="/cargando-ruta" asChild>
            <Pressable style={styles.routeCard}>
              <ImageBackground
                source={routeMapPreview}
                imageStyle={styles.mapImage}
                style={styles.mapPreview}
              >
                <View style={styles.mapShade} />
                <View style={styles.tags}>
                  <Tag label="Offline" tone="green" />
                  <Tag label="Moderada" tone="orange" />
                </View>
                <Text style={styles.mapTitle}>Sendero Laguna Esmeralda</Text>
              </ImageBackground>

              <View style={styles.routeDetails}>
                <Text style={styles.routeName}>Sendero Laguna Esmeralda</Text>
                <Text style={styles.routeLocation}>Ushuaia, Tierra del Fuego</Text>

                <View style={styles.metrics}>
                  <RouteMetric icon="M" label="9,4 km" />
                  <RouteMetric icon="T" label="4 h 10 min" />
                  <RouteMetric icon="A" label="Moderada" accent />
                </View>
              </View>
            </Pressable>
          </Link>

          <Link href="/cargando-ruta" asChild>
            <Pressable style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Ver detalle de la ruta</Text>
            </Pressable>
          </Link>
        </View>

        <BottomNav active="inicio" />
      </View>
    </SafeAreaView>
  );
}

const Tag = ({ label, tone }: TagProps) => (
  <View style={styles.tag}>
    <View style={[styles.tagDot, tone === "orange" ? styles.orangeDot : styles.greenDot]} />
    <Text style={[styles.tagText, tone === "orange" ? styles.orangeText : styles.greenText]}>
      {label}
    </Text>
  </View>
);

const RouteMetric = ({ icon, label, accent }: RouteMetricProps) => (
  <View style={styles.metric}>
    <View style={[styles.metricIcon, accent && styles.metricIconAccent]}>
      <Text style={[styles.metricIconText, accent && styles.metricIconTextAccent]}>{icon}</Text>
    </View>
    <Text style={[styles.metricLabel, accent && styles.metricLabelAccent]}>{label}</Text>
  </View>
);

const colors = {
  ink: "#131D17",
  muted: "#718178",
  border: "#E0E7E2",
  primary: "#166343",
  primarySoft: "#E5F2EB",
  orange: "#D6801B",
  surface: "#FFFFFF",
  page: "#F7FAF6",
  pageBottom: "#E8EFE7",
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.page,
  },
  screen: {
    flex: 1,
    backgroundColor: colors.page,
  },
  statusBar: {
    height: 44,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 24,
  },
  statusTime: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "500",
    lineHeight: 17,
  },
  statusMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "500",
    lineHeight: 17,
  },
  content: {
    flex: 1,
    gap: 20,
    paddingHorizontal: 24,
    paddingTop: 18,
    paddingBottom: 112,
  },
  hero: {
    gap: 12,
  },
  title: {
    color: colors.ink,
    fontSize: 32,
    fontWeight: "800",
    lineHeight: 38,
  },
  subtitle: {
    color: colors.muted,
    fontSize: 15,
    fontWeight: "500",
    lineHeight: 22,
  },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "600",
    lineHeight: 25,
  },
  sectionAction: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 18,
  },
  routeCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 24,
    borderWidth: 1,
    overflow: "hidden",
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.05,
    shadowRadius: 24,
    elevation: 3,
  },
  mapPreview: {
    height: 220,
    justifyContent: "space-between",
    overflow: "hidden",
    padding: 16,
  },
  mapImage: {
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  mapShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.1)",
  },
  tags: {
    flexDirection: "row",
    gap: 8,
    zIndex: 1,
  },
  tag: {
    alignItems: "center",
    backgroundColor: "rgba(255, 255, 255, 0.9)",
    borderColor: "rgba(255, 255, 255, 0.15)",
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  tagDot: {
    borderRadius: 999,
    height: 6,
    width: 6,
  },
  greenDot: {
    backgroundColor: colors.primary,
  },
  orangeDot: {
    backgroundColor: colors.orange,
  },
  tagText: {
    fontSize: 12,
    fontWeight: "700",
  },
  greenText: {
    color: colors.primary,
  },
  orangeText: {
    color: colors.orange,
  },
  mapTitle: {
    color: colors.surface,
    fontSize: 20,
    fontWeight: "800",
    lineHeight: 26,
    width: 280,
    zIndex: 1,
  },
  routeDetails: {
    gap: 12,
    padding: 16,
  },
  routeName: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "600",
    lineHeight: 25,
  },
  routeLocation: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "500",
    lineHeight: 17,
    marginTop: -8,
  },
  metrics: {
    flexDirection: "row",
    gap: 16,
  },
  metric: {
    alignItems: "center",
    flexDirection: "row",
    gap: 6,
  },
  metricIcon: {
    alignItems: "center",
    borderColor: colors.primary,
    borderRadius: 4,
    borderWidth: 1.5,
    height: 14,
    justifyContent: "center",
    width: 14,
  },
  metricIconAccent: {
    borderColor: colors.orange,
  },
  metricIconText: {
    color: colors.primary,
    fontSize: 8,
    fontWeight: "800",
    lineHeight: 10,
  },
  metricIconTextAccent: {
    color: colors.orange,
  },
  metricLabel: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 18,
  },
  metricLabelAccent: {
    color: colors.orange,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 24,
    height: 52,
    justifyContent: "center",
    width: "100%",
  },
  primaryButtonText: {
    color: colors.surface,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 18,
  },
});

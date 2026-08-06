import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { AppScreen, PrimaryButton, ScreenTitle, colors } from "../../components/MiSenderoUI";

export default function ExploreSkeletonsScreen04() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Explorando"
        title="Cargando rutas"
        subtitle="Estamos preparando recomendaciones cercanas."
      />

      <View style={styles.searchSkeleton}>
        <Ionicons name="search" size={18} color={colors.primary} />
        <View style={styles.lineShort} />
      </View>

      <View style={styles.filterRow}>
        <View style={styles.filterSkeleton} />
        <View style={styles.filterSkeletonSmall} />
        <View style={styles.filterSkeleton} />
      </View>

      <SkeletonCard wide />
      <SkeletonCard />
      <SkeletonCard />

      <View style={styles.footer}>
        <PrimaryButton label="Ver rutas" href="/explorar-rutas" />
        <PrimaryButton label="Ir al inicio" href="/inicio" tone="secondary" />
      </View>
    </AppScreen>
  );
}

function SkeletonCard({ wide }: { wide?: boolean }) {
  return (
    <View style={[styles.card, wide && styles.cardWide]}>
      <View style={styles.imageSkeleton} />
      <View style={styles.cardBody}>
        <View style={styles.lineLong} />
        <View style={styles.lineMedium} />
        <View style={styles.metricRow}>
          <View style={styles.metricSkeleton} />
          <View style={styles.metricSkeleton} />
          <View style={styles.metricSkeletonSmall} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  searchSkeleton: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 18,
    flexDirection: "row",
    gap: 12,
    height: 54,
    marginBottom: 14,
    paddingHorizontal: 16,
  },
  lineShort: {
    backgroundColor: colors.line,
    borderRadius: 999,
    height: 12,
    width: 118,
  },
  filterRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 16,
  },
  filterSkeleton: {
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    height: 34,
    width: 96,
  },
  filterSkeletonSmall: {
    backgroundColor: colors.line,
    borderRadius: 999,
    height: 34,
    width: 72,
  },
  card: {
    backgroundColor: colors.white,
    borderRadius: 22,
    marginBottom: 14,
    overflow: "hidden",
  },
  cardWide: {
    borderColor: colors.primarySoft,
    borderWidth: 1,
  },
  imageSkeleton: {
    backgroundColor: "#DCE9DF",
    height: 118,
  },
  cardBody: {
    gap: 10,
    padding: 14,
  },
  lineLong: {
    backgroundColor: colors.line,
    borderRadius: 999,
    height: 14,
    width: "76%",
  },
  lineMedium: {
    backgroundColor: colors.surface,
    borderRadius: 999,
    height: 12,
    width: "52%",
  },
  metricRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 4,
  },
  metricSkeleton: {
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    height: 24,
    width: 72,
  },
  metricSkeletonSmall: {
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    height: 24,
    width: 54,
  },
  footer: {
    gap: 10,
    marginTop: "auto",
  },
});

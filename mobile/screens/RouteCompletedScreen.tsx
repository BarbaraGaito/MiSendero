import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, Metric, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function RouteCompletedScreen() {
  return (
    <AppScreen activeTab="actividad">
      <View style={styles.successIcon}>
        <Text style={styles.successCheck}>✓</Text>
      </View>
      <ScreenTitle
        eyebrow="Recorrido finalizado"
        title="¡Recorrido completado!"
        subtitle="Guardamos tu actividad y el resumen del sendero."
      />

      <View style={styles.metricsRow}>
        <Metric label="Distancia" value="9,4 km" />
        <Metric label="Tiempo" value="4:10 h" />
        <Metric label="Desnivel" value="312 m" />
      </View>

      <Card tone="green">
        <Text style={styles.cardTitle}>Tu rendimiento</Text>
        <View style={styles.chart}>
          <View style={[styles.bar, { height: 38 }]} />
          <View style={[styles.bar, { height: 74 }]} />
          <View style={[styles.bar, { height: 54 }]} />
          <View style={[styles.bar, { height: 92 }]} />
          <View style={[styles.bar, { height: 66 }]} />
        </View>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Sumaste una nueva ruta</Text>
        <Text style={styles.cardText}>Sendero Laguna Esmeralda ya aparece en tus actividades recientes.</Text>
      </Card>

      <PrimaryButton label="Explorar otra ruta" href="/explorar-rutas" />
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  successIcon: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.successSoft,
    borderRadius: 999,
    height: 72,
    justifyContent: "center",
    marginBottom: 18,
    width: 72,
  },
  successCheck: {
    color: colors.primary,
    fontSize: 34,
    fontWeight: "900",
  },
  metricsRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 14,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
  chart: {
    alignItems: "flex-end",
    flexDirection: "row",
    gap: 14,
    height: 116,
    justifyContent: "center",
    paddingTop: 12,
  },
  bar: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    width: 24,
  },
});

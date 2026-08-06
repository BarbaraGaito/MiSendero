import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function RestBreakScreen() {
  return (
    <AppScreen activeTab="actividad">
      <ScreenTitle
        eyebrow="Recorrido en pausa"
        title="Tomate un respiro"
        subtitle="El seguimiento queda pausado. Podés retomarlo cuando estés lista."
      />

      <Card tone="green">
        <Text style={styles.cardTitle}>Sendero Laguna Esmeralda</Text>
        <Text style={styles.cardText}>Progreso actual: 6,2 km de 9,4 km</Text>
        <View style={styles.progressTrack}>
          <View style={styles.progressFill} />
        </View>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Estado del recorrido</Text>
        <InfoRow label="Tiempo activo" value="2 h 48 min" />
        <InfoRow label="Distancia restante" value="3,2 km" />
        <InfoRow label="Batería estimada" value="1 h 35 min" />
      </Card>

      <Card tone="orange">
        <Text style={styles.cardTitle}>Sugerencia</Text>
        <Text style={styles.cardText}>
          Aprovechá la pausa para revisar agua, abrigo y señal antes de seguir.
        </Text>
      </Card>

      <View style={styles.actions}>
        <PrimaryButton label="Reanudar recorrido" href="/route-map" />
        <PrimaryButton label="Finalizar y guardar" href="/recorrido-finalizado" tone="secondary" />
      </View>
    </AppScreen>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
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
  progressTrack: {
    backgroundColor: colors.surface,
    borderRadius: 999,
    height: 10,
    marginTop: 4,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: "100%",
    width: "66%",
  },
  row: {
    alignItems: "center",
    borderTopColor: colors.border,
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 12,
  },
  rowLabel: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "600",
  },
  rowValue: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
  },
  actions: {
    gap: 10,
    marginTop: "auto",
  },
});

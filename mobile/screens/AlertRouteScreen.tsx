import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function AlertRouteScreen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Alerta de ruta"
        title="Te alejaste de la ruta"
        subtitle="Estás a 180 metros del sendero marcado. Revisá tu posición antes de continuar."
      />

      <Card tone="orange">
        <View style={styles.mapBox}>
          <View style={styles.safePath} />
          <View style={styles.warningPath} />
          <View style={styles.userDot} />
          <View style={styles.targetDot} />
        </View>
        <Text style={styles.cardTitle}>Ruta sugerida</Text>
        <Text style={styles.cardText}>Volvé hacia el tramo principal para retomar el circuito seguro.</Text>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>¿Qué querés hacer?</Text>
        <Text style={styles.cardText}>Podés volver al mapa o marcar que estás bien para seguir registrando actividad.</Text>
      </Card>

      <View style={styles.actions}>
        <PrimaryButton label="Volver a la ruta" href="/route-map" />
        <PrimaryButton label="Estoy bien" href="/recorrido-finalizado" tone="secondary" />
        <PrimaryButton label="Reportar problema" href="/reportar-terreno" tone="danger" />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  mapBox: {
    backgroundColor: "#EFF7EF",
    borderRadius: 22,
    height: 230,
    overflow: "hidden",
    position: "relative",
  },
  safePath: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: 8,
    left: 78,
    position: "absolute",
    top: 118,
    transform: [{ rotate: "-54deg" }],
    width: 178,
  },
  warningPath: {
    borderColor: colors.red,
    borderRadius: 70,
    borderStyle: "dashed",
    borderWidth: 2,
    height: 120,
    position: "absolute",
    right: 42,
    top: 54,
    width: 120,
  },
  userDot: {
    backgroundColor: colors.red,
    borderColor: colors.surface,
    borderRadius: 999,
    borderWidth: 4,
    height: 24,
    position: "absolute",
    right: 66,
    top: 120,
    width: 24,
  },
  targetDot: {
    backgroundColor: colors.primary,
    borderColor: colors.surface,
    borderRadius: 999,
    borderWidth: 4,
    height: 22,
    left: 118,
    position: "absolute",
    top: 86,
    width: 22,
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
  actions: {
    gap: 10,
    marginTop: "auto",
  },
});

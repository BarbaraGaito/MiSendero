import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function ReportSavedScreen() {
  return (
    <AppScreen withBottomNav={false}>
      <View style={styles.iconCircle}>
        <Text style={styles.iconText}>✓</Text>
      </View>

      <ScreenTitle
        eyebrow="Reporte guardado"
        title="Reporte guardado"
        subtitle="Gracias por avisar. Tu reporte ayuda a mejorar la seguridad del sendero."
      />

      <Card tone="green">
        <Text style={styles.cardTitle}>Detalle enviado</Text>
        <Text style={styles.cardText}>Barro en el tramo medio del Sendero Laguna Esmeralda.</Text>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Qué pasa ahora</Text>
        <Text style={styles.cardText}>
          El aviso queda asociado a esta ruta para que otros usuarios puedan verlo.
        </Text>
      </Card>

      <View style={styles.actions}>
        <PrimaryButton label="Volver al mapa" href="/route-map" />
        <PrimaryButton label="Ver mis actividades" href="/mis-actividades" tone="secondary" />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  iconCircle: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.successSoft,
    borderRadius: 999,
    height: 92,
    justifyContent: "center",
    marginBottom: 22,
    width: 92,
  },
  iconText: {
    color: colors.primary,
    fontSize: 42,
    fontWeight: "900",
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

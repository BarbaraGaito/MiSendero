import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function ConfirmSosScreen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Emergencia"
        title="¿Enviar una alerta SOS?"
        subtitle="Usá esta opción solo si necesitás asistencia inmediata."
      />

      <View style={styles.sosCircle}>
        <Text style={styles.sosText}>SOS</Text>
      </View>

      <Card tone="red">
        <Text style={styles.cardTitle}>Se compartirá esta información</Text>
        <Bullet text="Tu ubicación actual" />
        <Bullet text="El sendero en curso" />
        <Bullet text="Tus datos de contacto" />
        <Bullet text="Tu contacto de emergencia" />
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Antes de confirmar</Text>
        <Text style={styles.cardText}>
          Si fue un toque accidental, cancelá y volvé al mapa del recorrido.
        </Text>
      </Card>

      <View style={styles.actions}>
        <PrimaryButton label="Enviar alerta SOS" href="/contacto-seguridad" tone="danger" />
        <PrimaryButton label="Cancelar y volver" href="/alerta-ruta" tone="secondary" />
      </View>
    </AppScreen>
  );
}

function Bullet({ text }: { text: string }) {
  return (
    <View style={styles.bulletRow}>
      <View style={styles.bulletDot} />
      <Text style={styles.bulletText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  sosCircle: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.redSoft,
    borderColor: "#F5C9C4",
    borderRadius: 999,
    borderWidth: 1,
    height: 112,
    justifyContent: "center",
    marginBottom: 22,
    width: 112,
  },
  sosText: {
    color: colors.red,
    fontSize: 24,
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
  bulletRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
  },
  bulletDot: {
    backgroundColor: colors.red,
    borderRadius: 999,
    height: 7,
    width: 7,
  },
  bulletText: {
    color: colors.ink,
    flex: 1,
    fontSize: 14,
    fontWeight: "600",
  },
  actions: {
    gap: 10,
    marginTop: "auto",
  },
});

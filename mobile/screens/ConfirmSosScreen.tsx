import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useState } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";
import { getEmergencyContact } from "../../services/emergencyContact";
import { sendEmergencyAlert } from "../../services/emergencyAlerts";
import { EmergencyContact } from "../../types";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function ConfirmSosScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id) || null;
  const [contact, setContact] = useState<EmergencyContact | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    getEmergencyContact()
      .then(setContact)
      .finally(() => setIsLoading(false));
  }, []);

  const handleSos = async () => {
    if (!contact) {
      router.push("/contacto-seguridad");
      return;
    }

    if (isSending) return;
    setIsSending(true);

    try {
      const outcome = await sendEmergencyAlert(trailId);

      if (outcome === "sent") {
        Alert.alert(
          "Alerta SOS enviada",
          `Se notifico a ${contact.name} (${contact.phone}) con tu ubicacion actual.`
        );
      } else if (outcome === "queued") {
        Alert.alert(
          "Alerta SOS guardada",
          "No hay senal ahora. La alerta se enviara en cuanto la app detecte conexion."
        );
      } else if (outcome === "no_location") {
        Alert.alert(
          "No pudimos obtener tu ubicacion",
          "Activa el GPS y volve a intentar. Mientras tanto, comunicate por otro medio si es posible."
        );
      } else {
        Alert.alert("Sesion requerida", "Inicia sesion para poder enviar una alerta SOS.");
      }
    } finally {
      setIsSending(false);
    }
  };

  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Emergencia"
        title="Enviar una alerta SOS"
        subtitle="Usa esta opcion solo si necesitas asistencia inmediata."
      />

      <View style={styles.sosCircle}>
        <Text style={styles.sosText}>SOS</Text>
      </View>

      <Card tone={contact ? "red" : "orange"}>
        <Text style={styles.cardTitle}>
          {contact ? "Se compartira esta informacion" : "Falta contacto de emergencia"}
        </Text>
        {contact ? (
          <>
            <Bullet text="Tu ubicacion actual" />
            <Bullet text="El sendero en curso" />
            <Bullet text="Tus datos de contacto" />
            <Bullet text={`Contacto: ${contact.name} - ${contact.phone}`} />
          </>
        ) : (
          <Text style={styles.cardText}>
            Para usar SOS primero tenes que guardar un contacto de emergencia con conexion.
            Offline solo se puede consultar un contacto ya guardado.
          </Text>
        )}
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Antes de confirmar</Text>
        <Text style={styles.cardText}>
          Si fue un toque accidental, cancela y volve al mapa del recorrido.
        </Text>
      </Card>

      <View style={styles.actions}>
        <PrimaryButton
          label={
            isLoading
              ? "Verificando contacto"
              : isSending
                ? "Enviando alerta..."
                : contact
                  ? "Enviar alerta SOS"
                  : "Completar contacto"
          }
          onPress={handleSos}
          tone="danger"
        />
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
    marginTop: 6,
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

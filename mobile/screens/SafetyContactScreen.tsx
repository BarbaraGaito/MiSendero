import React from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function SafetyContactScreen() {
  return (
    <AppScreen activeTab="perfil">
      <ScreenTitle
        eyebrow="Contacto de seguridad"
        title="Contacto de seguridad"
        subtitle="Esta persona recibirá avisos si enviás una alerta SOS."
      />

      <Card>
        <Text style={styles.label}>Nombre completo</Text>
        <TextInput
          placeholder="Ej: Ayelén Mendoza"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />

        <Text style={styles.label}>Teléfono</Text>
        <TextInput
          keyboardType="phone-pad"
          placeholder="+54 9 11 5555 5555"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />

        <Text style={styles.label}>Vínculo</Text>
        <TextInput
          placeholder="Familiar, amistad, pareja..."
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
      </Card>

      <Card tone="green">
        <Text style={styles.cardTitle}>Permisos</Text>
        <Text style={styles.cardText}>
          MiSendero usará este contacto solo para alertas de seguridad.
        </Text>
      </Card>

      <View style={styles.footer}>
        <PrimaryButton label="Guardar contacto" href="/perfil" />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  label: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
  },
  input: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 14,
    height: 48,
    marginBottom: 8,
    paddingHorizontal: 12,
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
  footer: {
    marginTop: "auto",
  },
});

import React from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function ReportTerrainScreen() {
  return (
    <AppScreen activeTab="actividad">
      <ScreenTitle
        eyebrow="Reportar terreno"
        title="Reportá el terreno"
        subtitle="Ayudá a otros senderistas avisando cambios o riesgos."
      />

      <Card tone="green">
        <Text style={styles.label}>Ubicación detectada</Text>
        <Text style={styles.value}>Sendero Laguna Esmeralda • km 3,8</Text>
      </Card>

      <Card>
        <Text style={styles.label}>¿Qué encontraste?</Text>
        <View style={styles.options}>
          <Text style={styles.optionActive}>Barro</Text>
          <Text style={styles.option}>Rocas</Text>
          <Text style={styles.option}>Obstrucción</Text>
        </View>
      </Card>

      <Card>
        <Text style={styles.label}>Nivel de dificultad</Text>
        <View style={styles.options}>
          <Text style={styles.option}>Leve</Text>
          <Text style={styles.optionActiveOrange}>Media</Text>
          <Text style={styles.option}>Alta</Text>
        </View>
      </Card>

      <Card>
        <Text style={styles.label}>Detalle opcional</Text>
        <TextInput
          multiline
          placeholder="Ej: el tramo está resbaladizo después de la curva."
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
      </Card>

      <View style={styles.footer}>
        <PrimaryButton label="Enviar reporte" href="/reporte-guardado" />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  label: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  value: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: "700",
  },
  options: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  option: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  optionActive: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    color: colors.surface,
    fontSize: 13,
    fontWeight: "800",
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  optionActiveOrange: {
    backgroundColor: colors.orange,
    borderRadius: 999,
    color: colors.surface,
    fontSize: 13,
    fontWeight: "800",
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  input: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    color: colors.ink,
    minHeight: 92,
    padding: 12,
    textAlignVertical: "top",
  },
  footer: {
    marginTop: "auto",
  },
});

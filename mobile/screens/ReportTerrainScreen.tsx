import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import React, { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { createTrailReport } from "../../services/api";
import { getAuthSession } from "../../services/authSession";
import { enqueue, isOnline } from "../../services/syncQueue";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
  colors,
} from "../components/MiSenderoUI";

const issueOptions = [
  "Barro",
  "Rocas sueltas",
  "Arbol caido",
  "Sendero cortado",
  "Nieve o hielo",
  "Agua alta",
  "Derrumbe",
  "Senalizacion faltante",
  "Animales",
  "Basura",
];

const severityOptions = ["Leve", "Media", "Alta", "Critica"];
const trailStateOptions = [
  "Transitable",
  "Precaucion",
  "Paso dificil",
  "No transitable",
];
const causeOptions = [
  "Lluvia",
  "Viento",
  "Deshielo",
  "Uso intenso",
  "Mantenimiento",
  "No se sabe",
];

export default function ReportTerrainScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id) || 1;
  const [selectedIssues, setSelectedIssues] = useState<string[]>(["Barro"]);
  const [severity, setSeverity] = useState("Media");
  const [trailState, setTrailState] = useState("Precaucion");
  const [cause, setCause] = useState("Lluvia");
  const [blocksPath, setBlocksPath] = useState(false);
  const [details, setDetails] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const canSubmit = selectedIssues.length > 0 && severity && trailState;
  const summary = useMemo(
    () => `${selectedIssues.join(", ")} - ${severity} - ${trailState}`,
    [selectedIssues, severity, trailState]
  );

  const toggleIssue = (issue: string) => {
    setSelectedIssues((current) =>
      current.includes(issue)
        ? current.filter((item) => item !== issue)
        : [...current, issue]
    );
  };

  const submitReport = async () => {
    if (!canSubmit || isSubmitting) return;

    setIsSubmitting(true);
    setSubmitError(null);

    const report = {
      issue_summary: selectedIssues.join(", "),
      severity,
      trail_state: trailState,
      cause,
      blocks_path: blocksPath,
      details,
    };

    try {
      const session = await getAuthSession();
      const online = await isOnline();

      if (session && online) {
        try {
          await createTrailReport(trailId, report, session.token);
          router.push("/reporte-guardado");
          return;
        } catch (submitError) {
          // Falla de red/servidor a pesar de reportar "online": se encola igual,
          // en lugar de perder el reporte que la persona ya completo (RF-10).
        }
      }

      await enqueue("trail_report", { trailId, ...report });
      router.push({ pathname: "/reporte-guardado", params: { pending: "1" } });
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "No pudimos guardar el reporte."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AppScreen activeTab="actividad">
      <ScreenTitle
        eyebrow="Reportar terreno"
        title="Reporta el terreno"
        subtitle="Ayuda a otros senderistas avisando cambios o riesgos."
      />

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Card tone="green">
          <Text style={styles.label}>Ubicacion detectada</Text>
          <Text style={styles.value}>Ruta actual - posicion GPS aproximada</Text>
        </Card>

        <Card>
          <Text style={styles.label}>Que encontraste?</Text>
          <View style={styles.options}>
            {issueOptions.map((issue) => (
              <OptionChip
                key={issue}
                label={issue}
                selected={selectedIssues.includes(issue)}
                onPress={() => toggleIssue(issue)}
              />
            ))}
          </View>
        </Card>

        <Card>
          <Text style={styles.label}>Nivel de riesgo</Text>
          <View style={styles.options}>
            {severityOptions.map((option) => (
              <OptionChip
                key={option}
                label={option}
                selected={severity === option}
                tone={option === "Alta" || option === "Critica" ? "danger" : "green"}
                onPress={() => setSeverity(option)}
              />
            ))}
          </View>
        </Card>

        <Card>
          <Text style={styles.label}>Estado del paso</Text>
          <View style={styles.options}>
            {trailStateOptions.map((option) => (
              <OptionChip
                key={option}
                label={option}
                selected={trailState === option}
                tone={option === "No transitable" ? "danger" : "green"}
                onPress={() => setTrailState(option)}
              />
            ))}
          </View>
        </Card>

        <Card>
          <Text style={styles.label}>Causa probable</Text>
          <View style={styles.options}>
            {causeOptions.map((option) => (
              <OptionChip
                key={option}
                label={option}
                selected={cause === option}
                onPress={() => setCause(option)}
              />
            ))}
          </View>
        </Card>

        <Card>
          <Text style={styles.label}>Bloquea el paso?</Text>
          <View style={styles.options}>
            <OptionChip
              label="No bloquea"
              selected={!blocksPath}
              onPress={() => setBlocksPath(false)}
            />
            <OptionChip
              label="Si, bloquea"
              selected={blocksPath}
              tone="danger"
              onPress={() => setBlocksPath(true)}
            />
          </View>
        </Card>

        <Card>
          <Text style={styles.label}>Detalle opcional</Text>
          <TextInput
            multiline
            value={details}
            onChangeText={setDetails}
            placeholder="Ej: el tramo esta resbaladizo despues de la curva."
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
        </Card>

        <Card tone={blocksPath || severity === "Critica" ? "red" : "green"}>
          <Text style={styles.label}>Resumen</Text>
          <Text style={styles.summaryText}>
            {summary}. Causa: {cause}. {blocksPath ? "Bloquea el paso." : "No bloquea el paso."}
          </Text>
        </Card>

        <View style={styles.footer}>
          {submitError ? <Text style={styles.errorText}>{submitError}</Text> : null}
          <PrimaryButton
            label={isSubmitting ? "Enviando reporte" : "Enviar reporte"}
            icon="send-outline"
            onPress={submitReport}
          />
        </View>
      </ScrollView>
    </AppScreen>
  );
}

function OptionChip({
  label,
  selected,
  onPress,
  tone = "green",
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  tone?: "green" | "danger";
}) {
  const activeColor = tone === "danger" ? colors.danger : colors.primary;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.option,
        selected && { backgroundColor: activeColor, borderColor: activeColor },
      ]}
    >
      {selected ? (
        <Ionicons name="checkmark" size={15} color={colors.white} />
      ) : null}
      <Text style={[styles.optionText, selected && styles.optionTextActive]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    paddingBottom: 24,
  },
  label: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
    marginBottom: 10,
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
    alignItems: "center",
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    minHeight: 38,
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  optionText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "800",
  },
  optionTextActive: {
    color: colors.white,
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
  summaryText: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 20,
  },
  footer: {
    marginTop: 4,
  },
  errorText: {
    color: colors.danger,
    fontSize: 13,
    fontWeight: "800",
    marginBottom: 10,
  },
});

import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";
import {
  calculateExperienceLevel,
  getExperienceProfile,
  saveExperienceProfile,
  skipExperienceProfile,
} from "../../services/experienceProfile";

type Question = {
  id: string;
  title: string;
  subtitle: string;
  options: Array<{ label: string; value: string }>;
};

const questions: Question[] = [
  {
    id: "experience",
    title: "Que experiencia tenes en senderismo?",
    subtitle: "Esto nos ayuda a evitar rutas demasiado exigentes al inicio.",
    options: [
      { label: "Estoy empezando", value: "baja_experiencia" },
      { label: "Salgo ocasionalmente", value: "media_ocasional" },
      { label: "Tengo experiencia alta", value: "alta_experiencia" },
    ],
  },
  {
    id: "activity",
    title: "Como es tu actividad fisica actual?",
    subtitle: "No tiene que ser exacto, alcanza una idea general.",
    options: [
      { label: "Baja", value: "baja_actividad" },
      { label: "Moderada", value: "media_moderada" },
      { label: "Alta", value: "alta_actividad" },
    ],
  },
  {
    id: "distance",
    title: "Que distancia te resulta comoda?",
    subtitle: "Pensando en una salida de trekking normal.",
    options: [
      { label: "Hasta 5 km", value: "corta" },
      { label: "5 a 12 km", value: "media" },
      { label: "Mas de 12 km", value: "larga" },
    ],
  },
  {
    id: "terrain",
    title: "Que tipo de terreno preferis?",
    subtitle: "Se usa para priorizar dificultad y tecnica.",
    options: [
      { label: "Simple y senalizado", value: "baja_tecnica" },
      { label: "Algo irregular", value: "media_tecnica" },
      { label: "Tecnico o exigente", value: "alta_tecnico" },
    ],
  },
  {
    id: "altitude",
    title: "Como te sentis con desnivel?",
    subtitle: "Subidas largas, pendientes y cambios de altura.",
    options: [
      { label: "Prefiero poco desnivel", value: "baja_altitud" },
      { label: "Desnivel moderado", value: "media_altitud" },
      { label: "Me siento comodo", value: "alta_altitud" },
    ],
  },
];

export default function ExperienceOnboardingScreen() {
  const insets = useSafeAreaInsets();
  const { mode } = useLocalSearchParams<{ mode?: string }>();
  const [isCheckingProfile, setIsCheckingProfile] = useState(mode !== "edit");
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const question = questions[step];
  const selectedAnswer = answers[question.id];
  const projectedLevel = calculateExperienceLevel(answers);
  const isLastStep = step === questions.length - 1;

  useEffect(() => {
    if (mode === "edit") return;

    const redirectCompletedProfile = async () => {
      const profile = await getExperienceProfile();

      if (profile.completed) {
        router.replace("/inicio");
        return;
      }

      setIsCheckingProfile(false);
    };

    redirectCompletedProfile();
  }, [mode]);

  const selectAnswer = (value: string) => {
    setAnswers((current) => ({
      ...current,
      [question.id]: value,
    }));
  };

  const continueFlow = async () => {
    if (!selectedAnswer) return;

    if (!isLastStep) {
      setStep((current) => current + 1);
      return;
    }

    await saveExperienceProfile(answers);
    router.replace("/inicio");
  };

  const skipFlow = async () => {
    await skipExperienceProfile();
    router.replace("/inicio");
  };

  if (isCheckingProfile) {
    return null;
  }

  return (
    <ScreenShell>
      <TopBar
        title="Tu experiencia"
        subtitle={`${step + 1} de ${questions.length}`}
        onBack={step > 0 ? () => setStep((current) => current - 1) : undefined}
      />

      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: Math.max(28, insets.bottom + 24) },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.progressTrack}>
          <View
            style={[
              styles.progressFill,
              { width: `${((step + 1) / questions.length) * 100}%` },
            ]}
          />
        </View>

        <Text style={styles.title}>{question.title}</Text>
        <Text style={styles.subtitle}>{question.subtitle}</Text>

        <View style={styles.options}>
          {question.options.map((option) => {
            const selected = selectedAnswer === option.value;

            return (
              <Pressable
                key={option.value}
                onPress={() => selectAnswer(option.value)}
                style={[styles.option, selected && styles.optionSelected]}
              >
                <Text style={[styles.optionText, selected && styles.optionTextSelected]}>
                  {option.label}
                </Text>
                {selected ? (
                  <Ionicons name="checkmark-circle" size={22} color={colors.white} />
                ) : (
                  <Ionicons name="ellipse-outline" size={22} color={colors.muted} />
                )}
              </Pressable>
            );
          })}
        </View>

        <View style={styles.levelPreview}>
          <Text style={styles.levelLabel}>Categoria estimada</Text>
          <Text style={styles.levelValue}>{projectedLevel}</Text>
        </View>

        <View style={styles.footer}>
          <PrimaryButton
            label={isLastStep ? "Guardar perfil" : "Continuar"}
            icon={isLastStep ? "checkmark-outline" : "arrow-forward-outline"}
            onPress={continueFlow}
          />
          <Pressable onPress={skipFlow} style={styles.skipButton}>
            <Text style={styles.skipText}>Omitir y hacerlo mas tarde</Text>
          </Pressable>
        </View>
      </ScrollView>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    flexGrow: 1,
  },
  progressTrack: {
    backgroundColor: colors.line,
    borderRadius: 999,
    height: 8,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: colors.green,
    height: "100%",
  },
  title: {
    color: colors.ink,
    fontSize: 30,
    fontWeight: "900",
    lineHeight: 36,
    marginTop: 28,
  },
  subtitle: {
    color: colors.muted,
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
  },
  options: {
    gap: 12,
    marginTop: 28,
  },
  option: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderColor: colors.line,
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 62,
    paddingHorizontal: 16,
  },
  optionSelected: {
    backgroundColor: colors.green,
    borderColor: colors.green,
  },
  optionText: {
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    fontWeight: "800",
  },
  optionTextSelected: {
    color: colors.white,
  },
  levelPreview: {
    backgroundColor: colors.mint,
    borderRadius: 18,
    marginTop: 22,
    padding: 16,
  },
  levelLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  levelValue: {
    color: colors.greenDark,
    fontSize: 20,
    fontWeight: "900",
    marginTop: 4,
    textTransform: "capitalize",
  },
  footer: {
    gap: 12,
    paddingBottom: 12,
  },
  skipButton: {
    alignItems: "center",
    minHeight: 42,
    justifyContent: "center",
  },
  skipText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "800",
  },
});

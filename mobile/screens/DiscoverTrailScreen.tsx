import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { router } from "expo-router";
import { useNetworkState } from "expo-network";
import { Card, PrimaryButton, ScreenShell, ScreenTitle, colors } from "../components/MiSenderoUI";
import { TrailRecommendationCard } from "../components/TrailRecommendationCard";
import { findRecommendedTrail, getCoveredDestinations } from "../../services/trailAssistant";
import type { Difficulty, Duration, Experience, RecommendationResponse, TrailPreferences, TrailType } from "../../services/trailAssistant";

const types: { value: TrailType; label: string }[] = [
  { value: "naturaleza", label: "🌿 Paseo por la naturaleza" }, { value: "montaña", label: "⛰️ Montaña" },
  { value: "cascadas", label: "💧 Cascadas" }, { value: "lagos", label: "🏞️ Lagos o lagunas" },
  { value: "bosques", label: "🌲 Bosques" }, { value: "miradores", label: "🌅 Miradores" },
  { value: "cualquiera", label: "🥾 Cualquiera" },
];
const durations: { value: Duration; label: string }[] = [
  { value: "menos-1", label: "Menos de 1 hora" }, { value: "1-2", label: "Entre 1 y 2 horas" },
  { value: "2-4", label: "Entre 2 y 4 horas" }, { value: "4-6", label: "Entre 4 y 6 horas" },
  { value: "mas-6", label: "Más de 6 horas" }, { value: "cualquiera", label: "No tengo preferencia" },
];
const difficulties: { value: Difficulty; label: string }[] = [
  { value: "facil", label: "Fácil" }, { value: "moderada", label: "Moderada" },
  { value: "dificil", label: "Difícil" }, { value: "cualquiera", label: "Cualquiera" },
];
const experiences: { value: Experience; label: string }[] = [
  { value: "principiante", label: "Principiante" }, { value: "intermedio", label: "Intermedio" }, { value: "avanzado", label: "Avanzado" },
];
const fold = (text: string) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
const questions = ["¿A dónde querés ir?", "¿Qué tipo de sendero te gustaría hacer?", "¿Cuánto tiempo querés caminar?", "¿Qué dificultad preferís?", "¿Qué experiencia tenés haciendo trekking?"];
export default function DiscoverTrailScreen() {
  const network = useNetworkState();
  const offline = network.isConnected === false || network.isInternetReachable === false;
  const [step, setStep] = useState(0);
  const [destination, setDestination] = useState("");
  const [trailTypes, setTrailTypes] = useState<TrailType[]>([]);
  const [duration, setDuration] = useState<Duration | null>(null);
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null);
  const [experience, setExperience] = useState<Experience | null>(null);
  const [destinations, setDestinations] = useState<string[]>([]);
  const [destinationsLoading, setDestinationsLoading] = useState(false);
  const [destinationsError, setDestinationsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  useEffect(() => {
    if (!offline) setError((current) => current?.startsWith("Necesitás Internet") ? null : current);
  }, [offline]);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const scroll = useRef<ScrollView>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const loadDestinations = useCallback(async () => {
    if (offline) return;
    setDestinationsLoading(true); setDestinationsError(null);
    try {
      const values = await getCoveredDestinations();
      if (mounted.current) setDestinations(values);
    } catch {
      if (mounted.current) setDestinationsError("No pudimos cargar los destinos del catálogo. Intentá nuevamente.");
    } finally { if (mounted.current) setDestinationsLoading(false); }
  }, [offline]);
  useEffect(() => { void loadDestinations(); }, [loadDestinations]);
  useEffect(() => { scroll.current?.scrollTo({ y: 0, animated: true }); }, [step, result, loading]);
  const toggleType = (type: TrailType) => setTrailTypes((current) => type === "cualquiera" ? [type] :
    current.includes(type) ? current.filter((t) => t !== type) : [...current.filter((t) => t !== "cualquiera"), type]);
  const coveredDestination = destinations.some((d) => fold(d) === fold(destination));
  const suggestedDestinations = destinations.filter((d) => !destination.trim() || fold(d).includes(fold(destination))).slice(0, 8);
  const canContinue = [coveredDestination && !destinationsLoading, trailTypes.length > 0, duration !== null, difficulty !== null, experience !== null][step];
  const edit = () => { setResult(null); setError(null); setStep(0); };
  const submit = async () => {
    if (inFlight.current || offline || !duration || !difficulty || !experience || !trailTypes.length || !coveredDestination) return;
    inFlight.current = true; setLoading(true); setError(null);
    try {
      const preferences: TrailPreferences = { destination: destination.trim(), trailTypes, duration, difficulty, experience };
      const response = await findRecommendedTrail(preferences);
      if (mounted.current) setResult(response);
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "No pudimos buscar tu sendero. Intentá nuevamente.");
    } finally { inFlight.current = false; if (mounted.current) setLoading(false); }
  };
  const options = step === 1 ? types : step === 2 ? durations : step === 3 ? difficulties : experiences;
  return <ScreenShell>
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView ref={scroll} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Pressable accessibilityRole="button" accessibilityLabel="Volver" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>‹ Volver</Text>
        </Pressable>
        <ScreenTitle eyebrow="TU PRÓXIMA CAMINATA" title="Descubrí tu sendero" subtitle="Cinco respuestas para encontrar un recorrido para vos." />
        {offline ? <Text accessibilityLiveRegion="polite" style={styles.notice}>Necesitás Internet para generar recomendaciones nuevas. Los mapas descargados siguen disponibles sin conexión.</Text> : null}
        {loading ? <Card>
          <ActivityIndicator size="large" color={colors.green} accessibilityLabel="Buscando el sendero ideal para vos..." />
          <Text accessibilityLiveRegion="polite" style={styles.loading}>Buscando el sendero ideal para vos...</Text>
        </Card> : result ? <View accessibilityLiveRegion="polite">
          <Text style={styles.resultTitle}>{result.message}</Text>
          {result.recommendation ? <TrailRecommendationCard key={result.recommendation.trailId} trail={result.recommendation} onRestart={edit} />
            : <PrimaryButton label="Modificar respuestas" onPress={edit} />}
        </View> : <>
          <Text style={styles.step}>{`Paso ${step + 1} de 5`}</Text>
          <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 5, now: step + 1 }} style={styles.track}>
            <View style={[styles.progress, { width: `${(step + 1) * 20}%` }]} />
          </View>
          <Text accessibilityRole="header" style={styles.question}>{questions[step]}</Text>
          {step === 0 ? <Card>
            <TextInput accessibilityLabel="Destino" placeholder="Por ejemplo: Bariloche o El Chaltén" placeholderTextColor={colors.muted}
              value={destination} onChangeText={setDestination} maxLength={120} autoCapitalize="words" returnKeyType="next"
              onSubmitEditing={() => { if (canContinue) setStep(1); }} style={styles.input} />
            <Text style={styles.hint}>Buscá y seleccioná una ciudad, provincia o parque de nuestro catálogo.</Text>
            {destinationsLoading ? <ActivityIndicator accessibilityLabel="Cargando destinos" color={colors.green} /> : null}
            {destinationsError ? <>
              <Text accessibilityRole="alert" style={styles.error}>{destinationsError}</Text>
              <PrimaryButton label="Reintentar destinos" tone="secondary" onPress={() => { void loadDestinations(); }} />
            </> : null}
            {!offline && !destinationsLoading && !destinationsError && !suggestedDestinations.length ? <Text style={styles.hint}>No encontramos destinos cubiertos con ese nombre. Probá con otra zona.</Text> : null}
            {suggestedDestinations.map((value) => <Pressable key={value} accessibilityRole="radio" accessibilityLabel={`Destino: ${value}`}
              accessibilityState={{ checked: fold(value) === fold(destination) }} onPress={() => setDestination(value)} style={styles.destination}>
              <Text style={styles.optionText}>{value}</Text>
            </Pressable>)}
          </Card> : <>
            {step === 1 ? <Text style={styles.hint}>Podés elegir varias opciones. Buscaremos coincidencias con al menos una.</Text> : null}
            {step === 2 ? <Text style={styles.hint}>Tiempo total de caminata, incluyendo ida y vuelta cuando corresponde.</Text> : null}
            {step === 4 ? <Text style={styles.hint}>Para principiantes buscamos dificultad fácil. Para nivel intermedio excluimos dificultad alta.</Text> : null}
            {options.map((option) => {
              const selected = step === 1 ? trailTypes.includes(option.value as TrailType) : step === 2 ? duration === option.value : step === 3 ? difficulty === option.value : experience === option.value;
              return <Pressable key={option.value} accessibilityRole={step === 1 ? "checkbox" : "radio"} accessibilityLabel={option.label}
                accessibilityState={{ checked: selected }} onPress={() => step === 1 ? toggleType(option.value as TrailType) : step === 2 ? setDuration(option.value as Duration) : step === 3 ? setDifficulty(option.value as Difficulty) : setExperience(option.value as Experience)}
                style={({ pressed }) => [styles.option, selected && styles.selected, pressed && styles.pressed]}>
                <Text style={[styles.optionText, selected && styles.selectedText]}>{option.label}</Text>
                <Text style={styles.check}>{selected ? "✓" : "○"}</Text>
              </Pressable>;
            })}
          </>}
          {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          <View style={styles.actions}>
            {step > 0 ? <PrimaryButton label="Anterior" tone="secondary" onPress={() => { setError(null); setStep((s) => s - 1); }} /> : null}
            <PrimaryButton label={step === 4 ? "Encontrar mi sendero" : "Continuar"} disabled={!canContinue || (step === 4 && offline)}
              onPress={() => { if (step === 4) void submit(); else { setError(null); setStep((s) => s + 1); } }} />
          </View>
        </>}
      </ScrollView>
    </KeyboardAvoidingView>
  </ScreenShell>;
}
const styles = StyleSheet.create({
  flex: { flex: 1 }, content: { paddingBottom: 32 }, back: { paddingVertical: 10, alignSelf: "flex-start" },
  backText: { fontSize: 16, color: colors.greenDark, fontWeight: "700" },
  notice: { padding: 14, borderRadius: 14, backgroundColor: colors.mint, color: colors.greenDark, fontSize: 13, lineHeight: 20, marginBottom: 24 },
  step: { color: colors.greenDark, fontWeight: "700", marginBottom: 10 }, track: { height: 7, backgroundColor: colors.line, borderRadius: 8, overflow: "hidden", marginBottom: 24 },
  progress: { height: 7, backgroundColor: colors.green, borderRadius: 8 },
  question: { fontFamily: "BricolageGrotesque_700Bold", color: colors.ink, fontSize: 25, lineHeight: 31, marginBottom: 18 },
  input: { borderWidth: 1, borderColor: colors.line, borderRadius: 14, padding: 14, color: colors.ink, fontSize: 16, backgroundColor: colors.white },
  hint: { fontSize: 13, color: colors.muted, lineHeight: 21, marginVertical: 12 },
  destination: { borderTopWidth: 1, borderTopColor: colors.line, paddingVertical: 12 },
  option: { flexDirection: "row", alignItems: "center", gap: 12, padding: 18, borderRadius: 18, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white, marginBottom: 10 },
  selected: { borderColor: colors.green, backgroundColor: colors.mint }, optionText: { flex: 1, fontSize: 16, color: colors.ink, fontWeight: "600" },
  selectedText: { color: colors.greenDark }, check: { color: colors.green, fontWeight: "800", fontSize: 20 }, pressed: { opacity: 0.75 },
  actions: { gap: 12, marginTop: 20 }, loading: { color: colors.greenDark, fontSize: 19, textAlign: "center", marginTop: 20, lineHeight: 27 },
  resultTitle: { fontFamily: "BricolageGrotesque_700Bold", fontSize: 24, color: colors.greenDark, lineHeight: 31, marginBottom: 18 },
  error: { color: colors.danger, lineHeight: 22, marginTop: 16 },
});

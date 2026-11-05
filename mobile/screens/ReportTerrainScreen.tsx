import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { randomUUID } from "expo-crypto";
import { useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { getTrailById, getTrailReports } from "../../services/trailRepository";
import { Coordinate, formatDistance, getClosestPointOnRoute, getDistanceToRouteMeters, getRouteProgressMeters, parseRouteCoordinates } from "../../services/geoUtils";
import { enqueue, runSync } from "../../services/syncQueue";
import { userMessage } from "../../services/userMessages";
import { findSimilarReports, passageOptions, parseObservationDate } from "../../services/reportExperience";
import { Trail, TrailReport } from "../../types";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";
import { TrailMap } from "../components/TrailMap";
import { ReportFeedbackControls } from "../components/ReportFeedbackControls";
import { useDeviceLocation } from "../hooks/useDeviceLocation";

const issueOptions = ["Barro", "Rocas sueltas", "Arbol caido", "Sendero cortado", "Nieve o hielo", "Agua alta", "Derrumbe", "Senalizacion faltante", "Animales", "Basura"];
const causeOptions = ["Lluvia", "Viento", "Deshielo", "Uso intenso", "Mantenimiento", "No se sabe"];
const observationOptions = [
  { label: "Ahora", minutes: 0 }, { label: "Hace 30 min", minutes: 30 },
  { label: "Hace 1 h", minutes: 60 }, { label: "Hace 3 h", minutes: 180 }, { label: "Ayer (aprox.)", minutes: 1440 },
];
type ReportLocation = { coordinate: Coordinate; accuracyMeters: number | null; routeProgressMeters: number };

export default function ReportTerrainScreen() {
  const { id, startedAt, latitude, longitude, perspective } = useLocalSearchParams<{
    id?: string; startedAt?: string; latitude?: string; longitude?: string; perspective?: string;
  }>();
  const trailId = Number(id) || 1;
  const [selectedIssues, setSelectedIssues] = useState<string[]>([]);
  const [passageId, setPassageId] = useState<string | null>(null);
  const [cause, setCause] = useState<string | null>(null);
  const [details, setDetails] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const [observationLabel, setObservationLabel] = useState<string | null>(null);
  const [customObservation, setCustomObservation] = useState("");
  const [trail, setTrail] = useState<Trail | null>(null);
  const [reports, setReports] = useState<TrailReport[]>([]);
  const [locationMode, setLocationMode] = useState<"current" | "map">(latitude != null || longitude != null ? "map" : "current");
  const [capturedLocation, setCapturedLocation] = useState<ReportLocation | null>(null);
  const [mapLocation, setMapLocation] = useState<ReportLocation | null>(null);
  const [endLocation, setEndLocation] = useState<ReportLocation | null>(null);
  const [isSection, setIsSection] = useState(false);
  const [selectionTarget, setSelectionTarget] = useState<"start" | "end">("start");
  const [locationMessage, setLocationMessage] = useState<string | null>(null);
  const [isMapInteracting, setIsMapInteracting] = useState(false);
  const [duplicateOverride, setDuplicateOverride] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { location, isLoading: isLocationLoading, permissionDenied } = useDeviceLocation(true);

  useEffect(() => {
    let active = true;
    setTrail(null); setReports([]); setCapturedLocation(null); setMapLocation(null); setEndLocation(null);
    setSelectedIssues([]); setPassageId(null); setObservedAt(null); setObservationLabel(null); setDuplicateOverride(null);
    setCause(null); setDetails(""); setShowDetails(false); setCustomObservation("");
    setIsSection(false); setSelectionTarget("start"); setLocationMessage(null); setSubmitError(null);
    setLocationMode(latitude != null || longitude != null ? "map" : "current");
    getTrailById(trailId).then(value => { if (active) setTrail(value); }).catch(() => { if (active) setTrail(null); });
    getTrailReports(trailId).then(value => { if (active) setReports(value); }).catch(() => undefined);
    return () => { active = false; };
  }, [trailId]);

  const routePoints = useMemo(() => parseRouteCoordinates(trail?.route_coordinates), [trail?.route_coordinates]);
  const currentValidation = useMemo(() => {
    if (!location) return null;
    if (routePoints.length < 2) return "Esta ruta no tiene trazado suficiente para validar la ubicación.";
    if (location.accuracy != null && location.accuracy > 80) return `El GPS tiene un margen de ${Math.round(location.accuracy)} m. Elegí el lugar en el mapa.`;
    const distance = getDistanceToRouteMeters(location.coordinate, routePoints);
    if (distance == null) return "No pudimos validar tu ubicación. Elegí un punto en el mapa.";
    if (distance > 80 + Math.min(Math.max(location.accuracy ?? 0, 0), 50)) return `Estás a ${formatDistance(distance)} del sendero. Elegí un punto sobre el recorrido.`;
    return null;
  }, [location, routePoints]);
  const currentReportLocation = useMemo<ReportLocation | null>(() => {
    if (!location || trail?.id !== trailId || currentValidation || routePoints.length < 2) return null;
    const progress = getRouteProgressMeters(location.coordinate, routePoints);
    return progress == null ? null : { coordinate: [...location.coordinate], accuracyMeters: location.accuracy, routeProgressMeters: progress };
  }, [location, trail?.id, trailId, currentValidation, routePoints]);

  // Capture the first valid position. Walking while filling the form must not move the incident.
  useEffect(() => { if (!capturedLocation && currentReportLocation) setCapturedLocation(currentReportLocation); }, [capturedLocation, currentReportLocation]);
  useEffect(() => {
    if ((latitude == null && longitude == null) || routePoints.length < 2 || trail?.id !== trailId) return;
    const coordinate: Coordinate = [Number(latitude), Number(longitude)];
    const valid = latitude != null && longitude != null && coordinate.every(Number.isFinite) && Math.abs(coordinate[0]) <= 90 && Math.abs(coordinate[1]) <= 180;
    const closest = valid ? getClosestPointOnRoute(coordinate, routePoints) : null;
    setLocationMode("map");
    if (!closest || closest.distanceMeters > 80) {
      setMapLocation(null); setLocationMessage("No pudimos validar ese punto. Elegí una ubicación sobre el sendero."); return;
    }
    setMapLocation({ coordinate: closest.coordinate, accuracyMeters: null, routeProgressMeters: closest.progressMeters });
    setLocationMessage("Punto elegido en el mapa. Podés ajustarlo antes de enviar.");
  }, [latitude, longitude, routePoints, trail?.id, trailId]);

  const selectedLocation = locationMode === "map" ? mapLocation : capturedLocation;
  const ordered = selectedLocation && isSection && endLocation
    ? [selectedLocation, endLocation].sort((a, b) => a.routeProgressMeters - b.routeProgressMeters) : null;
  const start = ordered?.[0] ?? selectedLocation;
  const end = ordered?.[1] ?? null;
  const sectionValid = !isSection || Boolean(start && end && end.routeProgressMeters - start.routeProgressMeters >= 5);
  const passage = passageOptions.find(option => option.id === passageId);
  const similar = useMemo(() => findSimilarReports(reports, trailId, selectedIssues, start?.coordinate ?? null,
    start?.routeProgressMeters ?? null, end?.routeProgressMeters ?? null), [reports, trailId, selectedIssues, start?.coordinate, start?.routeProgressMeters, end?.routeProgressMeters]);
  const duplicateKey = JSON.stringify([selectedIssues, start?.coordinate, end?.coordinate, similar.map(report => report.id)]);
  const hasDuplicate = similar.length > 0 && duplicateOverride !== duplicateKey;
  const canSubmit = trail?.id === trailId && selectedIssues.length > 0 && Boolean(passage && observedAt && start) && sectionValid && !hasDuplicate;
  const refreshReports = async () => setReports(await getTrailReports(trailId));
  const returnAfterSave = () => router.replace({ pathname: "/reporte-guardado", params: { pending: "1", id: String(trailId), startedAt: startedAt ?? "" } });
  const submitReport = async () => {
    if (!canSubmit || submittingRef.current || !start || !passage || !observedAt) return;
    submittingRef.current = true; setIsSubmitting(true); setSubmitError(null);
    try {
      await enqueue("trail_report", {
        trailId, client_event_id: randomUUID(), observed_at: observedAt, issue_summary: selectedIssues.join(", "),
        severity: passage.severity, trail_state: passage.trailState, blocks_path: passage.blocksPath, cause, details,
        latitude: start.coordinate[0], longitude: start.coordinate[1], accuracy_meters: start.accuracyMeters,
        route_progress_meters: start.routeProgressMeters,
        ...(end ? { end_latitude: end.coordinate[0], end_longitude: end.coordinate[1], route_end_progress_meters: end.routeProgressMeters } : {}),
      });
      void runSync().catch(() => undefined);
      returnAfterSave();
    } catch (error) { setSubmitError(userMessage(error, "No pudimos guardar el reporte. Intentá nuevamente.")); }
    finally { submittingRef.current = false; setIsSubmitting(false); }
  };

  return <AppScreen activeTab="actividad">
    <ScreenTitle eyebrow="Reportar terreno" title="¿Qué encontraste?" subtitle="Elegí el incidente, cómo está el paso y cuándo lo viste." />
    <ScrollView scrollEnabled={!isMapInteracting} contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
      <Card>
        <Text style={styles.title}>1. Qué ocurrió</Text>
        <View style={styles.options}>{issueOptions.map(issue => <OptionChip key={issue} label={issue} selected={selectedIssues.includes(issue)}
          onPress={() => setSelectedIssues(items => items.includes(issue) ? items.filter(value => value !== issue) : [...items, issue])} />)}</View>
      </Card>
      <Card>
        <Text style={styles.title}>2. ¿Se puede pasar?</Text>
        <View style={styles.passageOptions}>{passageOptions.map(option => <Pressable key={option.id} accessibilityRole="button"
          accessibilityLabel={option.label} accessibilityState={{ selected: passageId === option.id }} onPress={() => setPassageId(option.id)}
          style={[styles.passage, passageId === option.id && styles.passageSelected]}>
          <Ionicons name={option.blocksPath ? "close-circle-outline" : "walk-outline"} size={22} color={option.blocksPath ? colors.danger : colors.green} />
          <View style={styles.flex}><Text style={styles.passageLabel}>{option.label}</Text><Text style={styles.hint}>{option.hint}</Text></View>
          {passageId === option.id ? <Ionicons name="checkmark-circle" size={22} color={colors.green} /> : null}
        </Pressable>)}</View>
      </Card>
      <Card>
        <Text style={styles.title}>3. ¿Cuándo lo viste?</Text>
        <View style={styles.options}>{observationOptions.map(option => <OptionChip key={option.label} label={option.label}
          selected={observationLabel === option.label} onPress={() => { setObservationLabel(option.label); setObservedAt(new Date(Date.now() - option.minutes * 60000).toISOString()); }} />)}</View>
        <View style={styles.spaced}><OptionChip label="Otra fecha" selected={observationLabel === "custom"} onPress={() => { setObservationLabel("custom"); setObservedAt(parseObservationDate(customObservation)); }} /></View>
        {observationLabel === "custom" ? <View style={styles.spaced}>
          <TextInput accessibilityLabel="Fecha y hora de observación" placeholder="DD/MM/AAAA HH:mm" autoCapitalize="none" value={customObservation}
            onChangeText={value => { setCustomObservation(value); setObservedAt(parseObservationDate(value)); }} style={styles.dateInput} />
          {!observedAt ? <Text style={styles.error}>Ingresá una fecha válida de los últimos 30 días, sin fechas futuras.</Text> : null}
        </View> : null}
        <Text style={styles.hint}>La fecha corresponde a tu observación, incluso si enviás el aviso más tarde.</Text>
      </Card>
      <Card tone="green">
        <Text style={styles.title}>Lugar del incidente</Text>
        <View style={styles.options}>
          <OptionChip label="Usar actual" selected={locationMode === "current" && !isSection} onPress={() => {
            setLocationMode("current"); setIsSection(false); setEndLocation(null); setCapturedLocation(currentReportLocation); setLocationMessage(currentValidation);
          }} />
          <OptionChip label="Elegir en mapa" selected={locationMode === "map"} onPress={() => { setLocationMode("map"); setLocationMessage(null); }} />
        </View>
        <View style={[styles.options, styles.spaced]}>
          <OptionChip label="Un punto" selected={!isSection} onPress={() => { setIsSection(false); setEndLocation(null); setSelectionTarget("start"); }} />
          <OptionChip label="Un tramo" selected={isSection} onPress={() => {
            setIsSection(true); setLocationMode("map"); if (selectedLocation) setMapLocation(selectedLocation);
            setSelectionTarget(selectedLocation ? "end" : "start"); setLocationMessage("Marcá dónde empieza y termina el sector afectado.");
          }} />
        </View>
        <Text style={styles.location}>{selectedLocation ? formatLocation(selectedLocation) : locationMode === "map" ? "Tocá un punto sobre el sendero." :
          currentValidation || (permissionDenied ? "GPS sin permiso. Podés elegir en el mapa." : isLocationLoading ? "Buscando posición GPS…" : "Elegí la ubicación en el mapa.")}</Text>
        {locationMode === "current" && capturedLocation ? <Text style={styles.hint}>Ubicación tomada al iniciar el reporte{capturedLocation.accuracyMeters != null ? ` · precisión GPS ±${Math.round(capturedLocation.accuracyMeters)} m` : ""}. “Usar actual” la actualiza.</Text> : null}
        {locationMessage ? <Text accessibilityLiveRegion="polite" style={styles.hint}>{locationMessage}</Text> : null}
        {isSection ? <View style={[styles.options, styles.spaced]}>
          <OptionChip label="Marcar inicio" selected={selectionTarget === "start"} onPress={() => setSelectionTarget("start")} />
          <OptionChip label="Marcar fin" selected={selectionTarget === "end"} onPress={() => setSelectionTarget("end")} />
          <Text style={styles.hint}>{end ? `Sector de ${formatDistance(end.routeProgressMeters - (start?.routeProgressMeters ?? 0))}` : "Falta marcar el final del tramo."}</Text>
        </View> : null}
        {locationMode === "map" ? <View style={styles.spaced}>
          <TrailMap trail={trail} reports={reports} initialPerspective={perspective === "1"} fitRoute showDetailsCard={false} showUserLocation={false}
            onInteractionChange={setIsMapInteracting} onReportsChanged={refreshReports} selectedCoordinate={mapLocation?.coordinate ?? null} selectedEndCoordinate={endLocation?.coordinate ?? null}
            selectedRouteRange={start && end ? { start: start.routeProgressMeters, end: end.routeProgressMeters } : null}
            onSelectCoordinate={({ coordinate, routeProgressMeters }) => {
              const selection = { coordinate, routeProgressMeters, accuracyMeters: null };
              if (isSection && selectionTarget === "end") setEndLocation(selection);
              else { setMapLocation(selection); if (isSection) setSelectionTarget("end"); }
              setLocationMessage(isSection ? "Punto del tramo seleccionado. Podés ajustar ambos extremos." : "Punto seleccionado sobre el sendero.");
            }}
            onSelectionRejected={distance => setLocationMessage(distance == null ? "Esta ruta no tiene trazado suficiente para elegir un punto." : "Elegí un punto sobre el sendero marcado.")} />
        </View> : null}
      </Card>
      {hasDuplicate ? <Card tone="green">
        <Text style={styles.title}>Ya hay un aviso parecido en este sector</Text>
        <Text style={styles.hint}>Si es el mismo incidente, actualizá el aviso existente para evitar marcas repetidas.</Text>
        {similar.slice(0, 3).map(report => <View key={report.id} style={styles.spaced}>
          <Text style={styles.passageLabel}>{report.issue_summary} · {report.trail_state}</Text>
          {observedAt ? <ReportFeedbackControls report={report} observedAt={observedAt} onChanged={refreshReports} onRecorded={returnAfterSave} />
            : <Text style={styles.hint}>Indicá cuándo lo viste para actualizar este aviso.</Text>}
        </View>)}
        <PrimaryButton label="Es otro incidente: crear reporte" tone="secondary" onPress={() => setDuplicateOverride(duplicateKey)} />
      </Card> : null}
      <PrimaryButton label={showDetails ? "Ocultar detalles opcionales" : "Agregar detalles opcionales"} tone="secondary" onPress={() => setShowDetails(value => !value)} />
      {showDetails ? <Card>
        <Text style={styles.title}>Causa, si la conocés</Text>
        <View style={styles.options}>{causeOptions.map(option => <OptionChip key={option} label={option} selected={cause === option} onPress={() => setCause(value => value === option ? null : option)} />)}</View>
        <Text style={[styles.title, styles.spaced]}>Detalle opcional</Text>
        <TextInput accessibilityLabel="Detalle del incidente" value={details} onChangeText={setDetails} multiline maxLength={1000}
          placeholder="Ej.: el obstáculo está después de la curva." style={styles.input} />
      </Card> : null}
      <Card tone={passage?.blocksPath ? "red" : "green"}>
        <Text style={styles.title}>Resumen del aviso</Text>
        <Text style={styles.summary}>{selectedIssues.length ? selectedIssues.join(", ") : "Elegí qué ocurrió."}{passage ? ` · ${passage.label} · Riesgo ${passage.severity}` : ""}</Text>
        {start ? <Text style={styles.hint}>Coordenadas: {formatLocation(start)}{end ? ` hasta km ${(end.routeProgressMeters / 1000).toLocaleString("es-AR", { maximumFractionDigits: 2 })}` : ""}</Text> : null}
        {observedAt ? <Text style={styles.hint}>Observado: {new Date(observedAt).toLocaleString("es-AR")}</Text> : null}
        {!sectionValid ? <Text style={styles.error}>Marcá dos puntos distintos del sendero, separados al menos 5 m.</Text> : null}
      </Card>
      <Text style={styles.hint}>El lugar se publica aproximado, con margen de hasta 150 m y horario por hora. El texto libre queda disponible solo para vos y moderación. No ingreses datos de otras personas.</Text>
      {submitError ? <Text accessibilityRole="alert" style={styles.error}>{submitError}</Text> : null}
      <PrimaryButton label={isSubmitting ? "Enviando reporte" : "Enviar reporte"} icon="send-outline" onPress={submitReport} disabled={!canSubmit || isSubmitting} />
    </ScrollView>
  </AppScreen>;
}

function formatLocation(location: ReportLocation) {
  return `${location.coordinate[0].toFixed(5)}, ${location.coordinate[1].toFixed(5)} · km ${(location.routeProgressMeters / 1000).toLocaleString("es-AR", { maximumFractionDigits: 2 })}`;
}
function OptionChip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ selected }} onPress={onPress} style={[styles.option, selected && styles.optionSelected]}>
    {selected ? <Ionicons name="checkmark" size={15} color={colors.white} /> : null}
    <Text style={[styles.optionText, selected && styles.optionTextSelected]}>{label}</Text>
  </Pressable>;
}
const styles = StyleSheet.create({
  scroll: { paddingBottom: 28, gap: 10 }, title: { color: colors.ink, fontSize: 16, fontWeight: "800", marginBottom: 10 },
  options: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, option: { minHeight: 44, paddingHorizontal: 12, paddingVertical: 9,
    flexDirection: "row", alignItems: "center", gap: 5, borderRadius: 20, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.page },
  optionSelected: { backgroundColor: colors.green, borderColor: colors.green }, optionText: { color: colors.greenDark, fontSize: 13, fontWeight: "700" },
  optionTextSelected: { color: colors.white }, passageOptions: { gap: 8 }, passage: { flexDirection: "row", alignItems: "center", gap: 10,
    borderWidth: 1, borderColor: colors.border, borderRadius: 15, padding: 12, minHeight: 64 },
  passageSelected: { backgroundColor: colors.successSoft, borderColor: colors.green }, passageLabel: { color: colors.ink, fontSize: 14, fontWeight: "800" },
  flex: { flex: 1 }, hint: { color: colors.muted, fontSize: 12, lineHeight: 18 }, spaced: { marginTop: 12 },
  location: { color: colors.greenDark, fontWeight: "700", fontSize: 13, lineHeight: 20, marginTop: 10 },
  input: { minHeight: 90, color: colors.ink, borderColor: colors.border, borderWidth: 1, borderRadius: 12, padding: 12, textAlignVertical: "top" },
  dateInput: { minHeight: 48, color: colors.ink, borderColor: colors.border, borderWidth: 1, borderRadius: 12, padding: 10 },
  summary: { color: colors.ink, fontSize: 14, lineHeight: 21 }, error: { color: colors.danger, fontSize: 13, lineHeight: 19 },
});

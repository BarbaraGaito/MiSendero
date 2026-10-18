import { Ionicons } from "@expo/vector-icons";
import { userMessage } from "../../services/userMessages";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { randomUUID } from "expo-crypto";
import { getTrailById } from "../../services/trailRepository";
import {
  Coordinate,
  formatDistance,
  getDistanceToRouteMeters,
  getRouteProgressMeters,
  parseRouteCoordinates,
} from "../../services/geoUtils";
import { enqueue, runSync } from "../../services/syncQueue";
import { Trail } from "../../types";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
  colors,
} from "../components/MiSenderoUI";
import { TrailMap } from "../components/TrailMap";
import { useDeviceLocation } from "../hooks/useDeviceLocation";

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
const REPORT_LOCATION_TOLERANCE_METERS = 80;
const GPS_ACCURACY_BUFFER_CAP_METERS = 50;

type LocationMode = "current" | "map";
type SelectedReportLocation = {
  coordinate: Coordinate;
  accuracyMeters: number | null;
  routeProgressMeters: number | null;
  source: LocationMode;
};

export default function ReportTerrainScreen() {
  const { id, startedAt } = useLocalSearchParams<{ id?: string; startedAt?: string }>();
  const trailId = Number(id) || 1;
  const [selectedIssues, setSelectedIssues] = useState<string[]>(["Barro"]);
  const [severity, setSeverity] = useState("Media");
  const [trailState, setTrailState] = useState("Precaucion");
  const [cause, setCause] = useState("Lluvia");
  const [blocksPath, setBlocksPath] = useState(false);
  const [details, setDetails] = useState("");
  const [trail, setTrail] = useState<Trail | null>(null);
  const [locationMode, setLocationMode] = useState<LocationMode>("current");
  const [selectedMapLocation, setSelectedMapLocation] =
    useState<SelectedReportLocation | null>(null);
  const [locationMessage, setLocationMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { location, isLoading: isLocationLoading, permissionDenied } =
    useDeviceLocation(true);

  useEffect(() => {
    getTrailById(trailId).then(setTrail).catch(() => setTrail(null));
  }, [trailId]);

  const routePoints = useMemo(
    () => parseRouteCoordinates(trail?.route_coordinates),
    [trail?.route_coordinates]
  );
  const summary = useMemo(
    () => `${selectedIssues.join(", ")} - ${severity} - ${trailState}`,
    [selectedIssues, severity, trailState]
  );
  const currentRouteProgressMeters = useMemo(() => {
    if (!location || routePoints.length === 0) return null;

    return getRouteProgressMeters(location.coordinate, routePoints);
  }, [location, routePoints]);
  const currentRouteDistanceMeters = useMemo(() => {
    if (!location || routePoints.length === 0) return null;

    return getDistanceToRouteMeters(location.coordinate, routePoints);
  }, [location, routePoints]);
  const currentLocationValidationMessage = useMemo(() => {
    if (!location) return null;
    if (routePoints.length === 0) {
      return "Esta ruta no tiene trazado suficiente para guardar coordenadas validadas.";
    }
    if (currentRouteDistanceMeters === null) {
      return "No pudimos validar si tu ubicacion esta sobre el sendero. Elegi un punto en el mapa.";
    }

    const accuracyBuffer = Math.min(
      Math.max(location.accuracy ?? 0, 0),
      GPS_ACCURACY_BUFFER_CAP_METERS
    );
    const allowedDistance = REPORT_LOCATION_TOLERANCE_METERS + accuracyBuffer;

    if (currentRouteDistanceMeters > allowedDistance) {
      return `Estas a ${formatDistance(currentRouteDistanceMeters)} del sendero. Acercate o elegi un punto valido en el mapa.`;
    }

    return null;
  }, [currentRouteDistanceMeters, location, routePoints.length]);
  const currentReportLocation: SelectedReportLocation | null =
    location && !currentLocationValidationMessage
      ? {
          coordinate: location.coordinate,
          accuracyMeters: location.accuracy,
          routeProgressMeters: currentRouteProgressMeters,
          source: "current",
        }
      : null;
  const selectedReportLocation: SelectedReportLocation | null =
    locationMode === "map"
      ? selectedMapLocation
      : currentReportLocation;
  const canSubmit =
    selectedIssues.length > 0 &&
    Boolean(severity) &&
    Boolean(trailState) &&
    Boolean(selectedReportLocation);

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
      client_event_id: randomUUID(),
      observed_at: new Date().toISOString(),
      issue_summary: selectedIssues.join(", "),
      severity,
      trail_state: trailState,
      cause,
      blocks_path: blocksPath,
      details,
      latitude: selectedReportLocation?.coordinate[0] ?? null,
      longitude: selectedReportLocation?.coordinate[1] ?? null,
      accuracy_meters: selectedReportLocation?.accuracyMeters ?? null,
      route_progress_meters: selectedReportLocation?.routeProgressMeters ?? null,
    };

    try {
      // Persist before the first HTTP attempt, also when online.
      await enqueue("trail_report", { trailId, ...report });
      void runSync().catch(() => undefined);
      router.replace({ pathname: "/reporte-guardado", params: { pending: "1", id: String(trailId), startedAt: startedAt ?? "" } });
    } catch (error) {
      setSubmitError(
        userMessage(error, "No pudimos guardar el reporte. Intentá nuevamente.")
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
          <Text style={styles.label}>Ubicacion del reporte</Text>
          <View style={styles.options}>
            <OptionChip
              label="Usar actual"
              selected={locationMode === "current"}
              onPress={() => {
                setLocationMode("current");
                setLocationMessage(null);
              }}
            />
            <OptionChip
              label="Elegir en mapa"
              selected={locationMode === "map"}
              onPress={() => {
                setLocationMode("map");
                setLocationMessage(null);
              }}
            />
          </View>
          <Text style={styles.value}>
            {getLocationStatusText({
              isLocationLoading,
              locationMode,
              permissionDenied,
              selectedReportLocation,
              currentLocationValidationMessage,
            })}
          </Text>
          {locationMode === "current" && currentLocationValidationMessage ? (
            <Text style={styles.locationMessage}>{currentLocationValidationMessage}</Text>
          ) : locationMessage ? (
            <Text style={styles.locationMessage}>{locationMessage}</Text>
          ) : null}
          {locationMode === "map" ? (
            <View style={styles.mapPicker}>
              <TrailMap
                trail={trail}
                fitRoute
                showDetailsCard={false}
                showUserLocation={false}
                selectedCoordinate={selectedMapLocation?.coordinate ?? null}
                onSelectCoordinate={({ coordinate, routeProgressMeters }) => {
                  setSelectedMapLocation({
                    coordinate,
                    accuracyMeters: null,
                    routeProgressMeters,
                    source: "map",
                  });
                  setLocationMessage("Punto seleccionado sobre el sendero.");
                }}
                onSelectionRejected={(distanceToRouteMeters) => {
                  setLocationMessage(
                    distanceToRouteMeters === null
                      ? "Esta ruta no tiene trazado suficiente para elegir un punto en el mapa."
                      : "Elegi un punto sobre el sendero marcado para guardar coordenadas."
                  );
                }}
              />
            </View>
          ) : null}
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
          <Text style={styles.summaryText}>El punto del incidente se publica aproximado, con un margen de hasta 150 m y horario por hora. El texto libre queda disponible solo para vos y moderación. No ingreses datos de otras personas.</Text>
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
          {selectedReportLocation ? (
            <Text style={styles.locationSummary}>
              Coordenadas:{" "}
              {formatLocation(
                selectedReportLocation.coordinate[0],
                selectedReportLocation.coordinate[1],
                selectedReportLocation.routeProgressMeters
              )}
            </Text>
          ) : (
            <Text style={styles.locationSummary}>
              Elegi una ubicacion para poder enviar el reporte.
            </Text>
          )}
        </Card>

        <View style={styles.footer}>
          {submitError ? <Text style={styles.errorText}>{submitError}</Text> : null}
          <PrimaryButton
            label={isSubmitting ? "Enviando reporte" : "Enviar reporte"}
            icon="send-outline"
            onPress={submitReport}
            disabled={!canSubmit}
          />
        </View>
      </ScrollView>
    </AppScreen>
  );
}

function getLocationStatusText({
  isLocationLoading,
  locationMode,
  permissionDenied,
  selectedReportLocation,
  currentLocationValidationMessage,
}: {
  isLocationLoading: boolean;
  locationMode: LocationMode;
  permissionDenied: boolean;
  selectedReportLocation: SelectedReportLocation | null;
  currentLocationValidationMessage: string | null;
}) {
  if (selectedReportLocation) {
    return formatLocation(
      selectedReportLocation.coordinate[0],
      selectedReportLocation.coordinate[1],
      selectedReportLocation.routeProgressMeters
    );
  }

  if (locationMode === "map") return "Toca un punto sobre el sendero marcado.";
  if (currentLocationValidationMessage) return "Ubicacion actual fuera del sendero.";
  if (permissionDenied) return "GPS sin permiso. Podes elegir un punto en el mapa.";
  if (isLocationLoading) return "Buscando posicion GPS...";

  return "No pudimos obtener una posicion GPS precisa. Podes elegir en el mapa.";
}

function formatLocation(
  latitude: number,
  longitude: number,
  routeProgressMeters: number | null
) {
  const coordinate = `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;

  if (routeProgressMeters === null) return coordinate;

  return `${coordinate} - km ${(routeProgressMeters / 1000).toLocaleString("es-AR", {
    maximumFractionDigits: 1,
  })} de la ruta`;
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
    lineHeight: 20,
    marginTop: 12,
  },
  locationMessage: {
    color: colors.orange,
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 18,
    marginTop: 8,
  },
  mapPicker: {
    marginTop: 12,
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
  locationSummary: {
    color: colors.greenDark,
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 18,
    marginTop: 8,
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

import * as Battery from "expo-battery";
import { userMessage } from "../../services/userMessages";
import { getVerifiedOfflineMapByTrailId } from "../../services/offlineMaps";
import { ensureRouteSession, getActiveRouteSession } from "../../services/routeSession";
import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { getTrailById } from "../../services/trailRepository";
import { hasEmergencyContact } from "../../services/emergencyContact";
import { DepartureMessageRequiredError, getDepartureMessage } from "../../services/departureMessages";
import {
  Coordinate,
  formatDistance,
  getDistanceMeters,
  getRouteStart,
  parseRouteCoordinates,
  ROUTE_START_WARNING_METERS,
} from "../../services/geoUtils";
import { Trail } from "../../types";
import { NationalParkEntry } from "../components/NationalParkUI";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";
import { useDeviceLocation } from "../hooks/useDeviceLocation";

const getSimulatedStartLocation = (trail: Trail | null) => {
  if (!trail) return null;
  if (
    !trail.route_coordinates &&
    (trail.center_lat === null || trail.center_lng === null)
  ) {
    return null;
  }

  const fallbackCenter: Coordinate = [
    trail.center_lat ?? 0,
    trail.center_lng ?? 0,
  ];
  const route = parseRouteCoordinates(trail.route_coordinates);

  return getRouteStart(route, fallbackCenter);
};

const showMissingContactAlert = (trailId: number) => {
  Alert.alert(
    "Contacto de emergencia requerido",
    "Antes de iniciar una ruta tenes que guardar un contacto de emergencia. Así tendrás a quién llamar o enviar un SMS durante el recorrido. Guardarlo no envía ningún aviso.",
    [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Completar contacto",
        onPress: () =>
          router.push({
            pathname: "/contacto-seguridad",
            params: { id: String(trailId), returnTo: "trail-start" },
          }),
      },
    ]
  );
};

const showFarFromStartAlert = (
  trailId: number,
  routeStartDistance: number,
  beginRoute: () => void
) => {
  Alert.alert(
    "Estas lejos del inicio",
    `Estas a ${formatDistance(routeStartDistance)} del punto inicial. Te recomendamos acercarte al inicio real antes de comenzar.`,
    [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Ver mapa",
        onPress: () =>
          router.push({
            pathname: "/alerta-ruta",
            params: {
              id: String(trailId),
              distance: String(Math.round(routeStartDistance)),
              reason: "start",
            },
          }),
      },
      { text: "Comenzar igual", style: "destructive", onPress: beginRoute },
    ]
  );
};

const getContactStatusText = (
  isContactLoading: boolean,
  hasSafetyContact: boolean
) => {
  if (isContactLoading) return "Verificando contacto guardado...";
  if (hasSafetyContact) {
    return "Contacto guardado. Podés usarlo para preparar un SMS o una llamada.";
  }
  return "Completa un contacto de emergencia para poder iniciar y usar SOS.";
};

const getLocationStatusText = ({
  permissionDenied,
  isTestingLocation,
  isLocationLoading,
  error,
  routeStartDistance,
  isFarFromStart,
}: {
  permissionDenied: boolean;
  isTestingLocation: boolean;
  isLocationLoading: boolean;
  error: string | null;
  routeStartDistance: number | null;
  isFarFromStart: boolean;
}) => {
  if (permissionDenied) {
    return "Activa la ubicacion para validar si estas cerca del inicio.";
  }
  if (isTestingLocation) {
    return "Modo prueba activo: se simula que estás en el inicio de la ruta.";
  }
  if (isLocationLoading) return "Buscando tu ubicacion actual...";
  if (error) return error;
  if (routeStartDistance === null) {
    return "Estamos validando tu distancia al punto inicial.";
  }
  if (isFarFromStart) {
    return `Estas a ${formatDistance(routeStartDistance)} del inicio de la ruta.`;
  }
  return `Estas cerca del inicio: ${formatDistance(routeStartDistance)} aprox.`;
};

export default function Screen05TrailStart() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id) || 1;
  const [trail, setTrail] = useState<Trail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasSafetyContact, setHasSafetyContact] = useState(false);
  const [isContactLoading, setIsContactLoading] = useState(true);
  const [waterReady, setWaterReady] = useState(false);
  const [planAgreed, setPlanAgreed] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [battery, setBattery] = useState<number | null>(null);
  const [departureReady, setDepartureReady] = useState(false);
  const [hasActiveRoute, setHasActiveRoute] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    getTrailById(trailId)
      .then((data) => {
        setTrail(data);
        setError(null);
      })
      .catch(() => {
        setError("No pudimos validar el inicio de la ruta.");
      });
  }, [trailId]);

  useFocusEffect(
    useCallback(() => {
      let isActive = true;

      void Promise.all([
        getVerifiedOfflineMapByTrailId(trailId).catch(() => null),
        Battery.getBatteryLevelAsync().catch(() => -1),
      ]).then(([map, level]) => {
        if (isActive) { setMapReady(!!map); setBattery(level >= 0 ? Math.round(level * 100) : null); }
      });
      setIsContactLoading(true);
      Promise.all([hasEmergencyContact(), getDepartureMessage(trailId), getActiveRouteSession()])
        .then(([exists, message, activeRoute]) => {
          if (isActive) { setHasSafetyContact(exists); setDepartureReady(!!message); setHasActiveRoute(!!activeRoute); }
        })
        .catch(() => { if (isActive) { setHasSafetyContact(false); setDepartureReady(false); setHasActiveRoute(false); } })
        .finally(() => {
          if (isActive) setIsContactLoading(false);
        });

      return () => {
        isActive = false;
      };
    }, [trailId])
  );

  const simulatedStartLocation = useMemo(
    () => getSimulatedStartLocation(trail),
    [trail]
  );
  const {
    location,
    isLoading: isLocationLoading,
    permissionDenied,
    isTestingLocation,
  } = useDeviceLocation(true, simulatedStartLocation);

  const routeStartDistance = useMemo(() => {
    if (!simulatedStartLocation || !location) return null;

    return getDistanceMeters(location.coordinate, simulatedStartLocation);
  }, [location, simulatedStartLocation]);

  const isFarFromStart =
    routeStartDistance !== null &&
    routeStartDistance > ROUTE_START_WARNING_METERS;
  const contactStatusText = getContactStatusText(
    isContactLoading,
    hasSafetyContact
  );
  const locationStatusText = getLocationStatusText({
    permissionDenied,
    isTestingLocation,
    isLocationLoading,
    error,
    routeStartDistance,
    isFarFromStart,
  });
  const checklist = [
    { text: "Tengo agua y equipo suficiente", ready: waterReady, toggle: () => setWaterReady(!waterReady) },
    { text: mapReady ? "Mapa disponible sin conexión" : "Descargá el mapa antes de salir", ready: mapReady },
    { text: battery === null ? "Batería: no disponible" : `Batería: ${battery}%`, ready: battery !== null && battery >= 60 },
    { text: "Acordé ruta y hora de regreso con mi contacto", ready: planAgreed, toggle: () => setPlanAgreed(!planAgreed) },
    // A test run never requires, sends or consumes a real departure plan.
    isTestingLocation
      ? { text: "Modo prueba: no se envía plan de salida", ready: true }
      : { text: departureReady ? "Envío del plan de esta salida registrado" : "Falta enviar el plan por SMS (obligatorio)", ready: departureReady },
  ];

  const beginRoute = async () => {
    if (starting) return;
    if (trail?.provenance?.mapping?.navigation_ready === false) {
      Alert.alert("Consultá el recorrido antes de salir", "Revisá los accesos y las indicaciones con la administración del sendero antes de iniciar esta ruta.");
      return;
    }
    setStarting(true);
    try {
      const existing = await getActiveRouteSession();
      if (existing) {
        router.push({ pathname: existing.state === "paused" ? "/descanso" : "/route-map", params: {
          id: String(existing.trail_id), active: "1", startedAt: String(existing.started_at),
        } });
        return;
      }
      const start = Date.now();
      await ensureRouteSession(trailId, start, isTestingLocation);
      router.push({ pathname: "/route-map", params: { active: "1", id: String(trailId), startedAt: String(start) } });
    } catch (error) {
      if (error instanceof DepartureMessageRequiredError) { setDepartureReady(false); router.push({ pathname: "/plan-salida", params: { id: String(trailId) } }); }
      else Alert.alert("No se pudo iniciar", userMessage(error, "Intentá nuevamente."));
    } finally { setStarting(false); }
  };

  const handleStart = () => {
    if (isContactLoading || starting) return;
    if (hasActiveRoute) { void beginRoute(); return; }

    if (!hasSafetyContact) {
      showMissingContactAlert(trailId);
      return;
    }

    if (!departureReady && !isTestingLocation) {
      router.push({ pathname: "/plan-salida", params: { id: String(trailId) } });
      return;
    }

    if (isFarFromStart && routeStartDistance !== null) {
      showFarFromStartAlert(trailId, routeStartDistance, beginRoute);
      return;
    }

    beginRoute();
  };

  return (
    <ScreenShell>
      <TopBar title="Antes de salir" onBack={() => router.back()} />

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: Math.max(28, insets.bottom + 24) },
        ]}
      >
        <View style={styles.statusCircle}>
          <Ionicons name="clipboard-outline" size={48} color={colors.green} />
        </View>
        <Text style={styles.title}>Revisá antes de comenzar</Text>
        <Text style={styles.subtitle}>
          Confirma los ultimos puntos de seguridad y empieza el recorrido.
        </Text>

        {trail?.national_park && <NationalParkEntry park={trail.national_park} trailId={trail.id} trailName={trail.name} beforeStart />}
        <InfoCard style={styles.card}>
          <Text style={styles.cardTitle}>Checklist rapido</Text>
          {checklist.map((item) => (
            <Pressable key={item.text} style={styles.row} onPress={item.toggle} disabled={!item.toggle}
              accessibilityRole={item.toggle ? "checkbox" : "text"} accessibilityState={{ checked: item.ready }}>
              <Ionicons name={item.ready ? "checkmark-circle" : "ellipse-outline"} size={22} color={item.ready ? colors.green : colors.muted} />
              <Text style={styles.rowText}>{item.text}</Text>
            </Pressable>
          ))}
          <Text style={styles.warningBody}>Las casillas de equipo y acuerdo las confirmás vos. Guardar un contacto o abrir Mensajes no confirma que haya recibido tu aviso.</Text>
          {!mapReady && <PrimaryButton label="Revisar descarga offline" tone="secondary" onPress={() => router.push({ pathname: "/trail-detail", params: { id: String(trailId) } })} />}
        </InfoCard>

        <InfoCard style={styles.warningCard} icon="alert-circle-outline" iconColor={colors.danger}>
          <Text style={styles.warningTitle}>Recordatorio</Text>
          <Text style={styles.warningBody}>
            El seguimiento GPS de esta versión funciona con la app abierta en primer plano. Bloquear el teléfono o cerrarla puede interrumpir el registro; no completa esos tramos por estimación.
          </Text>
        </InfoCard>

        {isTestingLocation ? (
          <InfoCard style={styles.statusCard} icon="flask-outline">
            <Text style={styles.warningTitle}>Modo prueba: no se envía plan de salida</Text>
            <Text style={styles.warningBody}>
              El recorrido es simulado: no se envía SMS ni avisos a tu contacto.
            </Text>
          </InfoCard>
        ) : (
          <PrimaryButton label={departureReady ? "Revisar plan de regreso" : "Enviar plan de regreso por SMS"} tone="secondary" onPress={() => router.push({ pathname: "/plan-salida", params: { id: String(trailId) } })} />
        )}

        <InfoCard style={hasSafetyContact ? styles.statusCard : styles.warningCard}
          icon={hasSafetyContact ? "shield-checkmark-outline" : "shield-outline"}
          iconColor={hasSafetyContact ? colors.green : colors.danger}>
          <Text style={styles.warningTitle}>Contacto de emergencia</Text>
          <Text style={styles.warningBody}>{contactStatusText}</Text>
        </InfoCard>

        <InfoCard style={isFarFromStart ? styles.warningCard : styles.statusCard}
          icon={isFarFromStart ? "warning-outline" : "navigate-outline"}
          iconColor={isFarFromStart ? colors.danger : colors.green}>
          <Text style={styles.warningTitle}>Ubicacion de inicio</Text>
          <Text style={styles.warningBody}>{locationStatusText}</Text>
        </InfoCard>

        <View style={styles.footer}>
          <PrimaryButton
            label={
              starting ? "Iniciando..." : isContactLoading
                ? "Verificando salida"
                : hasActiveRoute ? "Continuar recorrido"
                : hasSafetyContact
                  ? isTestingLocation ? "Comenzar prueba" : departureReady ? "Comenzar ahora" : "Enviar plan antes de salir"
                  : "Completar contacto"
            }
            disabled={isContactLoading || starting}
            icon={hasActiveRoute || departureReady || (isTestingLocation && hasSafetyContact) ? "play-outline" : hasSafetyContact ? "chatbubble-outline" : "shield-checkmark-outline"}
            onPress={handleStart}
          />
        </View>
      </ScrollView>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  scroll: {
    alignItems: "center",
    flexGrow: 1,
  },
  statusCircle: {
    alignItems: "center",
    backgroundColor: colors.mint,
    borderRadius: 54,
    height: 108,
    justifyContent: "center",
    marginTop: 14,
    width: 108,
  },
  title: {
    color: colors.ink,
    fontSize: 31,
    fontWeight: "900",
    lineHeight: 37,
    marginTop: 22,
    textAlign: "center",
  },
  subtitle: {
    color: colors.muted,
    fontSize: 16,
    lineHeight: 23,
    marginTop: 10,
    textAlign: "center",
  },
  card: {
    alignSelf: "stretch",
    marginTop: 26,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
    marginBottom: 12,
  },
  row: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: 1,
    flexDirection: "row",
    gap: 10,
    paddingVertical: 13,
  },
  rowText: {
    flex: 1,
    color: colors.ink,
    fontSize: 15,
    fontWeight: "700",
  },
  warningCard: {
    alignSelf: "stretch",
    backgroundColor: "#FFF4F2",
    marginTop: 12,
  },
  statusCard: {
    alignSelf: "stretch",
    marginTop: 12,
  },
  warningTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  warningBody: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 3,
  },
  footer: {
    alignSelf: "stretch",
    marginTop: 18,
  },
});

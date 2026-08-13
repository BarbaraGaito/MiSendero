import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useMemo, useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { getTrailById } from "../../services/api";
import {
  Coordinate,
  formatDistance,
  getDistanceMeters,
  getRouteStart,
  parseRouteCoordinates,
  ROUTE_START_WARNING_METERS,
} from "../../services/geoUtils";
import { Trail } from "../../types";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";
import { useDeviceLocation } from "../hooks/useDeviceLocation";

const checklist = [
  "Agua suficiente",
  "Mapa descargado",
  "Bateria mayor al 60%",
  "Aviso de salida enviado",
];

export default function Screen05TrailStart() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id) || 1;
  const [trail, setTrail] = useState<Trail | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const simulatedStartLocation = useMemo(() => {
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
  }, [trail]);
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

  const beginRoute = () => {
    router.push({
      pathname: "/route-map",
      params: { active: "1", id: String(trailId) },
    });
  };

  const handleStart = () => {
    if (isFarFromStart && routeStartDistance !== null) {
      Alert.alert(
        "Estas lejos del inicio",
        `Estas a ${formatDistance(routeStartDistance)} del punto inicial. Te recomendamos acercarte al inicio real antes de comenzar.`,
        [
          { text: "Cancelar", style: "cancel" },
          { text: "Comenzar igual", style: "destructive", onPress: beginRoute },
        ]
      );
      return;
    }

    beginRoute();
  };

  return (
    <ScreenShell>
      <TopBar title="Antes de salir" onBack={() => router.back()} />

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        <View style={styles.statusCircle}>
          <Ionicons name="checkmark" size={48} color={colors.green} />
        </View>
        <Text style={styles.title}>Todo listo para comenzar</Text>
        <Text style={styles.subtitle}>
          Confirma los ultimos puntos de seguridad y empieza el recorrido.
        </Text>

        <InfoCard style={styles.card}>
          <Text style={styles.cardTitle}>Checklist rapido</Text>
          {checklist.map((item) => (
            <View key={item} style={styles.row}>
              <Ionicons name="checkmark-circle" size={22} color={colors.green} />
              <Text style={styles.rowText}>{item}</Text>
            </View>
          ))}
        </InfoCard>

        <InfoCard style={styles.warning}>
          <Ionicons name="alert-circle-outline" size={24} color={colors.danger} />
          <View style={styles.warningText}>
            <Text style={styles.warningTitle}>Recordatorio</Text>
            <Text style={styles.warningBody}>
              Si cambia el clima o baja la luz, vuelve al punto de inicio.
            </Text>
          </View>
        </InfoCard>

        <InfoCard style={isFarFromStart ? styles.startWarning : styles.locationCard}>
          <Ionicons
            name={isFarFromStart ? "warning-outline" : "navigate-outline"}
            size={24}
            color={isFarFromStart ? colors.danger : colors.green}
          />
          <View style={styles.warningText}>
            <Text style={styles.warningTitle}>Ubicacion de inicio</Text>
            <Text style={styles.warningBody}>
              {permissionDenied
                ? "Activa la ubicacion para validar si estas cerca del inicio."
                : isTestingLocation
                  ? "Modo testing activo: se simula que estas en el inicio de la ruta."
                : isLocationLoading
                  ? "Buscando tu ubicacion actual..."
                  : error
                    ? error
                    : routeStartDistance === null
                      ? "Estamos validando tu distancia al punto inicial."
                      : isFarFromStart
                        ? `Estas a ${formatDistance(routeStartDistance)} del inicio de la ruta.`
                        : `Estas cerca del inicio: ${formatDistance(routeStartDistance)} aprox.`}
            </Text>
          </View>
        </InfoCard>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: Math.max(20, insets.bottom + 14) }]}>
        <PrimaryButton
          label="Comenzar ahora"
          icon="play-outline"
          onPress={handleStart}
        />
      </View>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  scroll: {
    alignItems: "center",
    paddingBottom: 142,
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
    color: colors.ink,
    fontSize: 15,
    fontWeight: "700",
  },
  warning: {
    alignItems: "center",
    alignSelf: "stretch",
    backgroundColor: "#FFF4F2",
    flexDirection: "row",
    gap: 12,
    marginTop: 16,
  },
  locationCard: {
    alignItems: "center",
    alignSelf: "stretch",
    backgroundColor: colors.white,
    flexDirection: "row",
    gap: 12,
    marginTop: 16,
  },
  startWarning: {
    alignItems: "center",
    alignSelf: "stretch",
    backgroundColor: "#FFF4F2",
    flexDirection: "row",
    gap: 12,
    marginTop: 16,
  },
  warningText: {
    flex: 1,
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
    backgroundColor: colors.softer,
    bottom: 0,
    left: 0,
    padding: 22,
    paddingBottom: 28,
    position: "absolute",
    right: 0,
  },
});

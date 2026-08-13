import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useMemo, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { getTrailById } from "../../services/api";
import {
  Coordinate,
  formatDistance,
  getDistanceMeters,
  getRouteStart,
  parseRouteCoordinates,
} from "../../services/geoUtils";
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

export default function AlertRouteScreen() {
  const { distance, id, reason } = useLocalSearchParams<{
    distance?: string;
    id?: string;
    reason?: string;
  }>();
  const trailId = Number(id) || 1;
  const isStartWarning = reason === "start";
  const [trail, setTrail] = useState<Trail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTrailById(trailId)
      .then((data) => {
        setTrail(data);
        setError(null);
      })
      .catch(() => {
        setError("No pudimos cargar el mapa de la ruta.");
      });
  }, [trailId]);

  const route = useMemo(
    () => parseRouteCoordinates(trail?.route_coordinates),
    [trail?.route_coordinates]
  );
  const routeStart = useMemo(() => {
    if (!trail) return null;

    const fallbackCenter: Coordinate = [
      trail.center_lat ?? 0,
      trail.center_lng ?? 0,
    ];

    return getRouteStart(route, fallbackCenter);
  }, [route, trail]);
  const { location, permissionDenied, isTestingLocation } = useDeviceLocation(
    true,
    routeStart
  );
  const startDistanceMeters = useMemo(() => {
    if (!location || !routeStart) return null;
    return getDistanceMeters(location.coordinate, routeStart);
  }, [location, routeStart]);
  const paramDistanceMeters = Number(distance);
  const distanceMeters =
    startDistanceMeters ??
    (Number.isFinite(paramDistanceMeters) ? paramDistanceMeters : null);
  const distanceText =
    distanceMeters !== null ? formatDistance(distanceMeters) : "distancia no disponible";
  const title = isStartWarning ? "Estas lejos del inicio" : "Te alejaste de la ruta";
  const subtitle = isStartWarning
    ? `Estas a ${distanceText} del punto de inicio de la ruta.`
    : `Estas a ${distanceText} del sendero marcado. Revisa tu posicion antes de continuar.`;

  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Alerta de ruta"
        title={title}
        subtitle={subtitle}
      />

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {error ? <Text style={styles.statusText}>{error}</Text> : null}

        <TrailMap trail={trail} fitRoute showDetailsCard={false} />

        <Card tone="orange">
          <Text style={styles.cardTitle}>
            {isStartWarning ? "Punto de inicio" : "Ruta marcada"}
          </Text>
          <Text style={styles.cardText}>
            {permissionDenied
              ? "Activa la ubicacion para calcular la distancia real."
              : isTestingLocation
                ? "Modo testing activo: se simula que estas en el inicio."
                : isStartWarning
                  ? `Acercate al punto inicial antes de comenzar. Distancia actual: ${distanceText}.`
                  : `Vuelve hacia el tramo principal para retomar el circuito seguro. Distancia actual: ${distanceText}.`}
          </Text>
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Que queres hacer?</Text>
          <Text style={styles.cardText}>
            Puedes volver al mapa, iniciar igualmente o reportar un problema del
            terreno.
          </Text>
        </Card>

        <View style={styles.actions}>
          <PrimaryButton
            label={isStartWarning ? "Volver al inicio" : "Volver a la ruta"}
            onPress={() =>
              router.push(
                isStartWarning
                  ? {
                      pathname: "/route-map",
                      params: { id: String(trailId) },
                    }
                  : {
                      pathname: "/route-map",
                      params: { active: "1", id: String(trailId) },
                    }
              )
            }
          />
          {isStartWarning ? (
            <PrimaryButton
              label="Comenzar igual"
              onPress={() =>
                router.push({
                  pathname: "/route-map",
                  params: { active: "1", id: String(trailId) },
                })
              }
              tone="secondary"
            />
          ) : (
            <PrimaryButton label="Estoy bien" href="/recorrido-finalizado" tone="secondary" />
          )}
          <PrimaryButton label="Reportar problema" href="/reportar-terreno" tone="danger" />
        </View>
      </ScrollView>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    paddingBottom: 24,
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 12,
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
  actions: {
    gap: 10,
    marginTop: 4,
  },
});

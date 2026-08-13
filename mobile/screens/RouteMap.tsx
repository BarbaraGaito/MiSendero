import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { getTrailById } from "../../services/api";
import { Trail } from "../../types";
import { TrailMap } from "../components/TrailMap";
import { useDeviceLocation } from "../hooks/useDeviceLocation";
import {
  Coordinate,
  formatDistance,
  getDistanceToRouteMeters,
  getRouteStart,
  parseRouteCoordinates,
  ROUTE_DEVIATION_WARNING_METERS,
} from "../../services/geoUtils";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";

export default function Screen04RouteMap() {
  const insets = useSafeAreaInsets();
  const { active, id } = useLocalSearchParams<{ active?: string; id?: string }>();
  const trailId = Number(id) || 1;
  const isActiveRoute = active === "1";
  const [trail, setTrail] = useState<Trail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setIsLoading(true);

    getTrailById(trailId)
      .then((data) => {
        setTrail(data);
        setError(null);
      })
      .catch(() => {
        setError("No pudimos cargar el mapa de este sendero.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [trailId]);

  const routePoints = useMemo(
    () => parseRouteCoordinates(trail?.route_coordinates),
    [trail?.route_coordinates]
  );
  const simulatedStartLocation = useMemo(() => {
    if (!trail) return null;
    if (
      routePoints.length === 0 &&
      (trail.center_lat === null || trail.center_lng === null)
    ) {
      return null;
    }

    const fallbackCenter: Coordinate = [
      trail.center_lat ?? 0,
      trail.center_lng ?? 0,
    ];

    return getRouteStart(routePoints, fallbackCenter);
  }, [routePoints, trail]);
  const {
    location,
    permissionDenied: locationPermissionDenied,
    isTestingLocation,
  } = useDeviceLocation(isActiveRoute, simulatedStartLocation);
  const routeDeviationMeters = useMemo(() => {
    if (!isActiveRoute || !location || routePoints.length === 0) return null;
    return getDistanceToRouteMeters(location.coordinate, routePoints);
  }, [isActiveRoute, location, routePoints]);
  const isOffRoute =
    routeDeviationMeters !== null &&
    routeDeviationMeters > ROUTE_DEVIATION_WARNING_METERS;

  if (isActiveRoute) {
    return (
      <SafeAreaView edges={["top", "bottom"]} style={styles.activeShell}>
        <TrailMap
          trail={trail}
          fitRoute
          immersive
          initialPerspective
          showDetailsCard={false}
        />

        <View style={styles.activeHeader}>
          <Pressable onPress={() => router.back()} style={styles.activeIconButton}>
            <Ionicons name="chevron-back" size={22} color={colors.ink} />
          </Pressable>
          <View style={styles.activeTitleBox}>
            <Text style={styles.activeEyebrow}>Ruta en curso</Text>
            <Text numberOfLines={1} style={styles.activeTitle}>
              {trail?.name || "Mapa del recorrido"}
            </Text>
          </View>
        </View>

        {isLoading || error ? (
          <View style={styles.activeStatus}>
            <Text style={styles.statusText}>
              {isLoading ? "Cargando mapa..." : error}
            </Text>
          </View>
        ) : null}

        {!isLoading && !error && locationPermissionDenied ? (
          <View style={styles.activeStatus}>
            <Text style={styles.statusText}>
              Activa la ubicacion para detectar desvíos de ruta.
            </Text>
          </View>
        ) : null}

        {isOffRoute && routeDeviationMeters !== null ? (
          <View style={styles.deviationBanner}>
            <Ionicons name="warning-outline" size={20} color={colors.danger} />
            <View style={styles.deviationText}>
              <Text style={styles.deviationTitle}>Te alejaste de la ruta</Text>
              <Text style={styles.deviationBody}>
                Estas a {formatDistance(routeDeviationMeters)} del sendero marcado.
              </Text>
            </View>
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/alerta-ruta",
                  params: {
                    id: String(trailId),
                    distance: String(Math.round(routeDeviationMeters)),
                  },
                })
              }
              style={styles.deviationButton}
            >
              <Text style={styles.deviationButtonText}>Ver</Text>
            </Pressable>
          </View>
        ) : null}

        {isTestingLocation ? (
          <View style={styles.testingBanner}>
            <Ionicons name="flask-outline" size={17} color={colors.greenDark} />
            <Text style={styles.testingBannerText}>
              Modo testing: ubicacion simulada en el inicio
            </Text>
          </View>
        ) : null}

        <View style={[styles.activeFooter, { paddingBottom: Math.max(16, insets.bottom + 10) }]}>
          <Pressable
            onPress={() => router.push("/descanso")}
            style={styles.activeAction}
          >
            <Ionicons name="pause-circle-outline" size={20} color={colors.greenDark} />
            <Text style={styles.activeActionText}>Descanso</Text>
          </Pressable>
          <Pressable
            onPress={() => router.push("/reportar-terreno")}
            style={styles.activeAction}
          >
            <Ionicons name="warning-outline" size={20} color={colors.greenDark} />
            <Text style={styles.activeActionText}>Terreno</Text>
          </Pressable>
          <Pressable
            onPress={() => router.push("/confirmar-sos")}
            style={[styles.activeAction, styles.activeDangerAction]}
          >
            <Ionicons name="alert-circle-outline" size={20} color={colors.white} />
            <Text style={styles.activeDangerText}>SOS</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <ScreenShell>
      <TopBar title="Mapa del recorrido" onBack={() => router.back()} />

      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: Math.max(24, insets.bottom + 18) },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {isLoading ? <Text style={styles.statusText}>Cargando mapa...</Text> : null}
        {error ? <Text style={styles.statusText}>{error}</Text> : null}

        <TrailMap trail={trail} />

        <InfoCard style={styles.progressCard}>
          <View style={styles.progressText}>
            <Text style={styles.cardTitle}>Ruta lista</Text>
            <Text style={styles.cardText}>
              Usa Terreno para ver curvas de nivel o 3D para revisar la ruta con relieve.
            </Text>
          </View>
          <View style={styles.downloadBadge}>
            <Ionicons name="map-outline" size={24} color={colors.green} />
          </View>
        </InfoCard>

        <View style={styles.footer}>
          <PrimaryButton
            label="Iniciar recorrido"
            icon="navigate-outline"
            onPress={() =>
              router.push({
                pathname: "/trail-start",
                params: { id: String(trailId) },
              })
            }
          />
          <PrimaryButton
            label="Tomar descanso"
            icon="pause-circle-outline"
            href="/descanso"
            tone="secondary"
          />
          <PrimaryButton
            label="Reportar terreno"
            icon="warning-outline"
            href="/reportar-terreno"
            tone="secondary"
          />
          <PrimaryButton
            label="Alerta de ruta"
            icon="trail-sign-outline"
            href="/alerta-ruta"
            tone="secondary"
          />
          <PrimaryButton
            label="SOS"
            icon="alert-circle-outline"
            href="/confirmar-sos"
            tone="danger"
          />
        </View>
      </ScrollView>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  activeShell: {
    backgroundColor: colors.softer,
    flex: 1,
  },
  activeHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    left: 14,
    position: "absolute",
    right: 14,
    top: 14,
    zIndex: 20,
  },
  activeIconButton: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.96)",
    borderRadius: 18,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  activeTitleBox: {
    backgroundColor: "rgba(255,255,255,0.96)",
    borderRadius: 18,
    flex: 1,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  activeEyebrow: {
    color: colors.green,
    fontSize: 11,
    fontWeight: "900",
  },
  activeTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
    marginTop: 1,
  },
  activeStatus: {
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 16,
    left: 14,
    paddingHorizontal: 12,
    paddingVertical: 9,
    position: "absolute",
    right: 14,
    top: 72,
    zIndex: 20,
  },
  deviationBanner: {
    alignItems: "center",
    backgroundColor: "rgba(255,244,242,0.97)",
    borderColor: "rgba(216,76,63,0.24)",
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    left: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    position: "absolute",
    right: 14,
    top: 76,
    zIndex: 21,
  },
  deviationText: {
    flex: 1,
  },
  deviationTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  deviationBody: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    marginTop: 2,
  },
  deviationButton: {
    backgroundColor: colors.danger,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  deviationButtonText: {
    color: colors.white,
    fontSize: 12,
    fontWeight: "900",
  },
  testingBanner: {
    alignItems: "center",
    backgroundColor: "rgba(223,243,231,0.97)",
    borderColor: "rgba(13,122,69,0.24)",
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    left: 14,
    paddingHorizontal: 12,
    paddingVertical: 9,
    position: "absolute",
    right: 14,
    top: 136,
    zIndex: 21,
  },
  testingBannerText: {
    color: colors.greenDark,
    flex: 1,
    fontSize: 12,
    fontWeight: "900",
  },
  activeFooter: {
    backgroundColor: "rgba(246,250,247,0.96)",
    borderTopColor: colors.line,
    borderTopWidth: 1,
    bottom: 0,
    flexDirection: "row",
    gap: 10,
    left: 0,
    padding: 14,
    position: "absolute",
    right: 0,
    zIndex: 20,
  },
  activeAction: {
    alignItems: "center",
    backgroundColor: colors.primarySoft,
    borderRadius: 18,
    flex: 1,
    flexDirection: "row",
    gap: 7,
    justifyContent: "center",
    minHeight: 48,
  },
  activeDangerAction: {
    backgroundColor: colors.danger,
  },
  activeActionText: {
    color: colors.greenDark,
    fontSize: 13,
    fontWeight: "900",
  },
  activeDangerText: {
    color: colors.white,
    fontSize: 13,
    fontWeight: "900",
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 10,
  },
  scrollContent: {
    flexGrow: 1,
  },
  progressCard: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    marginBottom: 16,
    marginTop: 2,
  },
  progressText: {
    flex: 1,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 4,
  },
  downloadBadge: {
    alignItems: "center",
    backgroundColor: colors.soft,
    borderRadius: 20,
    height: 48,
    justifyContent: "center",
    width: 48,
  },
  footer: {
    gap: 10,
    paddingTop: 6,
  },
});

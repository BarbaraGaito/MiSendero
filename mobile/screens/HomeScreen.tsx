import { StatusBar } from "expo-status-bar";
import React, { useEffect, useState } from "react";
import {
  ImageBackground,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { getProfile, getTrails } from "../../services/api";
import { getAuthSession } from "../../services/authSession";
import { Profile, Trail } from "../../types";
import { BottomNav, trailImages } from "../components/MiSenderoUI";
import {
  ExperienceProfile,
  getExperienceProfile,
  getRecommendedTrailForProfile,
} from "../../services/experienceProfile";

type TagProps = {
  label: string;
  tone: "green" | "orange";
};

type RouteMetricProps = {
  icon: string;
  label: string;
  accent?: boolean;
};

export default function HomeScreen() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [experienceProfile, setExperienceProfile] =
    useState<ExperienceProfile | null>(null);
  const [recommendedTrail, setRecommendedTrail] = useState<Trail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadHome = async () => {
      try {
        const session = await getAuthSession();

        if (!session) {
          router.replace("/");
          return;
        }

        const [profileData, trails, experience] = await Promise.all([
          getProfile(session.token),
          getTrails(),
          getExperienceProfile(),
        ]);

        setProfile(profileData);
        setExperienceProfile(experience);
        setRecommendedTrail(getRecommendedTrailForProfile(trails, experience));
      } catch (loadError) {
        setError("No pudimos actualizar tu inicio.");
      }
    };

    loadHome();
  }, []);

  const userName = profile?.user?.name || "viajera";
  const distance = recommendedTrail?.distance_km
    ? `${recommendedTrail.distance_km} km`
    : "Distancia a confirmar";
  const duration = recommendedTrail?.duration || "Duracion a confirmar";
  const difficulty = recommendedTrail?.difficulty || "A confirmar";
  const canRecommend = experienceProfile?.completed;

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <StatusBar style="dark" />
      <View style={styles.screen}>
        <View style={styles.content}>
          <View style={styles.hero}>
            <Text style={styles.title}>Buen dia, {userName}</Text>
            <Text style={styles.subtitle}>
              Prepara tu proxima salida y lleva la ruta sin depender de la senal.
            </Text>
          </View>

          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Recomendada para vos</Text>
            <Text
              onPress={() => router.push("/explorar-rutas")}
              style={styles.sectionAction}
            >
              Ver rutas
            </Text>
          </View>

          {error ? <Text style={styles.statusText}>{error}</Text> : null}

          {!canRecommend ? (
            <View style={styles.emptyCard}>
              <Text style={styles.routeName}>Completa tu perfil de experiencia</Text>
              <Text style={styles.routeLocation}>
                Responde unas preguntas rapidas para recomendarte rutas acordes a tu nivel.
              </Text>
              <Pressable
                onPress={() => router.push("/onboarding-experiencia")}
                style={styles.inlineButton}
              >
                <Text style={styles.inlineButtonText}>Completar ahora</Text>
              </Pressable>
            </View>
          ) : recommendedTrail ? (
            <Pressable
              style={styles.routeCard}
              onPress={() =>
                router.push({
                  pathname: "/trail-detail",
                  params: { id: String(recommendedTrail.id) },
                })
              }
            >
              <ImageBackground
                source={{ uri: recommendedTrail.image_url || trailImages.mountain }}
                imageStyle={styles.mapImage}
                style={styles.mapPreview}
              >
                <View style={styles.mapShade} />
                <View style={styles.tags}>
                  <Tag label={difficulty} tone="orange" />
                </View>
                <Text style={styles.mapTitle}>{recommendedTrail.name}</Text>
              </ImageBackground>

              <View style={styles.routeDetails}>
                <Text style={styles.routeName}>{recommendedTrail.name}</Text>
                <Text style={styles.routeLocation}>{recommendedTrail.location}</Text>

                <View style={styles.metrics}>
                  <RouteMetric icon="M" label={distance} />
                  <RouteMetric icon="T" label={duration} />
                  <RouteMetric icon="A" label={difficulty} accent />
                </View>
              </View>
            </Pressable>
          ) : (
            <View style={styles.emptyCard}>
              <Text style={styles.routeName}>No hay rutas disponibles por ahora</Text>
              <Text style={styles.routeLocation}>Cuando agregues senderos, apareceran aca.</Text>
            </View>
          )}

          {canRecommend && recommendedTrail ? (
            <Pressable
              style={styles.primaryButton}
              onPress={() =>
                router.push({
                  pathname: "/trail-detail",
                  params: { id: String(recommendedTrail.id) },
                })
              }
            >
              <Text style={styles.primaryButtonText}>Ver detalle de la ruta</Text>
            </Pressable>
          ) : null}
        </View>

        <BottomNav active="inicio" />
      </View>
    </SafeAreaView>
  );
}

const Tag = ({ label, tone }: TagProps) => (
  <View style={styles.tag}>
    <View style={[styles.tagDot, tone === "orange" ? styles.orangeDot : styles.greenDot]} />
    <Text style={[styles.tagText, tone === "orange" ? styles.orangeText : styles.greenText]}>
      {label}
    </Text>
  </View>
);

const RouteMetric = ({ icon, label, accent }: RouteMetricProps) => (
  <View style={styles.metric}>
    <View style={[styles.metricIcon, accent && styles.metricIconAccent]}>
      <Text style={[styles.metricIconText, accent && styles.metricIconTextAccent]}>{icon}</Text>
    </View>
    <Text style={[styles.metricLabel, accent && styles.metricLabelAccent]}>{label}</Text>
  </View>
);

const colors = {
  ink: "#131D17",
  muted: "#718178",
  border: "#E0E7E2",
  primary: "#166343",
  primarySoft: "#E5F2EB",
  orange: "#D6801B",
  surface: "#FFFFFF",
  page: "#F7FAF6",
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.page,
  },
  screen: {
    flex: 1,
    backgroundColor: colors.page,
  },
  content: {
    flex: 1,
    gap: 20,
    paddingBottom: 16,
    paddingHorizontal: 24,
    paddingTop: 18,
  },
  hero: {
    gap: 12,
  },
  title: {
    color: colors.ink,
    fontSize: 32,
    fontWeight: "800",
    lineHeight: 38,
  },
  subtitle: {
    color: colors.muted,
    fontSize: 15,
    fontWeight: "500",
    lineHeight: 22,
  },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "600",
    lineHeight: 25,
  },
  sectionAction: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 18,
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
  },
  routeCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 24,
    borderWidth: 1,
    elevation: 3,
    overflow: "hidden",
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.05,
    shadowRadius: 24,
  },
  emptyCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 24,
    borderWidth: 1,
    gap: 8,
    padding: 18,
  },
  inlineButton: {
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: colors.primary,
    borderRadius: 16,
    marginTop: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  inlineButtonText: {
    color: colors.surface,
    fontSize: 13,
    fontWeight: "800",
  },
  mapPreview: {
    height: 220,
    justifyContent: "space-between",
    overflow: "hidden",
    padding: 16,
  },
  mapImage: {
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  mapShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.1)",
  },
  tags: {
    flexDirection: "row",
    gap: 8,
    zIndex: 1,
  },
  tag: {
    alignItems: "center",
    backgroundColor: "rgba(255, 255, 255, 0.9)",
    borderColor: "rgba(255, 255, 255, 0.15)",
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  tagDot: {
    borderRadius: 999,
    height: 6,
    width: 6,
  },
  greenDot: {
    backgroundColor: colors.primary,
  },
  orangeDot: {
    backgroundColor: colors.orange,
  },
  tagText: {
    fontSize: 12,
    fontWeight: "700",
  },
  greenText: {
    color: colors.primary,
  },
  orangeText: {
    color: colors.orange,
  },
  mapTitle: {
    color: colors.surface,
    fontSize: 20,
    fontWeight: "800",
    lineHeight: 26,
    width: 280,
    zIndex: 1,
  },
  routeDetails: {
    gap: 12,
    padding: 16,
  },
  routeName: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "600",
    lineHeight: 25,
  },
  routeLocation: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "500",
    lineHeight: 17,
    marginTop: -8,
  },
  metrics: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 16,
  },
  metric: {
    alignItems: "center",
    flexDirection: "row",
    gap: 6,
  },
  metricIcon: {
    alignItems: "center",
    borderColor: colors.primary,
    borderRadius: 4,
    borderWidth: 1.5,
    height: 14,
    justifyContent: "center",
    width: 14,
  },
  metricIconAccent: {
    borderColor: colors.orange,
  },
  metricIconText: {
    color: colors.primary,
    fontSize: 8,
    fontWeight: "800",
    lineHeight: 10,
  },
  metricIconTextAccent: {
    color: colors.orange,
  },
  metricLabel: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 18,
  },
  metricLabelAccent: {
    color: colors.orange,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 24,
    height: 52,
    justifyContent: "center",
    width: "100%",
  },
  primaryButtonText: {
    color: colors.surface,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 18,
  },
});

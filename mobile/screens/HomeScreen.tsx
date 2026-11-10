import * as Network from "expo-network";
import { StatusBar } from "expo-status-bar";
import { ResumeRouteCard } from "../components/ResumeRouteCard";
import { useCallback, useMemo, useRef, useState } from "react";
import {
  ImageBackground,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { router, useFocusEffect } from "expo-router";
import { getProfile } from "../../services/api";
import { getTrails } from "../../services/trailRepository";
import { formatKilometers } from "../../services/geoUtils";
import { getAuthSession } from "../../services/authSession";
import { Profile, Trail } from "../../types";
import {
  AppScreen,
  PrimaryButton,
  StatusNotice,
  colors,
  typography,
} from "../components/MiSenderoUI";
import { ExpandableSection } from "../components/ExpandableSection";
import { TrailMetrics } from "../components/TrailMetrics";
import {
  ExperienceProfile,
  getExperienceProfile,
  getRecommendedTrailForProfile,
  getTrailRecommendationReasons,
} from "../../services/experienceProfile";

type TagProps = {
  label: string;
};

export default function HomeScreen() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [experienceProfile, setExperienceProfile] =
    useState<ExperienceProfile | null>(null);
  const [trails, setTrails] = useState<Trail[]>([]);
  const [unavailableImageUrls, setUnavailableImageUrls] = useState<ReadonlySet<string>>(() => new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const loadHome = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setIsLoading(true);
    setError(null);

    try {
      const session = await getAuthSession();
      if (currentRequest !== requestId.current) return;

      if (!session) {
        router.replace("/");
        return;
      }

      const network = await Network.getNetworkStateAsync().catch(() => null);
      const offline = network?.isConnected === false || network?.isInternetReachable === false;
      const [profileData, trails, experience] = await Promise.all([
        offline ? Promise.resolve({ user: session.user } as Profile) : getProfile(session.token).catch(() => ({ user: session.user } as Profile)),
        getTrails(),
        getExperienceProfile(session.user.id),
      ]);

      if (currentRequest !== requestId.current) return;
      setProfile(profileData);
      setExperienceProfile(experience);
      setTrails(trails);
      setUnavailableImageUrls(new Set());
    } catch {
      if (currentRequest === requestId.current) setError("No pudimos actualizar tu inicio.");
    } finally {
      if (currentRequest === requestId.current) setIsLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    void loadHome();
    return () => { requestId.current += 1; };
  }, [loadHome]));

  const recommendedTrail = useMemo(() => experienceProfile
    ? getRecommendedTrailForProfile(trails, experienceProfile, unavailableImageUrls)
    : null, [trails, experienceProfile, unavailableImageUrls]);
  const photoUrl = recommendedTrail?.image_url?.trim();
  const recommendedPhoto = photoUrl && !unavailableImageUrls.has(photoUrl) ? photoUrl : null;
  const userName = profile?.user?.name || "viajera";
  const distance = recommendedTrail?.distance_km
    ? formatKilometers(recommendedTrail.distance_km)
    : "Distancia a confirmar";
  const duration = recommendedTrail?.duration || "Duracion a confirmar";
  const difficulty = recommendedTrail?.difficulty || "A confirmar";
  const canRecommend = experienceProfile?.completed && !experienceProfile.skipped && Boolean(experienceProfile.level);
  const recommendationReasons =
    experienceProfile && recommendedTrail
      ? getTrailRecommendationReasons(recommendedTrail, experienceProfile)
      : [];

  return (
    <AppScreen activeTab="inicio">
      <StatusBar style="dark" />
      <ResumeRouteCard />
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
          <View style={styles.hero}>
            <Text style={styles.title}>Buen día, {userName}</Text>
            <Text style={styles.subtitle}>
              Encontrá un camino para tu próxima salida.
            </Text>
          </View>

          <View style={styles.sectionHeader}>
            <PrimaryButton label="Descubrí tu sendero" tone="light" href="/descubri-tu-sendero" icon="sparkles-outline" />
          </View>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Recomendada para vos</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Ver todas las rutas"
              onPress={() => router.push("/explorar-rutas")}
              style={styles.sectionLink}
            >
              <Text style={styles.sectionAction}>Ver rutas</Text>
            </Pressable>
          </View>

          {!isLoading && !error && canRecommend ? (
            <Text style={styles.experienceLevel}>{`Tu nivel: ${experienceProfile?.level}`}</Text>
          ) : null}

          {isLoading ? (
            <StatusNotice
              isLoading
              message="Buscando tu perfil, rutas y recomendaciones."
              title="Actualizando inicio"
            />
          ) : null}

          {error ? (
            <StatusNotice
              actionLabel="Reintentar"
              message={error}
              onAction={loadHome}
              title="No se pudo actualizar"
              tone="error"
            />
          ) : null}

          {!isLoading && !error && !canRecommend ? (
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
          ) : null}

          {!isLoading && !error && canRecommend && recommendedTrail ? (
            <View style={styles.routeCard}>
              <Pressable
                accessibilityLabel={`Ver detalle de ${recommendedTrail.name}`}
                accessibilityRole="button"
                style={({ pressed }) => [
                  pressed && styles.pressed,
                ]}
                onPress={() =>
                  router.push({
                    pathname: "/trail-detail",
                    params: { id: String(recommendedTrail.id) },
                  })
                }
              >
                <ImageBackground
                  key={recommendedTrail.id}
                  source={recommendedPhoto ? { uri: recommendedPhoto } : undefined}
                  onError={() => {
                    if (!recommendedPhoto) return;
                    setUnavailableImageUrls(current => current.has(recommendedPhoto)
                      ? current : new Set([...current, recommendedPhoto]));
                  }}
                  imageStyle={styles.mapImage}
                  style={styles.mapPreview}
                >
                  <View style={styles.mapShade} />
                  <View style={styles.tags}>
                    <Tag label={difficulty} />
                  </View>
                  {!recommendedPhoto ? <Text style={styles.photoUnavailable}>Foto no disponible</Text> : null}
                </ImageBackground>

                <View style={styles.routeDetails}>
                  <Text style={styles.routeName}>{recommendedTrail.name}</Text>
                  <Text style={styles.routeLocation}>{recommendedTrail.location}</Text>

                  <TrailMetrics columns={2} items={[
                    { icon: "walk-outline", label: "Distancia", value: distance },
                    { icon: "time-outline", label: "Duración estimada", value: duration },
                  ]} />
                </View>
              </Pressable>
              <View style={styles.cardActions}>
                <PrimaryButton icon="trail-sign-outline" label="Ver detalle de la ruta" onPress={() => router.push({ pathname: "/trail-detail", params: { id: String(recommendedTrail.id) } })} />
                {recommendationReasons.length > 0 ? <ExpandableSection key={recommendedTrail.id} title="¿Por qué esta ruta?" icon="sparkles-outline">
                  {recommendationReasons.map(reason => <Text key={reason} style={styles.reasonText}>{reason}</Text>)}
                </ExpandableSection> : null}
              </View>
            </View>
          ) : null}

          {!isLoading && !error && canRecommend && !recommendedTrail ? (
            <View style={styles.emptyCard}>
              <Text style={styles.routeName}>No hay senderos acordes a tu nivel por ahora</Text>
              <Text style={styles.routeLocation}>Cuando haya rutas compatibles con tu experiencia, aparecerán acá.</Text>
            </View>
          ) : null}

      </ScrollView>
    </AppScreen>
  );
}

const Tag = ({ label }: TagProps) => (
  <View style={styles.tag}>
    <View style={styles.tagDot} />
    <Text style={styles.tagText}>
      {label}
    </Text>
  </View>
);

const styles = StyleSheet.create({
  content: {
    gap: 20,
    paddingBottom: 16,
    paddingTop: 6,
  },
  hero: {
    gap: 12,
  },
  title: {
    fontFamily: typography.extraBold,
    color: colors.ink,
    fontSize: 32,
    fontWeight: "800",
    lineHeight: 38,
  },
  subtitle: {
    fontFamily: typography.regular,
    color: colors.muted,
    fontSize: 15,
    lineHeight: 22,
  },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  sectionTitle: {
    fontFamily: typography.bold,
    color: colors.ink,
    fontSize: 18,
    fontWeight: "700",
    lineHeight: 25,
  },
  experienceLevel: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "700",
    marginTop: -12,
  },
  sectionAction: {
    fontFamily: typography.medium,
    color: colors.primary,
    fontSize: 13,
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
  pressed: {
    opacity: 0.72,
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
    backgroundColor: colors.primary,
    height: 220,
    justifyContent: "space-between",
    overflow: "hidden",
    padding: 16,
  },
  photoUnavailable: {
    color: colors.surface,
    fontSize: 13,
    textAlign: "center",
  },
  mapImage: {
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  mapShade: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
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
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: 6,
    width: 6,
  },
  tagText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "700",
  },
  routeDetails: {
    gap: 12,
    padding: 16,
  },
  routeName: {
    fontFamily: typography.bold,
    color: colors.ink,
    fontSize: 18,
    fontWeight: "700",
    lineHeight: 25,
  },
  routeLocation: {
    fontFamily: typography.regular,
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21,
    marginTop: -8,
  },
  reasonText: {
    fontFamily: typography.regular,
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21,
  },
  sectionLink: { minHeight: 44, justifyContent: "center", paddingLeft: 12 },
  cardActions: { paddingHorizontal: 16, paddingBottom: 8, gap: 8 },
});

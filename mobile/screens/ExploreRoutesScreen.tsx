import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  FlatList, ImageBackground, Pressable, StyleSheet, Text, View, useWindowDimensions,
  type ListRenderItem,
} from "react-native";
import { AppScreen, StatusNotice, colors, typography } from "../components/MiSenderoUI";
import { surfaceShadows } from "../components/surfaceShadows";
import { defaultCatalogFilters, TrailCatalogFilters, type CatalogFilters } from "../components/TrailCatalogFilters";
import { TrailSkeleton } from "../components/TrailSkeleton";
import { getTrails } from "../../services/trailRepository";
import { formatKilometers } from "../../services/geoUtils";
import { filterTrails } from "../../services/trailFilters";
import { getFavoriteTrailIds } from "../../services/favoriteTrails";
import { initDB } from "../../database/database";
import type { Trail } from "../../types";

const ROUTES_PAGE_SIZE = 6;

type RouteListItem = { trail: Trail; image: string };
type PhotoStatus = "loaded" | "failed";

export default function ExploreRoutesScreen() {
  const { width } = useWindowDimensions();
  const wide = width >= 840;
  const [trails, setTrails] = useState<Trail[]>([]);
  const [favoriteTrailIds, setFavoriteTrailIds] = useState<number[]>([]);
  const [filters, setFilters] = useState(defaultCatalogFilters);
  const [filterDraft, setFilterDraft] = useState<CatalogFilters | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(ROUTES_PAGE_SIZE);
  const [photoStatuses, setPhotoStatuses] = useState<Record<string, PhotoStatus>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const routeList = useRef<FlatList<RouteListItem>>(null);

  const { favoritesOnly } = filters;
  const hasActiveFilters = filters.area !== "all" || filters.distance !== "Todas" ||
    filters.difficulty !== "Todas" || favoritesOnly || searchQuery.trim().length > 0;
  const favoriteIdSet = useMemo(() => new Set(favoriteTrailIds), [favoriteTrailIds]);
  const filteredTrails = useMemo(() => {
    const photoRank = (trail: Trail) => {
      const url = trail.image_url?.trim();
      if (!url || photoStatuses[url] === "failed") return 2;
      return photoStatuses[url] === "loaded" ? 0 : 1;
    };
    const matches = filterTrails(trails, [], searchQuery, filters.difficulty, filters.distance, filters.area);
    return (favoritesOnly ? matches.filter((trail) => favoriteIdSet.has(trail.id)) : matches)
      .sort((a, b) => photoRank(a) - photoRank(b));
  }, [favoriteIdSet, favoritesOnly, filters, searchQuery, trails, photoStatuses]);

  const visibleRouteItems = useMemo(() => filteredTrails.slice(0, visibleCount).map((trail) => ({
    trail,
    image: trail.image_url?.trim() || "",
  })), [filteredTrails, visibleCount]);

  const loadRoutes = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await initDB();
      const trailList = await getTrails();
      setTrails(trailList);
      setPhotoStatuses({});
    } catch {
      setError("No pudimos cargar los senderos en este momento.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRoutes();
  }, [loadRoutes]);

  useFocusEffect(useCallback(() => {
    let active = true;
    void initDB().then(getFavoriteTrailIds).then((ids) => {
      if (active) setFavoriteTrailIds(ids);
    }).catch(() => {
      // A local favorites read should not prevent browsing the catalog.
    });
    return () => { active = false; };
  }, []));

  useEffect(() => {
    setVisibleCount(ROUTES_PAGE_SIZE);
  }, [filters, searchQuery]);

  const loadMoreRoutes = useCallback(() => {
    setVisibleCount((current) => Math.min(filteredTrails.length, current + ROUTES_PAGE_SIZE));
  }, [filteredTrails.length]);

  const markPhotoStatus = useCallback((imageUrl: string, status: PhotoStatus) => {
    if (!imageUrl) return;
    setPhotoStatuses(current => current[imageUrl] === status ? current : { ...current, [imageUrl]: status });
  }, []);

  const resetSearch = () => {
    setFilters(defaultCatalogFilters);
    setFilterDraft(null);
    setSearchQuery("");
  };

  const renderRoute: ListRenderItem<RouteListItem> = useCallback(
    ({ item }) => (
      <RouteCard
        image={item.image}
        imageFailed={photoStatuses[item.image] === "failed"}
        isFavorite={favoriteIdSet.has(item.trail.id)}
        onPhotoStatus={markPhotoStatus}
        trail={item.trail}
        wide={wide}
      />
    ),
    [favoriteIdSet, markPhotoStatus, photoStatuses, wide]
  );

  const resultCount = filteredTrails.length;
  const showResults = !isLoading && !error;

  return (
    <AppScreen activeTab="explorar" maxContentWidth={wide ? 1060 : undefined}>
      <FlatList
        ref={routeList}
        key={wide ? "grid" : "list"}
        numColumns={wide ? 2 : 1}
        columnWrapperStyle={wide ? styles.cardRow : undefined}
        contentContainerStyle={styles.listContent}
        data={showResults ? visibleRouteItems : []}
        initialNumToRender={ROUTES_PAGE_SIZE}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        keyExtractor={(item) => String(item.trail.id)}
        ListHeaderComponent={(
          <View style={styles.header}>
            <View style={styles.intro}>
              <View style={styles.eyebrowRow}>
                <Ionicons aria-hidden accessible={false} name="compass-outline" color={colors.green} size={17} />
                <Text style={styles.eyebrow}>Explorá MiSendero</Text>
              </View>
              <Text accessibilityRole="header" style={[styles.title, wide && styles.titleWide]}>
                Encontrá tu próximo sendero
              </Text>
              <Text style={styles.subtitle}>
                Buscá por nombre o lugar y encontrá rutas para tu próxima salida.
              </Text>
            </View>

            <TrailCatalogFilters
              filters={filters} setFilters={setFilters}
              query={searchQuery} setQuery={setSearchQuery}
              draft={filterDraft} setDraft={setFilterDraft}
              onApply={(nextFilters) => {
                setFilters(nextFilters);
                setFilterDraft(null);
                routeList.current?.scrollToOffset({ offset: 0, animated: true });
              }}
            />

            {!hasActiveFilters && filterDraft === null ? <CatalogShortcuts /> : null}

            <View style={styles.results}>
              <View style={styles.resultsHeading}>
                <Text accessibilityRole="header" style={styles.sectionTitle}>Senderos</Text>
                {showResults ? (
                  <Text accessibilityLiveRegion="polite" aria-live="polite" style={styles.resultsCount}>
                    {resultCount === 1 ? "1 resultado" : `${resultCount} resultados`}
                  </Text>
                ) : null}
              </View>
              {isLoading ? <TrailSkeleton variant="list" count={wide ? 2 : 3} /> : null}
              {error ? (
                <StatusNotice actionLabel="Reintentar" message={error} onAction={loadRoutes}
                  title="No se pudo cargar" tone="error" />
              ) : null}
              {showResults && resultCount === 0 ? (
                <StatusNotice
                  actionLabel={hasActiveFilters ? "Restablecer búsqueda" : undefined}
                  message={getEmptyMessage(hasActiveFilters, favoritesOnly, favoriteTrailIds.length)}
                  onAction={hasActiveFilters ? resetSearch : undefined}
                  title={hasActiveFilters ? "Sin resultados" : "Sin senderos disponibles"}
                />
              ) : null}
            </View>
          </View>
        )}
        ListFooterComponent={showResults && resultCount > 0 ? (
          <View style={styles.footer}>
            {visibleRouteItems.length < resultCount ? (
              <Pressable accessibilityRole="button" onPress={loadMoreRoutes}
                style={({ pressed }) => [styles.moreButton, pressed && styles.pressed]}>
                <Text style={styles.moreLabel}>Ver más senderos</Text>
                <Ionicons aria-hidden accessible={false} name="chevron-down" size={17} color={colors.green} />
              </Pressable>
            ) : null}
            <StatusNotice title="Antes de salir"
              message="Si vas a una zona con poca señal, descargá el mapa del sendero con anticipación." />
          </View>
        ) : undefined}
        maxToRenderPerBatch={ROUTES_PAGE_SIZE}
        renderItem={renderRoute}
        showsVerticalScrollIndicator={false}
        windowSize={5}
      />
    </AppScreen>
  );
}

function getEmptyMessage(hasFilters: boolean, favoritesOnly: boolean, favoriteCount: number) {
  if (favoritesOnly && !favoriteCount) return "Todavía no guardaste senderos en favoritos.";
  if (hasFilters) return "Probá con menos filtros o buscá por otro nombre o lugar.";
  return "Cuando haya senderos disponibles, van a aparecer acá.";
}

function CatalogShortcuts() {
  return (
    <View style={styles.shortcuts}>
      <Pressable accessibilityRole="button" onPress={() => router.push("/descubri-tu-sendero")}
        style={({ pressed }) => [styles.shortcut, styles.recommendation, pressed && styles.pressed]}>
        <Ionicons aria-hidden accessible={false} name="sparkles-outline" size={19} color={colors.green} />
        <Text style={styles.shortcutText}>Descubrí tu sendero</Text>
        <Ionicons aria-hidden accessible={false} name="chevron-forward" size={16} color={colors.green} />
      </Pressable>
      <Pressable accessibilityRole="button" onPress={() => router.push("/parques-nacionales")}
        style={({ pressed }) => [styles.shortcut, pressed && styles.pressed]}>
        <Ionicons aria-hidden accessible={false} name="shield-checkmark-outline" size={19} color={colors.green} />
        <Text style={styles.shortcutText}>Parques Nacionales</Text>
        <Ionicons aria-hidden accessible={false} name="chevron-forward" size={16} color={colors.green} />
      </Pressable>
    </View>
  );
}

function RouteCard({ trail, image, imageFailed, isFavorite, onPhotoStatus, wide }: {
  trail: Trail;
  image: string;
  imageFailed: boolean;
  isFavorite: boolean;
  onPhotoStatus: (imageUrl: string, status: PhotoStatus) => void;
  wide: boolean;
}) {
  const distance = trail.distance_km == null ? "Distancia a confirmar" : formatKilometers(trail.distance_km);
  const difficulty = trail.difficulty?.trim().toLowerCase();
  const difficultyLabel = `Dificultad ${difficulty || "a confirmar"}`;
  const aiEstimated = Boolean(difficulty) && trail.provenance?.difficulty_source === "ai";
  const showPhoto = Boolean(image) && !imageFailed;

  return (
    <Pressable
      accessibilityLabel={`Ver detalle de ${trail.name}`}
      accessibilityHint={`${trail.location}. ${difficultyLabel}${aiEstimated ? ", estimada con IA" : ""}. ${distance}.`}
      accessibilityRole="button"
      style={({ pressed }) => [styles.routeCard, wide && styles.routeCardWide, pressed && styles.pressed]}
      onPress={() => router.push({ pathname: "/trail-detail", params: { id: String(trail.id) } })}
    >
      <ImageBackground
        fadeDuration={0}
        onError={() => onPhotoStatus(image, "failed")}
        onLoad={() => onPhotoStatus(image, "loaded")}
        source={showPhoto ? { uri: image } : undefined}
        style={styles.imageBox}
      >
        {!showPhoto ? (
          <View style={styles.photoFallback}>
            <Ionicons aria-hidden accessible={false} name="image-outline" size={23} color={colors.muted} />
            <Text style={styles.photoFallbackText}>Foto no disponible</Text>
          </View>
        ) : null}
        <View style={styles.imageBadges}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{difficultyLabel}</Text>
            {aiEstimated ? <Text style={styles.badgeSource}>Estimada con IA</Text> : null}
          </View>
          {isFavorite ? (
            <View style={styles.favoriteBadge}>
              <Ionicons aria-hidden accessible={false} name="star" size={16} color={colors.green} />
            </View>
          ) : null}
        </View>
      </ImageBackground>
      <View style={styles.routeBody}>
        <View style={styles.routeHeading}>
          <View style={styles.routeCopy}>
            <Text style={styles.routeTitle}>{trail.name}</Text>
            <Text style={styles.routePlace}>{trail.location}</Text>
          </View>
          <Ionicons aria-hidden accessible={false} name="chevron-forward" size={19} color={colors.green} />
        </View>
        <View style={styles.routeMeta}>
          <View style={styles.metric}>
            <Ionicons aria-hidden accessible={false} name="walk-outline" size={16} color={colors.green} />
            <Text style={styles.metricText}>{distance}</Text>
          </View>
          <View style={styles.metric}>
            <Ionicons aria-hidden accessible={false} name="time-outline" size={16} color={colors.green} />
            <Text style={styles.metricText}>{trail.duration || "Duración a confirmar"}</Text>
          </View>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  listContent: { paddingBottom: 20, paddingTop: 12 },
  header: { gap: 18, marginBottom: 12 },
  intro: { gap: 7, paddingBottom: 2 },
  eyebrowRow: { alignItems: "center", flexDirection: "row", gap: 7 },
  eyebrow: { color: colors.green, fontFamily: typography.bold, fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },
  title: { color: colors.ink, fontFamily: typography.extraBold, fontSize: 33, letterSpacing: -0.9, lineHeight: 36 },
  titleWide: { fontSize: 46, letterSpacing: -1.5, lineHeight: 51 },
  subtitle: { color: colors.muted, fontFamily: typography.regular, fontSize: 15, lineHeight: 22 },
  shortcuts: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  shortcut: {
    ...surfaceShadows.card,
    alignItems: "center", backgroundColor: colors.surface, borderRadius: 13,
    flexBasis: 150, flexDirection: "row", flexGrow: 1, gap: 8, minHeight: 46,
    paddingHorizontal: 11, paddingVertical: 8,
  },
  recommendation: { backgroundColor: colors.soft },
  shortcutText: { color: colors.green, flex: 1, fontFamily: typography.bold, fontSize: 14, lineHeight: 19 },
  results: { borderTopColor: colors.line, borderTopWidth: 1, gap: 10, paddingTop: 14 },
  resultsHeading: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "space-between" },
  sectionTitle: { color: colors.ink, fontFamily: typography.extraBold, fontSize: 21, lineHeight: 27 },
  resultsCount: { color: colors.muted, fontFamily: typography.medium, fontSize: 14, lineHeight: 20 },
  cardRow: { justifyContent: "space-between" },
  routeCard: {
    ...surfaceShadows.card,
    backgroundColor: colors.surface, borderRadius: 19, marginBottom: 14,
  },
  routeCardWide: { width: "49.2%" },
  pressed: { opacity: 0.78 },
  imageBox: { backgroundColor: colors.soft, borderTopLeftRadius: 19, borderTopRightRadius: 19, height: 148, overflow: "hidden" },
  imageBadges: { alignItems: "flex-start", flexDirection: "row", gap: 6, justifyContent: "space-between", padding: 12 },
  photoFallback: { ...StyleSheet.absoluteFill, alignItems: "center", gap: 4, justifyContent: "center", paddingTop: 23 },
  photoFallbackText: { color: colors.muted, fontFamily: typography.regular, fontSize: 13, lineHeight: 18 },
  badge: { backgroundColor: colors.white, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 6, flexShrink: 1 },
  badgeText: { color: colors.green, fontFamily: typography.bold, fontSize: 12, lineHeight: 17 },
  badgeSource: { color: colors.muted, fontFamily: typography.medium, fontSize: 12, lineHeight: 16 },
  favoriteBadge: {
    alignItems: "center", backgroundColor: colors.mint, borderRadius: 999,
    height: 31, justifyContent: "center", width: 31,
  },
  routeBody: { flex: 1, gap: 12, justifyContent: "space-between", padding: 14 },
  routeHeading: { alignItems: "center", flexDirection: "row", gap: 10 },
  routeCopy: { flex: 1, gap: 4, minWidth: 0 },
  routeTitle: { color: colors.ink, fontFamily: typography.extraBold, fontSize: 18, lineHeight: 23 },
  routePlace: { color: colors.muted, fontFamily: typography.regular, fontSize: 14, lineHeight: 19 },
  routeMeta: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  metric: {
    alignItems: "center", backgroundColor: colors.soft, borderRadius: 8, flexDirection: "row",
    gap: 5, maxWidth: "100%", paddingHorizontal: 8, paddingVertical: 5,
  },
  metricText: { color: colors.green, flexShrink: 1, fontFamily: typography.medium, fontSize: 13, lineHeight: 18 },
  footer: { gap: 16, paddingTop: 4 },
  moreButton: {
    ...surfaceShadows.card,
    alignItems: "center", alignSelf: "center", backgroundColor: colors.surface,
    borderRadius: 13, flexDirection: "row", gap: 8, justifyContent: "center", minHeight: 46,
    paddingHorizontal: 16,
  },
  moreLabel: { color: colors.green, fontFamily: typography.bold, fontSize: 15, lineHeight: 21 },
});

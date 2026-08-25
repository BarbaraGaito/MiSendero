import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Animated,
  Easing,
  FlatList,
  Image,
  ImageBackground,
  ListRenderItem,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import {
  AppScreen,
  Card,
  ScreenTitle,
  StatusNotice,
  colors,
  trailImages,
} from "../components/MiSenderoUI";
import { getTrails } from "../../services/api";
import { Trail } from "../../types";

const ROUTES_PAGE_SIZE = 6;
const DIFFICULTY_FILTERS = ["Todas", "Baja", "Media", "Alta"];
const DISTANCE_FILTERS = [
  { id: "Todas", label: "Todas" },
  { id: "Corta", label: "0-5 km" },
  { id: "Media", label: "5-10 km" },
  { id: "Larga", label: "+10 km" },
  { id: "Sin dato", label: "Sin dato" },
] as const;

type RouteListItem = {
  trail: Trail;
  image: string;
};

type DistanceFilter = (typeof DISTANCE_FILTERS)[number]["id"];

const normalizeText = (value: string) =>
  value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

export default function ExploreRoutesScreen() {
  const [trails, setTrails] = useState<Trail[]>([]);
  const [activeFilter, setActiveFilter] = useState("Todas");
  const [activeDistanceFilter, setActiveDistanceFilter] = useState<DistanceFilter>("Todas");
  const [searchQuery, setSearchQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(ROUTES_PAGE_SIZE);
  const [loadedImages, setLoadedImages] = useState<Record<string, boolean>>({});
  const [paintedImages, setPaintedImages] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const hasActiveFilters =
    activeFilter !== "Todas" || activeDistanceFilter !== "Todas" || searchQuery.trim().length > 0;
  const filteredTrails = useMemo(
    () => {
      const normalizedQuery = normalizeText(searchQuery.trim());

      return trails.filter((trail) => {
        const distanceKm = trail.distance_km;
        const searchableText = normalizeText(
          `${trail.name} ${trail.location}`
        );
        const matchesQuery =
          normalizedQuery.length === 0 || searchableText.includes(normalizedQuery);
        const matchesDifficulty =
          activeFilter === "Todas" ||
          normalizeText(trail.difficulty).includes(normalizeText(activeFilter));
        const matchesDistance =
          activeDistanceFilter === "Todas" ||
          (activeDistanceFilter === "Corta" &&
            typeof distanceKm === "number" &&
            distanceKm <= 5) ||
          (activeDistanceFilter === "Media" &&
            typeof distanceKm === "number" &&
            distanceKm > 5 &&
            distanceKm <= 10) ||
          (activeDistanceFilter === "Larga" &&
            typeof distanceKm === "number" &&
            distanceKm > 10) ||
          (activeDistanceFilter === "Sin dato" && distanceKm === null);

        return matchesQuery && matchesDifficulty && matchesDistance;
      });
    },
    [activeDistanceFilter, activeFilter, searchQuery, trails]
  );
  const visibleTrails = useMemo(
    () => filteredTrails.slice(0, visibleCount),
    [filteredTrails, visibleCount]
  );
  const visibleRouteItems = useMemo(
    () =>
      visibleTrails.map((trail, index) => ({
        trail,
        image: trail.image_url || (index % 2 === 0 ? trailImages.mountain : trailImages.forest),
      })),
    [visibleTrails]
  );
  const loadedRouteItems = useMemo(
    () => visibleRouteItems.filter((item) => loadedImages[item.image]),
    [loadedImages, visibleRouteItems]
  );
  const pendingImageUrls = useMemo(
    () => [
      ...new Set(
        visibleRouteItems
          .map((item) => item.image)
          .filter((imageUrl) => !loadedImages[imageUrl])
      ),
    ],
    [loadedImages, visibleRouteItems]
  );
  const isSearchingRoutes =
    !isLoading &&
    !error &&
    visibleRouteItems.some((item) => !paintedImages[item.image]);

  const loadRoutes = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      setTrails(await getTrails());
    } catch (loadError) {
      setError("No pudimos cargar los senderos en este momento.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRoutes();
  }, [loadRoutes]);

  useEffect(() => {
    setVisibleCount(ROUTES_PAGE_SIZE);
  }, [activeDistanceFilter, activeFilter, searchQuery]);

  const loadMoreRoutes = useCallback(() => {
    setVisibleCount((currentCount) =>
      Math.min(filteredTrails.length, currentCount + ROUTES_PAGE_SIZE)
    );
  }, [filteredTrails.length]);

  const markImageLoaded = useCallback((imageUrl: string) => {
    setLoadedImages((currentImages) => ({
      ...currentImages,
      [imageUrl]: true,
    }));
  }, []);

  const markImagePainted = useCallback((imageUrl: string) => {
    setPaintedImages((currentImages) => ({
      ...currentImages,
      [imageUrl]: true,
    }));
  }, []);

  const clearFilters = useCallback(() => {
    setActiveFilter("Todas");
    setActiveDistanceFilter("Todas");
    setSearchQuery("");
  }, []);

  const renderRoute: ListRenderItem<RouteListItem> = useCallback(
    ({ item }) => (
      <RouteCard
        image={item.image}
        imageReady={Boolean(paintedImages[item.image])}
        onImageReady={markImagePainted}
        trail={item.trail}
      />
    ),
    [markImagePainted, paintedImages]
  );

  const header = (
    <View>
      <ScreenTitle
        eyebrow="Explorar rutas"
        title="Encontra tu proxima ruta"
        subtitle="Busca por nombre o zona y filtra por dificultad o distancia."
      />

      <View>
        <View style={styles.searchBox}>
          <Ionicons name="search-outline" size={18} color={colors.muted} />
          <TextInput
            accessibilityLabel="Buscar rutas por zona o nombre"
            onChangeText={setSearchQuery}
            placeholder="Buscar por zona o nombre"
            placeholderTextColor={colors.muted}
            returnKeyType="search"
            style={styles.searchInput}
            value={searchQuery}
          />
          {searchQuery.trim().length > 0 ? (
            <Pressable
              accessibilityLabel="Limpiar busqueda"
              accessibilityRole="button"
              hitSlop={8}
              onPress={() => setSearchQuery("")}
              style={({ pressed }) => [
                styles.clearSearchButton,
                pressed && styles.pressed,
              ]}
            >
              <Ionicons name="close" size={16} color={colors.greenDark} />
            </Pressable>
          ) : null}
        </View>

        <Text style={styles.filterLabel}>Dificultad</Text>
        <View style={styles.filterRow}>
          {DIFFICULTY_FILTERS.map((filter) => {
            const isActive = activeFilter === filter;

            return (
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ selected: isActive }}
                key={filter}
                onPress={() => setActiveFilter(filter)}
                style={({ pressed }) => pressed && styles.pressed}
              >
                <Text style={isActive ? styles.filterActive : styles.filter}>
                  {filter}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text style={styles.filterLabel}>Distancia</Text>
        <View style={styles.filterRow}>
          {DISTANCE_FILTERS.map((filter) => {
            const isActive = activeDistanceFilter === filter.id;

            return (
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ selected: isActive }}
                key={filter.id}
                onPress={() => setActiveDistanceFilter(filter.id)}
                style={({ pressed }) => pressed && styles.pressed}
              >
                <Text style={isActive ? styles.filterActive : styles.filter}>
                  {filter.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {hasActiveFilters ? (
          <Pressable onPress={clearFilters} style={styles.clearFiltersButton}>
            <Ionicons name="refresh-outline" size={16} color={colors.greenDark} />
            <Text style={styles.clearFiltersText}>Limpiar filtros</Text>
          </Pressable>
        ) : null}

        <View style={styles.resultsHeader}>
          <Text style={styles.sectionTitle}>Senderos disponibles</Text>
          <Text style={styles.resultsCount}>{filteredTrails.length} rutas</Text>
        </View>

        {isLoading ? (
          <StatusNotice
            isLoading
            message="Estamos trayendo senderos y preparando las imagenes."
            title="Cargando senderos"
          />
        ) : null}
        {error ? (
          <StatusNotice
            actionLabel="Reintentar"
            message={error}
            onAction={loadRoutes}
            title="No se pudo cargar"
            tone="error"
          />
        ) : null}
        {!isLoading && !error && filteredTrails.length === 0 ? (
          <StatusNotice
            actionLabel={hasActiveFilters ? "Limpiar filtros" : undefined}
            message={
              hasActiveFilters
                ? "Probá con menos filtros o una busqueda mas amplia."
                : "Cuando haya senderos disponibles, apareceran en esta lista."
            }
            onAction={hasActiveFilters ? clearFilters : undefined}
            title={hasActiveFilters ? "Sin resultados" : "Sin senderos disponibles"}
            tone="warning"
          />
        ) : null}
      </View>
    </View>
  );

  const footer = (
    <>
      <ImagePreloadQueue
        imageUrls={pendingImageUrls}
        onImageLoaded={markImageLoaded}
      />
      {isSearchingRoutes ? <RoutesLoader /> : null}
      {visibleRouteItems.length < filteredTrails.length ? (
        <Text style={styles.statusText}>Cargando mas rutas...</Text>
      ) : null}
      {!isLoading && !error ? (
        <Card tone="green">
          <Text style={styles.cardTitle}>Tip de seguridad</Text>
          <Text style={styles.cardText}>Descarga el mapa antes de salir si la zona tiene poca senal.</Text>
        </Card>
      ) : null}
    </>
  );

  return (
    <AppScreen activeTab="explorar">
      <FlatList
        contentContainerStyle={styles.listContent}
        data={loadedRouteItems}
        initialNumToRender={ROUTES_PAGE_SIZE}
        keyExtractor={(item) => String(item.trail.id)}
        ListFooterComponent={footer}
        ListHeaderComponent={header}
        maxToRenderPerBatch={4}
        onEndReached={loadMoreRoutes}
        onEndReachedThreshold={0.45}
        removeClippedSubviews
        renderItem={renderRoute}
        showsVerticalScrollIndicator={false}
        updateCellsBatchingPeriod={80}
        windowSize={5}
      />
    </AppScreen>
  );
}

function RouteCard({
  trail,
  image,
  imageReady,
  onImageReady,
}: {
  trail: Trail;
  image: string;
  imageReady: boolean;
  onImageReady: (imageUrl: string) => void;
}) {
  const distance = trail.distance_km ? `${trail.distance_km} km` : "Distancia a confirmar";

  return (
    <Pressable
      accessibilityLabel={`Ver detalle de ${trail.name}`}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.routeCard,
        !imageReady && styles.routeCardHidden,
        pressed && styles.pressed,
      ]}
      onPress={() =>
        router.push({
          pathname: "/trail-detail",
          params: { id: String(trail.id) },
        })
      }
    >
      <ImageBackground
        fadeDuration={0}
        imageStyle={styles.image}
        onLoad={() => {
          requestAnimationFrame(() => onImageReady(image));
        }}
        source={{ uri: image }}
        style={styles.imageBox}
      >
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{trail.difficulty}</Text>
        </View>
      </ImageBackground>
      <View style={styles.routeBody}>
        <Text style={styles.routeTitle}>{trail.name}</Text>
        <Text style={styles.routePlace}>{trail.location}</Text>
        <Text style={styles.routeMeta}>
          {distance} - {trail.duration || "Duracion a confirmar"}
        </Text>
      </View>
    </Pressable>
  );
}

function RoutesLoader() {
  const progress = React.useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.timing(progress, {
        duration: 1400,
        easing: Easing.inOut(Easing.cubic),
        toValue: 1,
        useNativeDriver: true,
      })
    );

    animation.start();

    return () => animation.stop();
  }, [progress]);

  const translateX = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [-28, 252],
  });

  return (
    <View style={styles.routesLoader}>
      <View style={styles.routesProgressTrack}>
        <Animated.View
          style={[
            styles.routesProgressFill,
            { transform: [{ translateX }] },
          ]}
        />
        <Animated.View
          style={[
            styles.routesHiker,
            { transform: [{ translateX }] },
          ]}
        >
          <Ionicons name="walk-outline" size={18} color={colors.white} />
        </Animated.View>
      </View>
      <Text style={styles.routesLoaderText}>Buscando rutas</Text>
    </View>
  );
}

function ImagePreloadQueue({
  imageUrls,
  onImageLoaded,
}: {
  imageUrls: string[];
  onImageLoaded: (imageUrl: string) => void;
}) {
  if (imageUrls.length === 0) return null;

  return (
    <View pointerEvents="none" style={styles.imagePreloadQueue}>
      {imageUrls.map((imageUrl) => (
        <Image
          key={imageUrl}
          onLoad={() => onImageLoaded(imageUrl)}
          source={{ uri: imageUrl }}
          style={styles.hiddenPreloadImage}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  listContent: {
    paddingBottom: 118,
  },
  searchBox: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    minHeight: 48,
    marginBottom: 14,
    paddingHorizontal: 12,
  },
  searchInput: {
    color: colors.ink,
    flex: 1,
    fontSize: 14,
    fontWeight: "700",
    minWidth: 0,
    paddingVertical: 8,
  },
  clearSearchButton: {
    alignItems: "center",
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    height: 28,
    justifyContent: "center",
    width: 28,
  },
  filterLabel: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
    marginBottom: 8,
  },
  filterRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 14,
  },
  filter: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  filterActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
    borderRadius: 999,
    borderWidth: 1,
    color: colors.surface,
    fontSize: 13,
    fontWeight: "800",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  clearFiltersButton: {
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    flexDirection: "row",
    gap: 6,
    marginBottom: 16,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  clearFiltersText: {
    color: colors.greenDark,
    fontSize: 13,
    fontWeight: "900",
  },
  resultsHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
    marginBottom: 12,
  },
  sectionTitle: {
    color: colors.ink,
    flex: 1,
    fontSize: 18,
    fontWeight: "800",
  },
  resultsCount: {
    color: colors.muted,
    flexShrink: 0,
    fontSize: 12,
    fontWeight: "900",
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 14,
  },
  routeCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 22,
    borderWidth: 1,
    marginBottom: 14,
    overflow: "hidden",
  },
  routeCardHidden: {
    height: 0,
    marginBottom: 0,
    opacity: 0,
  },
  pressed: {
    opacity: 0.72,
  },
  routesLoader: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 22,
    borderWidth: 1,
    gap: 10,
    justifyContent: "center",
    marginBottom: 14,
    minHeight: 96,
    paddingHorizontal: 18,
  },
  routesLoaderText: {
    color: colors.greenDark,
    fontSize: 14,
    fontWeight: "900",
  },
  routesProgressTrack: {
    backgroundColor: colors.mint,
    borderRadius: 999,
    height: 14,
    maxWidth: 280,
    overflow: "hidden",
    position: "relative",
    width: "100%",
  },
  routesProgressFill: {
    backgroundColor: colors.green,
    borderRadius: 999,
    height: "100%",
    left: 0,
    opacity: 0.82,
    position: "absolute",
    top: 0,
    width: 84,
  },
  routesHiker: {
    alignItems: "center",
    backgroundColor: colors.green,
    borderRadius: 999,
    height: 28,
    justifyContent: "center",
    left: 0,
    position: "absolute",
    top: -7,
    width: 28,
  },
  imagePreloadQueue: {
    height: 1,
    left: -1000,
    overflow: "hidden",
    position: "absolute",
    top: -1000,
    width: 1,
  },
  hiddenPreloadImage: {
    height: 1,
    opacity: 0,
    width: 1,
  },
  imageBox: {
    height: 126,
    padding: 12,
  },
  image: {
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
  },
  badge: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.9)",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  badgeText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
  },
  routeBody: {
    gap: 3,
    padding: 14,
  },
  routeTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  routePlace: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "500",
  },
  routeMeta: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
    marginTop: 6,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
});

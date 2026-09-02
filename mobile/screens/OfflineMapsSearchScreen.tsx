import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
  colors,
  trailImages,
} from "../components/MiSenderoUI";
import { getTrails } from "../../services/api";
import { getOfflineMaps } from "../../services/offlineMaps";
import { Trail } from "../../types";

export default function OfflineMapsSearchScreen() {
  const [query, setQuery] = useState("");
  const [trails, setTrails] = useState<Trail[]>([]);
  const [downloadedTrailIds, setDownloadedTrailIds] = useState<Set<number>>(
    () => new Set()
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadTrails = async () => {
      try {
        const [loadedTrails, offlineMaps] = await Promise.all([
          getTrails(),
          getOfflineMaps(),
        ]);
        const downloadedIds = offlineMaps
          .filter(isOfflineMapAvailable)
          .map((map) => map.trailId ?? map.trail?.id)
          .filter((trailId): trailId is number => typeof trailId === "number");

        setTrails(loadedTrails);
        setDownloadedTrailIds(new Set(downloadedIds));
        setError(null);
      } catch {
        setError("No pudimos cargar las zonas disponibles.");
      } finally {
        setIsLoading(false);
      }
    };

    loadTrails();
  }, []);

  const normalizedQuery = query.trim().toLowerCase();
  const visibleTrails = normalizedQuery
    ? trails.filter((trail) =>
        `${trail.name} ${trail.location}`.toLowerCase().includes(normalizedQuery)
      )
    : trails;

  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Nueva descarga"
        title="Buscar mapas offline"
        subtitle="Elegi una ruta disponible para preparar su mapa."
      />

      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={18} color={colors.primary} />

          <TextInput
            placeholder="Buscar ruta o zona"
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={query}
            onChangeText={setQuery}
          />
        </View>

        <Pressable
          style={styles.filterButton}
          onPress={() => router.push("/filtros-mapas")}
        >
          <Ionicons name="options-outline" size={18} color="#D84C3F" />
          <Text style={styles.filterText}>Filtrar</Text>
        </Pressable>
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {error ? <Text style={styles.statusText}>{error}</Text> : null}
        {isLoading ? <Text style={styles.statusText}>Cargando rutas...</Text> : null}

        {!isLoading && visibleTrails.length === 0 ? (
          <Card>
            <Text style={styles.emptyTitle}>No hay rutas disponibles</Text>
            <Text style={styles.emptyText}>
              Cuando la base tenga rutas para tu busqueda, van a aparecer aca.
            </Text>
          </Card>
        ) : (
          visibleTrails.map((trail) => (
            <TrailDownloadCard
              isDownloaded={downloadedTrailIds.has(trail.id)}
              key={trail.id}
              trail={trail}
            />
          ))
        )}
      </ScrollView>

      <View style={styles.bottomButtons}>
        <PrimaryButton
          label="Ver mapas descargados"
          icon="download-outline"
          href="/offline-mapas-descargados"
        />

        <Pressable
          style={styles.secondaryButton}
          onPress={() => router.push("/mapas-offline")}
        >
          <Text style={styles.secondaryText}>Volver a mapas</Text>
        </Pressable>
      </View>
    </AppScreen>
  );
}

function TrailDownloadCard({
  isDownloaded,
  trail,
}: {
  isDownloaded: boolean;
  trail: Trail;
}) {
  const distance = trail.distance_km ? `${trail.distance_km} km` : "Distancia sin cargar";
  const duration = trail.duration || "Duracion sin cargar";

  return (
    <Card>
      <Image
        source={{ uri: trail.image_url || trailImages.mountain }}
        style={styles.image}
      />

      <View style={styles.info}>
        <View style={styles.titleRow}>
          <Ionicons name="map-outline" size={18} color={colors.primary} />
          <Text style={styles.title}>{trail.name}</Text>
        </View>

        <Text style={styles.subtitle}>
          {trail.location} - {distance} - {duration}
        </Text>
      </View>

      {isDownloaded ? (
        <View style={styles.downloadedBadge}>
          <Ionicons name="checkmark-circle-outline" size={18} color={colors.green} />
          <Text style={styles.downloadedText}>Mapa descargado</Text>
        </View>
      ) : (
        <PrimaryButton
          label="Descargar"
          icon="download-outline"
          onPress={() =>
            router.push({
              pathname: "/offline-descarga",
              params: { id: String(trail.id) },
            })
          }
        />
      )}
    </Card>
  );
}

const isOfflineMapAvailable = (map: Awaited<ReturnType<typeof getOfflineMaps>>[number]) =>
  map.status === "disponible" &&
  map.totalTiles > 0 &&
  map.downloadedTiles >= map.totalTiles;

const styles = StyleSheet.create({
  searchRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    marginBottom: 18,
  },
  searchBox: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 18,
    flex: 1,
    flexDirection: "row",
    height: 54,
    paddingHorizontal: 14,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 10,
  },
  input: {
    color: colors.ink,
    flex: 1,
    fontSize: 16,
    fontWeight: "700",
    marginLeft: 8,
  },
  filterButton: {
    alignItems: "center",
    backgroundColor: "#FFECEC",
    borderRadius: 18,
    flexDirection: "row",
    gap: 6,
    height: 54,
    paddingHorizontal: 16,
  },
  filterText: {
    color: "#D84C3F",
    fontWeight: "800",
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 12,
  },
  emptyTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  emptyText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 20,
    marginTop: 6,
  },
  image: {
    borderRadius: 18,
    height: 170,
    marginBottom: 16,
    width: "100%",
  },
  info: {
    marginBottom: 18,
  },
  titleRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 6,
  },
  title: {
    color: colors.ink,
    flex: 1,
    fontSize: 18,
    fontWeight: "800",
  },
  subtitle: {
    color: "#D97706",
    fontSize: 13,
    fontWeight: "700",
    marginTop: 6,
  },
  downloadedBadge: {
    alignItems: "center",
    backgroundColor: colors.primarySoft,
    borderRadius: 18,
    flexDirection: "row",
    gap: 7,
    justifyContent: "center",
    minHeight: 52,
    paddingHorizontal: 14,
  },
  downloadedText: {
    color: colors.greenDark,
    fontSize: 15,
    fontWeight: "900",
  },
  bottomButtons: {
    flex: 1,
    gap: 12,
    justifyContent: "flex-end",
    marginBottom: 12,
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderColor: colors.primary,
    borderRadius: 27,
    borderWidth: 1.5,
    height: 54,
    justifyContent: "center",
  },
  secondaryText: {
    color: colors.primary,
    fontSize: 16,
    fontWeight: "800",
  },
});

import { router, useFocusEffect } from "expo-router";
import { offlineMapStatusLabel } from "../../../services/offlineMapPresentation";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
} from "../../components/MiSenderoUI";
import {
  deleteOfflineMap,
  getOfflineMaps,
  getVerifiedOfflineMapByTrailId,
  OfflineMap,
} from "../../../services/offlineMaps";
import { DownloadedMapCard, styles } from "./OfflineFlowShared";

const formatDate = (timestamp: number) =>
  new Date(timestamp).toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "short",
  });

const formatStorage = (sizeMb: number) =>
  `${sizeMb.toLocaleString("es-AR", { maximumFractionDigits: 0 })} MB`;

export default function OfflineDownloadedMaps23Screen() {
  const [maps, setMaps] = useState<OfflineMap[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deletingMapId, setDeletingMapId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMaps = useCallback(async () => {
    try {
      setMaps(await getOfflineMaps());
      setError(null);
    } catch {
      setError("No pudimos cargar los mapas descargados.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMaps();
  }, [loadMaps]);

  useFocusEffect(
    useCallback(() => {
      loadMaps();
    }, [loadMaps])
  );

  const totalSize = maps.reduce((total, map) => total + map.sizeMb, 0);

  const removeMap = async (mapId: number) => {
    if (deletingMapId) return;

    setDeletingMapId(mapId);
    try {
      await deleteOfflineMap(mapId);
      await loadMaps();
    } catch {
      setError("No pudimos eliminar ese mapa offline.");
    } finally {
      setDeletingMapId(null);
    }
  };

  return (
    <AppScreen activeTab="perfil">
      <ScreenTitle
        eyebrow="Mapas offline"
        title="Mapas descargados"
        subtitle="Zonas guardadas localmente en este dispositivo."
      />

      <Card tone="green">
        <Text style={styles.cardTitle}>{formatStorage(totalSize)}</Text>
      </Card>

      <ScrollView showsVerticalScrollIndicator={false}>
        {error ? <Text style={styles.cardText}>{error}</Text> : null}
        {isLoading ? <Text style={styles.cardText}>Cargando mapas...</Text> : null}

        {!isLoading && maps.length === 0 ? (
          <Card>
            <Text style={styles.cardTitle}>No hay mapas descargados</Text>
            <Text style={styles.cardText}>
              Cuando guardes una zona offline, va a aparecer aca con su estado y
              espacio usado real.
            </Text>
          </Card>
        ) : (
          maps.map((map) => {
            const isReady = isOfflineMapReady(map);

            return (
              <DownloadedMapCard
                key={map.id}
                title={map.name}
                meta={`${formatMapStatus(map)} - ${formatStorage(map.sizeMb)} - ${formatDate(map.updatedAt)}`}
                action={isReady ? "Abrir" : "Reintentar"}
                secondaryAction={deletingMapId === map.id ? "Eliminando" : "Eliminar"}
                tone={isReady ? undefined : "danger"}
                onPress={async () => {
                  if (!map.trail) return;

                  const verifiedMap = await getVerifiedOfflineMapByTrailId(map.trail.id);

                  if (!verifiedMap) {
                    router.push({
                      pathname: "/offline-descarga",
                      params: { id: String(map.trail.id) },
                    });
                    return;
                  }

                  router.push({
                    pathname: "/route-map",
                    params: { id: String(map.trail.id), offline: "1" },
                  });
                }}
                onSecondaryPress={() => removeMap(map.id)}
              />
            );
          })
        )}
      </ScrollView>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Descargar zona" icon="download-outline" href="/offline-buscar" />
        <PrimaryButton label="Volver a perfil" href="/perfil" tone="secondary" />
      </View>
    </AppScreen>
  );
}

function isOfflineMapReady(map: OfflineMap) {
  return map.status === "disponible" && map.totalTiles > 0 && map.downloadedTiles >= map.totalTiles;
}

function formatMapStatus(map: OfflineMap) {
  return offlineMapStatusLabel(map);
}

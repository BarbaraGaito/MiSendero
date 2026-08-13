import { router, useFocusEffect } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
} from "../../components/MiSenderoUI";
import { getOfflineMaps, OfflineMap } from "../../../services/offlineMaps";
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
  const [error, setError] = useState<string | null>(null);

  const loadMaps = useCallback(async () => {
    try {
      setMaps(await getOfflineMaps());
      setError(null);
    } catch (loadError) {
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
          maps.map((map) => (
            <DownloadedMapCard
              key={map.id}
              title={map.name}
              meta={`${map.status} - ${formatStorage(map.sizeMb)} - ${formatDate(map.updatedAt)}`}
              action="Abrir"
              onPress={() => {
                if (!map.trail) return;

                router.push({
                  pathname: "/route-map",
                  params: { id: String(map.trail.id) },
                });
              }}
            />
          ))
        )}
      </ScrollView>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Descargar zona" icon="download-outline" href="/offline-buscar" />
        <PrimaryButton label="Volver a perfil" href="/perfil" tone="secondary" />
      </View>
    </AppScreen>
  );
}

import { useFocusEffect } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
  colors,
} from "../components/MiSenderoUI";
import { getOfflineMaps, OfflineMap } from "../../services/offlineMaps";

const formatDate = (timestamp: number) =>
  new Date(timestamp).toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "short",
  });

const formatStorage = (sizeMb: number) =>
  `${sizeMb.toLocaleString("es-AR", { maximumFractionDigits: 0 })} MB`;

export default function OfflineMapsScreen() {
  const [maps, setMaps] = useState<OfflineMap[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMaps = useCallback(async () => {
    try {
      setMaps(await getOfflineMaps());
      setError(null);
    } catch (loadError) {
      setError("No pudimos cargar los mapas offline.");
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
        eyebrow="Sin conexion"
        title="Mapas descargados"
        subtitle="Zonas guardadas localmente en este dispositivo."
      />

      <Card tone="green">
        <Text style={styles.storageTitle}>Espacio usado</Text>
        <Text style={styles.storageValue}>{formatStorage(totalSize)}</Text>
      </Card>

      <ScrollView showsVerticalScrollIndicator={false}>
        {error ? <Text style={styles.statusText}>{error}</Text> : null}
        {isLoading ? <Text style={styles.statusText}>Cargando mapas...</Text> : null}

        {!isLoading && maps.length === 0 ? (
          <Card>
            <Text style={styles.emptyTitle}>No hay mapas descargados</Text>
            <Text style={styles.emptyText}>
              Cuando guardes una zona offline, va a aparecer aca con su estado y
              espacio usado real.
            </Text>
          </Card>
        ) : (
          maps.map((map) => (
            <MapItem
              key={map.id}
              title={map.name}
              meta={`${map.status} - ${formatStorage(map.sizeMb)} - ${formatDate(map.updatedAt)}`}
            />
          ))
        )}
      </ScrollView>

      <PrimaryButton label="Descargar otro mapa" href="/offline-buscar" />
    </AppScreen>
  );
}

function MapItem({ title, meta }: { title: string; meta: string }) {
  return (
    <Card>
      <View style={styles.mapRow}>
        <View style={styles.mapText}>
          <Text style={styles.mapTitle}>{title}</Text>
          <Text style={styles.mapMeta}>{meta}</Text>
        </View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  storageTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  storageValue: {
    color: colors.primary,
    fontSize: 15,
    fontWeight: "800",
    marginTop: 4,
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
  mapRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  mapText: {
    flex: 1,
  },
  mapTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  mapMeta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 4,
    textTransform: "capitalize",
  },
});

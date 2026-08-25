import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useState } from "react";
import { Text, View } from "react-native";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
} from "../../components/MiSenderoUI";
import { getTrailById, getTrailReports } from "../../../services/api";
import { saveOfflineTrailMap } from "../../../services/offlineMaps";
import { Trail } from "../../../types";
import { InfoRow, ProgressHero, styles } from "./OfflineFlowShared";

type DownloadStatus = "loading" | "saved" | "error";

export default function OfflineDownload21Screen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id);
  const [trail, setTrail] = useState<Trail | null>(null);
  const [status, setStatus] = useState<DownloadStatus>("loading");
  const [message, setMessage] = useState("Preparando descarga...");

  useEffect(() => {
    let isMounted = true;

    const downloadTrail = async () => {
      if (!trailId) {
        setStatus("error");
        setMessage("No se encontro la ruta seleccionada.");
        return;
      }

      try {
        setStatus("loading");
        setMessage("Descargando datos de la ruta...");

        const trailData = await getTrailById(trailId);
        const reports = await getTrailReports(trailId).catch(() => []);

        await saveOfflineTrailMap(trailData, reports, (downloaded, total) => {
          if (isMounted) {
            setMessage(`Descargando tiles ${downloaded}/${total}...`);
          }
        });

        if (!isMounted) return;

        setTrail(trailData);
        setStatus("saved");
        setMessage("Mapa disponible sin conexion.");
      } catch (downloadError) {
        if (!isMounted) return;

        setStatus("error");
        setMessage("No pudimos descargar esta ruta. Revisa tu conexion e intenta de nuevo.");
      }
    };

    downloadTrail();

    return () => {
      isMounted = false;
    };
  }, [trailId]);

  const isSaved = status === "saved";
  const isError = status === "error";

  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Descarga"
        title={isSaved ? "Mapa descargado" : "Descargando zona"}
        subtitle="Guardamos los datos de la ruta para usarlos sin conexion."
      />

      <ProgressHero
        percent={isSaved ? "100%" : isError ? "0%" : "..." }
        status={isSaved ? "Listo" : isError ? "Error" : "En curso"}
        tone={isError ? "red" : "green"}
      />

      <Card>
        <InfoRow
          icon="map-outline"
          label="Ruta"
          value={trail?.name || "Ruta seleccionada"}
        />
        <InfoRow
          icon="cloud-done-outline"
          label="Estado"
          value={message}
        />
        <Text style={styles.cardText}>
          Se guardan coordenadas, centro del mapa, metadata de la ruta y reportes
          recientes disponibles.
        </Text>
      </Card>

      <View style={styles.bottomActions}>
        {isSaved ? (
          <>
            <PrimaryButton
              label="Ver mapas descargados"
              href="/offline-mapas-descargados"
            />
            <PrimaryButton
              label="Abrir ruta"
              tone="secondary"
              onPress={() =>
                router.push({
                  pathname: "/route-map",
                  params: { id: String(trailId) },
                })
              }
            />
          </>
        ) : (
          <>
            <PrimaryButton
              label="Reintentar"
              onPress={() =>
                router.replace({
                  pathname: "/offline-descarga",
                  params: { id: String(trailId) },
                })
              }
            />
            <PrimaryButton label="Volver" href="/offline-buscar" tone="secondary" />
          </>
        )}
      </View>
    </AppScreen>
  );
}

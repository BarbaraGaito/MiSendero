import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
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
  const [progress, setProgress] = useState({ downloaded: 0, total: 0 });

  useEffect(() => {
    let isMounted = true;
    let isCancelled = false;

    const downloadTrail = async () => {
      if (!trailId) {
        setStatus("error");
        setMessage("No se encontro la ruta seleccionada.");
        return;
      }

      try {
        setStatus("loading");
        setMessage("Descargando datos de la ruta...");
        setProgress({ downloaded: 0, total: 0 });

        const trailData = await getTrailById(trailId);
        if (isMounted) {
          setTrail(trailData);
        }
        const reports = await getTrailReports(trailId).catch(() => []);

        await saveOfflineTrailMap(
          trailData,
          reports,
          (downloaded, total) => {
            if (isMounted) {
              setProgress({ downloaded, total });
              setMessage(total > 0 ? `Descargando mapa: ${Math.min(100, Math.round(downloaded / total * 100))}%` : "Preparando el mapa...");
            }
          },
          { shouldCancel: () => isCancelled }
        );

        if (!isMounted) return;

        setTrail(trailData);
        setStatus("saved");
        setMessage("Mapa básico y recorrido disponibles sin conexión.");
      } catch (downloadError) {
        if (!isMounted) return;

        setStatus("error");
        setMessage(getDownloadErrorMessage(downloadError));
      }
    };

    downloadTrail();

    return () => {
      isMounted = false;
      isCancelled = true;
    };
  }, [trailId]);

  const isSaved = status === "saved";
  const isError = status === "error";
  const percent =
    isSaved || (progress.total > 0 && progress.downloaded >= progress.total)
      ? "100%"
      : isError
        ? "0%"
        : progress.total > 0
          ? `${Math.max(1, Math.round((progress.downloaded / progress.total) * 100))}%`
          : "...";

  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Descarga"
        title={isSaved ? "Mapa descargado" : "Descargando zona"}
        subtitle="Guardamos los datos de la ruta para usarlos sin conexion."
      />

      <ProgressHero
        percent={percent}
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
          Guardá el recorrido y sus reportes para consultarlos cuando no tengas señal.
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
        ) : isError ? (
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
        ) : (
          <>
            <PrimaryButton
              label="Descargando mapa"
              icon="download-outline"
              isLoading
              loadingLabel="Descargando mapa"
            />
            <PrimaryButton
              label="Volver"
              href="/offline-buscar"
              tone="secondary"
              disabled
            />
          </>
        )}
      </View>
    </AppScreen>
  );
}

function getDownloadErrorMessage(error: unknown) {
  if (error instanceof Error && "code" in error) {
    if (error.code === "provider-not-configured") return "Las descargas de mapas todavía no están disponibles. Podés consultar el sendero con conexión.";
    if (error.code === "storage-unavailable") return "Este dispositivo no permite guardar mapas sin conexión. Probá desde tu teléfono.";
  }
  if (error instanceof Error && error.message.startsWith("offline-map-incomplete")) {
    return "La descarga quedo incompleta. Reintenta con una conexion estable antes de salir.";
  }

  return "No pudimos descargar el mapa completo. Revisa tu conexion e intenta de nuevo.";
}

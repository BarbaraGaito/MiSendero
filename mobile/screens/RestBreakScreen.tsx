import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { getTrailById } from "../../services/api";
import { getWearableRuntimeStatus } from "../../services/wearableMetrics";
import { Trail, WearableRuntimeStatus } from "../../types";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function RestBreakScreen() {
  const { id, startedAt, totalMeters, traveledMeters } = useLocalSearchParams<{
    id?: string;
    startedAt?: string;
    totalMeters?: string;
    traveledMeters?: string;
  }>();
  const trailId = Number(id) || 1;
  const fallbackStartedAt = useMemo(() => Date.now(), []);
  const startedAtMs = Number(startedAt) || fallbackStartedAt;
  const pauseStartedAt = useMemo(() => Date.now(), []);
  const parsedTotalMeters = Number(totalMeters);
  const parsedTraveledMeters = Number(traveledMeters);
  const [trail, setTrail] = useState<Trail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wearableRuntime, setWearableRuntime] =
    useState<WearableRuntimeStatus | null>(null);
  const activeMinutes = Math.max(0, Math.floor((pauseStartedAt - startedAtMs) / 60000));

  useEffect(() => {
    getTrailById(trailId)
      .then((data) => {
        setTrail(data);
        setError(null);
      })
      .catch(() => {
        setError("No pudimos cargar los datos del sendero.");
      });
  }, [trailId]);

  useEffect(() => {
    getWearableRuntimeStatus(activeMinutes)
      .then(setWearableRuntime)
      .catch(() => setWearableRuntime(null));
  }, [activeMinutes]);

  const realTotalMeters =
    Number.isFinite(parsedTotalMeters) && parsedTotalMeters > 0
      ? parsedTotalMeters
      : trail?.distance_km
        ? trail.distance_km * 1000
        : 0;
  const realTraveledMeters =
    Number.isFinite(parsedTraveledMeters) && parsedTraveledMeters >= 0
      ? Math.min(parsedTraveledMeters, realTotalMeters || parsedTraveledMeters)
      : null;
  const remainingMeters =
    realTraveledMeters !== null && realTotalMeters > 0
      ? Math.max(0, realTotalMeters - realTraveledMeters)
      : null;
  const progressPercent =
    realTraveledMeters !== null && realTotalMeters > 0
      ? Math.min(100, Math.round((realTraveledMeters / realTotalMeters) * 100))
      : 0;
  const averageSpeedKmh =
    realTraveledMeters !== null && activeMinutes > 0
      ? (realTraveledMeters / 1000) / (activeMinutes / 60)
      : null;

  return (
    <AppScreen activeTab="actividad">
      <ScreenTitle
        eyebrow="Recorrido en pausa"
        title="Tomate un respiro"
        subtitle="El seguimiento queda pausado. Podes retomarlo cuando estes lista."
      />

      <Card tone="green">
        <Text style={styles.cardTitle}>{trail?.name || "Ruta en curso"}</Text>
        <Text style={styles.cardText}>
          {realTraveledMeters !== null && realTotalMeters > 0
            ? `Progreso actual: ${formatMeters(realTraveledMeters)} de ${formatMeters(realTotalMeters)}`
            : "Progreso actual: esperando datos GPS de la ruta"}
        </Text>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progressPercent}%` }]} />
        </View>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Estado del recorrido</Text>
        <InfoRow label="Tiempo activo" value={formatDuration(activeMinutes)} />
        <InfoRow
          label="Distancia recorrida"
          value={realTraveledMeters !== null ? formatMeters(realTraveledMeters) : "Sin GPS"}
        />
        <InfoRow
          label="Distancia restante"
          value={remainingMeters !== null ? formatMeters(remainingMeters) : "No disponible"}
        />
        <InfoRow
          label="Velocidad promedio"
          value={averageSpeedKmh !== null ? `${averageSpeedKmh.toFixed(1)} km/h` : "Calculando"}
        />
        <InfoRow label="Pausa iniciada" value={formatTime(pauseStartedAt)} />
      </Card>

      <Card tone={wearableRuntime?.prediction?.level === "high" ? "red" : "white"}>
        <Text style={styles.cardTitle}>Metricas del reloj</Text>
        {wearableRuntime?.latestSample ? (
          <>
            <InfoRow
              label="Frecuencia cardiaca"
              value={`${wearableRuntime.latestSample.heartRateBpm ?? "--"} bpm`}
            />
            <InfoRow
              label="Velocidad detectada"
              value={
                wearableRuntime.latestSample.speedKmh !== null
                  ? `${wearableRuntime.latestSample.speedKmh} km/h`
                  : "No disponible"
              }
            />
            <InfoRow
              label="Lectura"
              value={formatTime(wearableRuntime.latestSample.recordedAt)}
            />
            {wearableRuntime.prediction ? (
              <Text style={styles.cardText}>
                {wearableRuntime.prediction.message}
              </Text>
            ) : null}
          </>
        ) : (
          <Text style={styles.cardText}>
            No hay metricas recientes del reloj para este usuario.
          </Text>
        )}
      </Card>

      <Card tone="orange">
        <Text style={styles.cardTitle}>Sugerencia</Text>
        <Text style={styles.cardText}>
          Aprovecha la pausa para revisar agua, abrigo y senal antes de seguir.
        </Text>
      </Card>

      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      <View style={styles.actions}>
        <PrimaryButton
          label="Reanudar recorrido"
          onPress={() =>
            router.push({
              pathname: "/route-map",
              params: {
                active: "1",
                id: String(trailId),
                startedAt: String(startedAtMs),
              },
            })
          }
        />
        <PrimaryButton
          label="Finalizar y guardar"
          tone="secondary"
          onPress={() =>
            router.push({
              pathname: "/recorrido-finalizado",
              params: {
                id: String(trailId),
                startedAt: String(startedAtMs),
                traveledMeters:
                  realTraveledMeters !== null ? String(Math.round(realTraveledMeters)) : "",
                routeProgressMeters:
                  realTraveledMeters !== null ? String(Math.round(realTraveledMeters)) : "",
                totalMeters:
                  realTotalMeters > 0 ? String(Math.round(realTotalMeters)) : "",
              },
            })
          }
        />
      </View>
    </AppScreen>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

function formatMeters(meters: number) {
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

function formatDuration(totalMinutes: number) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours <= 0) return `${minutes} min`;
  return `${hours} h ${minutes.toString().padStart(2, "0")} min`;
}

function formatTime(timestamp: number) {
  return new Intl.DateTimeFormat("es-AR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

const styles = StyleSheet.create({
  cardTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 4,
  },
  progressTrack: {
    backgroundColor: colors.surface,
    borderRadius: 999,
    height: 10,
    marginTop: 10,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: "100%",
  },
  row: {
    alignItems: "center",
    borderTopColor: colors.border,
    borderTopWidth: 1,
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    paddingVertical: 12,
  },
  rowLabel: {
    color: colors.muted,
    flex: 1,
    fontSize: 14,
    fontWeight: "600",
  },
  rowValue: {
    color: colors.ink,
    flexShrink: 0,
    fontSize: 14,
    fontWeight: "800",
    textAlign: "right",
  },
  actions: {
    gap: 10,
    marginTop: "auto",
  },
  errorText: {
    color: colors.danger,
    fontSize: 13,
    fontWeight: "800",
    marginTop: 8,
  },
});

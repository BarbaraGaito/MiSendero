import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, Metric, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function ActivitiesScreen() {
  return (
    <AppScreen activeTab="actividad">
      <ScreenTitle
        eyebrow="Actividad"
        title="Mis actividades"
        subtitle="Resumen de tus recorridos guardados y pendientes."
      />

      <View style={styles.metricsRow}>
        <Metric label="Total" value="27,8 km" />
        <Metric label="Rutas" value="3" />
        <Metric label="Este mes" value="2" />
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        <ActivityCard
          title="Laguna Esmeralda"
          meta="Finalizada • 9,4 km"
          status="Guardada"
        />
        <ActivityCard
          title="Cerro Campanario"
          meta="Pausada • 3,2 km"
          status="Pendiente"
        />
        <ActivityCard
          title="Sendero Arrayanes"
          meta="Finalizada • 6,8 km"
          status="Guardada"
        />
        <PrimaryButton label="Ver historial local" href="/history" tone="secondary" />
      </ScrollView>
    </AppScreen>
  );
}

function ActivityCard({
  title,
  meta,
  status,
}: {
  title: string;
  meta: string;
  status: string;
}) {
  const pending = status === "Pendiente";

  return (
    <Card tone={pending ? "orange" : "white"}>
      <View style={styles.activityTop}>
        <View>
          <Text style={styles.activityTitle}>{title}</Text>
          <Text style={styles.activityMeta}>{meta}</Text>
        </View>
        <Text style={[styles.status, pending && styles.statusPending]}>{status}</Text>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  metricsRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 14,
  },
  activityTop: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  activityTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  activityMeta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 4,
  },
  status: {
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  statusPending: {
    backgroundColor: colors.orangeSoft,
    color: colors.orange,
  },
});

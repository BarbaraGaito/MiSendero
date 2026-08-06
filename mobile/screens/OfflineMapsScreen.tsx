import React from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function OfflineMapsScreen() {
  return (
    <AppScreen activeTab="perfil">
      <ScreenTitle
        eyebrow="Sin conexión"
        title="Mapas descargados"
        subtitle="Administrá el espacio y actualizá las zonas antes de salir."
      />

      <Card tone="green">
        <Text style={styles.storageTitle}>Espacio usado</Text>
        <Text style={styles.storageValue}>482 MB de 2 GB</Text>
        <View style={styles.progressTrack}>
          <View style={styles.progressFill} />
        </View>
      </Card>

      <ScrollView showsVerticalScrollIndicator={false}>
        <MapItem title="Bariloche y alrededores" meta="Actualizado hoy" action="Listo" />
        <MapItem title="Villa La Angostura" meta="Actualizado hace 12 días" action="Actualizar" />
        <MapItem title="Ushuaia" meta="Descargado parcialmente" action="Completar" />
      </ScrollView>

      <PrimaryButton label="Descargar otro mapa" href="/offline-buscar" />
    </AppScreen>
  );
}

function MapItem({ title, meta, action }: { title: string; meta: string; action: string }) {
  return (
    <Card>
      <View style={styles.mapRow}>
        <View>
          <Text style={styles.mapTitle}>{title}</Text>
          <Text style={styles.mapMeta}>{meta}</Text>
        </View>
        <Text style={styles.mapAction}>{action}</Text>
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
  },
  progressTrack: {
    backgroundColor: colors.surface,
    borderRadius: 999,
    height: 10,
    marginTop: 4,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: "100%",
    width: "24%",
  },
  mapRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
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
  },
  mapAction: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "900",
  },
});

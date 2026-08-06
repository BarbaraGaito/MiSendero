import React from "react";
import { ScrollView, Text, View } from "react-native";
import { router } from "expo-router";
import { AppScreen, Card, PrimaryButton, ScreenTitle } from "../../components/MiSenderoUI";
import { DownloadedMapCard, styles } from "./OfflineFlowShared";

export default function OfflineDownloadedMaps23Screen() {
  return (
    <AppScreen activeTab="perfil">
      <ScreenTitle
        eyebrow="Mapas offline"
        title="Mapas descargados"
        subtitle="Administrá las zonas guardadas en este dispositivo."
      />

      <Card tone="green">
        <Text style={styles.cardTitle}>482 MB de 2 GB</Text>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: "24%" }]} />
        </View>
      </Card>

      <ScrollView showsVerticalScrollIndicator={false}>
        <DownloadedMapCard
          title="Bariloche y alrededores"
          meta="Disponible offline · 486 MB"
          action="Borrar"
          tone="danger"
        />
        <DownloadedMapCard
          title="Villa La Angostura"
          meta="Actualizado hace 12 dias · 234 MB"
          action="Actualizar"
          onPress={() => router.push("/actualizacion-fallida")}
        />
      </ScrollView>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Descargar zona" icon="download-outline" href="/offline-buscar" />
        <PrimaryButton label="Volver a perfil" href="/perfil" tone="secondary" />
      </View>
    </AppScreen>
  );
}

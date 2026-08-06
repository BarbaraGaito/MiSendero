import React from "react";
import { View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle } from "../../components/MiSenderoUI";
import { InfoRow, ProgressHero, styles } from "./OfflineFlowShared";

export default function OfflineDownload21Screen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Descarga"
        title="Descargando zona"
        subtitle="Podés seguir usando MiSendero mientras se guarda el mapa."
      />

      <ProgressHero percent="68%" status="En curso" tone="green" />

      <Card>
        <InfoRow icon="map-outline" label="Parque Nacional Nahuel Huapi" value="159 MB" />
        <InfoRow icon="time-outline" label="Tiempo restante" value="4 min" />
      </Card>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Simular conexion perdida" href="/conexion-perdida" tone="secondary" />
        <PrimaryButton label="Finalizar descarga" href="/offline-descarga-completa" />
      </View>
    </AppScreen>
  );
}

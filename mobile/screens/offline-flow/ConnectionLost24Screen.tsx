import React from "react";
import { Text, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle } from "../../components/MiSenderoUI";
import { InfoRow, ProgressHero, styles } from "./OfflineFlowShared";

export default function ConnectionLost24Screen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Conexion perdida"
        title="Descarga en pausa"
        subtitle="El progreso queda guardado hasta recuperar señal."
      />

      <ProgressHero percent="68%" status="En pausa" tone="orange" />

      <Card>
        <InfoRow icon="map-outline" label="Bariloche y alrededores" value="159 MB" />
        <Text style={styles.cardText}>
          Esperando conexion para continuar la descarga automaticamente.
        </Text>
      </Card>

      <Card tone="green">
        <InfoRow icon="checkmark-circle-outline" label="Villa La Angostura" value="Lista" />
      </Card>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Reintentar descarga" href="/offline-descarga" />
        <PrimaryButton label="Volver a mapas offline" href="/offline-mapas-descargados" tone="secondary" />
      </View>
    </AppScreen>
  );
}

import React from "react";
import { Text, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle } from "../../components/MiSenderoUI";
import { InfoRow, ProgressHero, styles } from "./OfflineFlowShared";

export default function UpdateFailed25Screen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Actualizacion fallida"
        title="No pudimos actualizar el mapa"
        subtitle="Conservamos la version offline que ya tenias guardada."
      />

      <ProgressHero percent="68%" status="Guardado" tone="red" />

      <Card tone="red">
        <Text style={styles.cardTitle}>Progreso protegido</Text>
        <Text style={styles.cardText}>
          La descarga se interrumpio, pero el mapa anterior sigue disponible.
        </Text>
      </Card>

      <Card>
        <InfoRow icon="map-outline" label="Bariloche y alrededores" value="159 MB" />
        <InfoRow icon="checkmark-circle-outline" label="Villa La Angostura" value="Vigente" />
      </Card>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Reintentar actualizacion" href="/offline-descarga" />
        <PrimaryButton label="Volver a perfil" href="/perfil" tone="secondary" />
      </View>
    </AppScreen>
  );
}

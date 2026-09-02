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
        <InfoRow icon="map-outline" label="Actualizacion offline" value="Interrumpida" />
        <InfoRow icon="checkmark-circle-outline" label="Mapas guardados" value="Ver base local" />
      </Card>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Reintentar actualizacion" href="/offline-descarga" />
        <PrimaryButton label="Volver a perfil" href="/perfil" tone="secondary" />
      </View>
    </AppScreen>
  );
}

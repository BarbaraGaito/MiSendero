import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../../components/MiSenderoUI";
import { InfoRow, styles } from "./OfflineFlowShared";

export default function OfflineZoneDetail20Screen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Zona offline"
        title="Zona seleccionada"
        subtitle="Paquete preparado para salir sin depender de la señal."
      />

      <View style={styles.mapPreview}>
        <View style={[styles.contour, styles.contourOne]} />
        <View style={[styles.contour, styles.contourTwo]} />
        <View style={[styles.routeLine, styles.routeOne]} />
        <View style={[styles.routeLine, styles.routeTwo]} />
        <View style={styles.mapPin}>
          <Ionicons name="location" size={18} color={colors.white} />
        </View>
      </View>

      <Card>
        <InfoRow icon="map-outline" label="Rutas incluidas" value="Segun base" />
        <InfoRow icon="download-outline" label="Tamano" value="A calcular" />
        <InfoRow icon="shield-checkmark-outline" label="Seguridad" value="Puntos SOS" />
      </Card>

      <Card tone="orange">
        <Text style={styles.cardTitle}>Antes de descargar</Text>
        <Text style={styles.cardText}>
          Conectate a Wi-Fi si querés ahorrar datos moviles.
        </Text>
      </Card>

      <PrimaryButton label="Descargar zona" icon="download-outline" href="/offline-descarga" />
    </AppScreen>
  );
}

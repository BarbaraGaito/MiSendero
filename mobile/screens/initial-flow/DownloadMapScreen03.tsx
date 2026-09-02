import { Ionicons } from "@expo/vector-icons";
import { StyleSheet, Text, View } from "react-native";
import {
  Card,
  PrimaryButton,
  ScreenShell,
  ScreenTitle,
  colors,
} from "../../components/MiSenderoUI";

export default function DownloadMapScreen03() {
  return (
    <ScreenShell>
      <ScreenTitle
        eyebrow="Descargar mapa"
        title="Guarda el mapa offline"
        subtitle="Descarga la zona antes de salir para navegar aunque pierdas senal."
      />

      <Card tone="green">
        <View style={styles.mapPreview}>
          <View style={[styles.contour, styles.contourOne]} />
          <View style={[styles.contour, styles.contourTwo]} />
          <View style={[styles.routeSegment, styles.segmentOne]} />
          <View style={[styles.routeSegment, styles.segmentTwo]} />
          <View style={styles.pin}>
            <Ionicons name="download-outline" size={22} color={colors.white} />
          </View>
        </View>
        <Text style={styles.cardTitle}>Mapa de la ruta</Text>
        <Text style={styles.cardText}>Mapa, desvios, puntos SOS y relieve.</Text>
      </Card>

      <Card>
        <Info label="Cobertura" value="Disponible sin conexion" />
        <Info label="Bateria recomendada" value="60% o mas" />
        <Info label="Ultima actualizacion" value="Segun base disponible" />
      </Card>

      <View style={styles.footer}>
        <PrimaryButton label="Descargar y continuar" icon="download-outline" href="/trail-start" />
        <PrimaryButton label="Explorar mientras carga" href="/explorar-skeletons" tone="secondary" />
      </View>
    </ScreenShell>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  mapPreview: {
    backgroundColor: "#E8F2E9",
    borderRadius: 24,
    height: 250,
    marginBottom: 16,
    overflow: "hidden",
    position: "relative",
  },
  contour: {
    borderColor: "#C4DCCD",
    borderRadius: 999,
    borderWidth: 2,
    height: 102,
    position: "absolute",
    transform: [{ rotate: "-14deg" }],
  },
  contourOne: {
    left: 40,
    top: 58,
    width: 260,
  },
  contourTwo: {
    left: 74,
    top: 96,
    width: 194,
  },
  routeSegment: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: 9,
    position: "absolute",
  },
  segmentOne: {
    left: 64,
    top: 168,
    transform: [{ rotate: "-28deg" }],
    width: 138,
  },
  segmentTwo: {
    left: 166,
    top: 140,
    transform: [{ rotate: "24deg" }],
    width: 118,
  },
  pin: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: 48,
    justifyContent: "center",
    position: "absolute",
    right: 62,
    top: 110,
    width: 48,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 4,
  },
  infoRow: {
    borderTopColor: colors.line,
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 12,
  },
  infoLabel: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
  },
  infoValue: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "900",
  },
  footer: {
    gap: 10,
    marginTop: "auto",
  },
});

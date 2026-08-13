import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Card, PrimaryButton, ScreenShell, ScreenTitle, colors } from "../../components/MiSenderoUI";

export default function LoadingRouteScreen02() {
  return (
    <ScreenShell>
      <ScreenTitle
        eyebrow="Cargando ruta"
        title="Preparando sendero"
        subtitle="Estamos revisando mapa offline, clima y puntos de seguridad."
      />

      <Card style={styles.loaderCard}>
        <View style={styles.ring}>
          <Ionicons name="trail-sign-outline" size={42} color={colors.primary} />
        </View>
        <Text style={styles.loadingTitle}>Ruta seleccionada</Text>
        <Text style={styles.loadingText}>Sincronizando detalles de la ruta...</Text>
        <View style={styles.progressTrack}>
          <View style={styles.progressFill} />
        </View>
      </Card>

      <Card>
        <StatusRow icon="map-outline" label="Mapa base" value="Listo" />
        <StatusRow icon="cloud-outline" label="Clima" value="Actualizado" />
        <StatusRow icon="shield-checkmark-outline" label="Seguridad" value="Verificada" />
      </Card>

      <View style={styles.footer}>
        <PrimaryButton label="Ver detalle" href="/trail-detail" />
        <PrimaryButton label="Descargar mapa" href="/descargar-mapa" tone="secondary" />
      </View>
    </ScreenShell>
  );
}

function StatusRow({
  icon,
  label,
  value,
}: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  value: string;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowLeft}>
        <Ionicons name={icon} size={18} color={colors.primary} />
        <Text style={styles.rowLabel}>{label}</Text>
      </View>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  loaderCard: {
    alignItems: "center",
  },
  ring: {
    alignItems: "center",
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
    borderRadius: 999,
    borderWidth: 10,
    height: 128,
    justifyContent: "center",
    width: 128,
  },
  loadingTitle: {
    color: colors.ink,
    fontSize: 20,
    fontWeight: "900",
    marginTop: 16,
  },
  loadingText: {
    color: colors.muted,
    fontSize: 14,
    marginTop: 6,
  },
  progressTrack: {
    backgroundColor: colors.surface,
    borderRadius: 999,
    height: 10,
    marginTop: 18,
    overflow: "hidden",
    width: "100%",
  },
  progressFill: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: "100%",
    width: "72%",
  },
  row: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 12,
  },
  rowLeft: {
    alignItems: "center",
    flexDirection: "row",
    gap: 9,
  },
  rowLabel: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "700",
  },
  rowValue: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "900",
  },
  footer: {
    gap: 10,
    marginTop: "auto",
  },
});

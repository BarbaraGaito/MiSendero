import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../../components/MiSenderoUI";
import { Chip, InfoRow, styles } from "./OfflineFlowShared";

export default function OfflineFilters19Screen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Filtros"
        title="Filtrar mapas"
        subtitle="Ajustá la busqueda por region, dificultad y tamaño de descarga."
      />

      <Card tone="green">
        <View style={styles.inlineTitle}>
          <Ionicons name="options-outline" size={18} color={colors.primary} />
          <Text style={styles.cardTitle}>2 filtros activos</Text>
        </View>
      </Card>

      <Card>
        <Text style={styles.sectionLabel}>REGION</Text>
        <View style={styles.chips}>
          <Chip label="Patagonia" active />
          <Chip label="Cuyo" />
          <Chip label="NOA" />
        </View>
        <Text style={styles.helper}>Rio Negro y Neuquen</Text>
      </Card>

      <Card>
        <Text style={styles.sectionLabel}>DESCARGA</Text>
        <InfoRow icon="phone-portrait-outline" label="Hasta 500 MB" value="Activo" />
        <InfoRow icon="wifi-outline" label="Disponible offline" value="Si" />
        <InfoRow icon="walk-outline" label="Dificultad" value="Facil y media" />
      </Card>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Aplicar filtros" href="/offline-buscar" />
        <PrimaryButton label="Limpiar filtros" href="/offline-buscar" tone="secondary" />
      </View>
    </AppScreen>
  );
}

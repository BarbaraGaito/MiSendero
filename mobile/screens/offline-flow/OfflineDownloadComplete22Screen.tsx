import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../../components/MiSenderoUI";
import { InfoRow, styles } from "./OfflineFlowShared";

export default function OfflineDownloadComplete22Screen() {
  return (
    <AppScreen withBottomNav={false}>
      <View style={styles.successCircle}>
        <Ionicons name="checkmark" size={42} color={colors.primary} />
      </View>
      <ScreenTitle
        eyebrow="Lista"
        title="Zona descargada"
        subtitle="El mapa ya esta disponible para navegar sin conexion."
      />

      <Card tone="green">
        <Text style={styles.cardTitle}>Zona lista</Text>
        <Text style={styles.cardText}>
          Guardamos rutas, relieve, alertas y puntos de referencia.
        </Text>
      </Card>

      <Card>
        <InfoRow icon="cloud-done-outline" label="Estado" value="Disponible offline" />
        <InfoRow icon="server-outline" label="Espacio usado" value="Segun base local" />
      </Card>

      <View style={styles.bottomActions}>
        <PrimaryButton label="Ver mapas descargados" href="/offline-mapas-descargados" />
        <PrimaryButton label="Buscar otra zona" href="/offline-buscar" tone="secondary" />
      </View>
    </AppScreen>
  );
}

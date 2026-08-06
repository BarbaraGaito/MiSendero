import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { AppScreen, PrimaryButton, ScreenTitle, colors } from "../../components/MiSenderoUI";
import { OfflineZoneCard, styles } from "./OfflineFlowShared";

export default function OfflineSearch18Screen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Nueva descarga"
        title="Buscar zona offline"
        subtitle="Elegí un destino para guardar rutas, relieve y puntos de seguridad."
      />

      <View style={styles.searchBox}>
        <Ionicons name="search" size={18} color={colors.primary} />
        <Text style={styles.searchText}>Bariloche, Rio Negro</Text>
        <Pressable onPress={() => router.push("/offline-filtros")}>
          <Ionicons name="options-outline" size={20} color={colors.red} />
        </Pressable>
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        <OfflineZoneCard
          title="Parque Nacional Nahuel Huapi"
          meta="Rio Negro · 312 MB"
          body="Incluye senderos moderados, refugios cercanos y cobertura offline."
          action="Ver detalle"
          onPress={() => router.push("/offline-detalle-zona")}
        />
        <OfflineZoneCard
          title="Circuito Chico"
          meta="Bariloche · 184 MB"
          body="Mapa liviano para recorridos cortos y miradores urbanos."
          action="Descargar"
          onPress={() => router.push("/offline-descarga")}
        />
      </ScrollView>

      <PrimaryButton label="Volver a mapas" href="/mapas-offline" tone="secondary" />
    </AppScreen>
  );
}

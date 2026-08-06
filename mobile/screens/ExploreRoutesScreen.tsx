import { Link } from "expo-router";
import React from "react";
import { ImageBackground, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, ScreenTitle, colors } from "../components/MiSenderoUI";

const routeMapPreview = require("../../assets/route-map-preview.png");

export default function ExploreRoutesScreen() {
  return (
    <AppScreen activeTab="explorar">
      <ScreenTitle
        eyebrow="Explorar rutas"
        title="Encontrá tu próxima ruta"
        subtitle="Filtrá por dificultad, distancia y disponibilidad offline."
      />

      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.filterRow}>
          <Text style={styles.filterActive}>Cerca</Text>
          <Text style={styles.filter}>Moderadas</Text>
          <Text style={styles.filter}>Offline</Text>
        </View>

        <Text style={styles.sectionTitle}>Recomendadas para vos</Text>
        <RouteCard title="Sendero Arrayanes" place="Bariloche, Río Negro" distance="6,8 km" />
        <RouteCard title="Cerro Campanario" place="Circuito Chico" distance="3,2 km" />

        <Card tone="green">
          <Text style={styles.cardTitle}>Tip de seguridad</Text>
          <Text style={styles.cardText}>Descargá el mapa antes de salir si la zona tiene poca señal.</Text>
        </Card>
      </ScrollView>
    </AppScreen>
  );
}

function RouteCard({ title, place, distance }: { title: string; place: string; distance: string }) {
  return (
    <Link href="/trail-detail" asChild>
      <Pressable style={styles.routeCard}>
        <ImageBackground source={routeMapPreview} imageStyle={styles.image} style={styles.imageBox}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>Offline</Text>
          </View>
        </ImageBackground>
        <View style={styles.routeBody}>
          <Text style={styles.routeTitle}>{title}</Text>
          <Text style={styles.routePlace}>{place}</Text>
          <Text style={styles.routeMeta}>{distance} • Moderada</Text>
        </View>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  filterRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 18,
  },
  filter: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  filterActive: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    color: colors.surface,
    fontSize: 13,
    fontWeight: "800",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
    marginBottom: 12,
  },
  routeCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 22,
    borderWidth: 1,
    marginBottom: 14,
    overflow: "hidden",
  },
  imageBox: {
    height: 126,
    padding: 12,
  },
  image: {
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
  },
  badge: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.9)",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  badgeText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
  },
  routeBody: {
    gap: 3,
    padding: 14,
  },
  routeTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  routePlace: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "500",
  },
  routeMeta: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "800",
    marginTop: 6,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
});

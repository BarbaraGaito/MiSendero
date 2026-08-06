import React from "react";
import { router } from "expo-router";
import {
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
  colors,
} from "../components/MiSenderoUI";

export default function OfflineMapsSearchScreen() {
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Nueva descarga"
        title="Buscar mapas offline"
        subtitle="Encontrá una zona y descargala antes de salir."
      />

      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons
            name="search"
            size={18}
            color={colors.primary}
          />

          <TextInput
            placeholder="Bariloche"
            placeholderTextColor={colors.muted}
            style={styles.input}
            defaultValue="Bariloche"
          />
        </View>

        <Pressable
          style={styles.filterButton}
          onPress={() => router.push("/filtros-mapas")}
        >
          <Ionicons
            name="options-outline"
            size={18}
            color="#D84C3F"
          />
          <Text style={styles.filterText}>Filtrar</Text>
        </Pressable>
      </View>

      <Card>
        <Image
          source={{
            uri: "https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200",
          }}
          style={styles.image}
        />

        <View style={styles.downloadBadge}>
          <Ionicons
            name="download-outline"
            size={13}
            color={colors.primary}
          />
          <Text style={styles.downloadBadgeText}>
            312 MB
          </Text>
        </View>

        <View style={styles.info}>
          <View style={styles.titleRow}>
            <Ionicons
              name="map-outline"
              size={18}
              color={colors.primary}
            />

            <Text style={styles.title}>
              Parque Nacional Nahuel Huapi
            </Text>
          </View>

          <Text style={styles.subtitle}>
            Río Negro · 312 MB
          </Text>
        </View>

        <PrimaryButton
          label="Descargar"
          icon="download-outline"
          href="/offline-descarga"
        />
      </Card>

      <View style={styles.bottomButtons}>
        <PrimaryButton
          label="Ver resultados"
          icon="download-outline"
          href="/offline-mapas-descargados"
        />

        <Pressable
          style={styles.secondaryButton}
          onPress={() => router.push("/mapas-offline")}
        >
          <Text style={styles.secondaryText}>
            Volver a Mapas
          </Text>
        </Pressable>
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  searchRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 18,
    gap: 10,
  },

  searchBox: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 18,
    paddingHorizontal: 14,
    height: 54,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 10,
  },

  input: {
    flex: 1,
    marginLeft: 8,
    color: colors.ink,
    fontSize: 16,
    fontWeight: "700",
  },

  filterButton: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FFECEC",
    borderRadius: 18,
    paddingHorizontal: 16,
    height: 54,
    gap: 6,
  },

  filterText: {
    color: "#D84C3F",
    fontWeight: "800",
  },

  image: {
    width: "100%",
    height: 170,
    borderRadius: 18,
    marginBottom: 16,
  },

  downloadBadge: {
    position: "absolute",
    right: 18,
    top: 150,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 20,
    paddingHorizontal: 10,
    paddingVertical: 5,
    gap: 4,
    elevation: 2,
  },

  downloadBadgeText: {
    color: colors.primary,
    fontWeight: "800",
    fontSize: 12,
  },

  info: {
    marginBottom: 18,
  },

  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },

  title: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
    flex: 1,
  },

  subtitle: {
    marginTop: 6,
    color: "#D97706",
    fontSize: 13,
    fontWeight: "700",
  },

  bottomButtons: {
    flex: 1,
    justifyContent: "flex-end",
    marginBottom: 12,
    gap: 12,
  },

  secondaryButton: {
    height: 54,
    borderRadius: 27,
    borderWidth: 1.5,
    borderColor: colors.primary,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: colors.white,
  },

  secondaryText: {
    color: colors.primary,
    fontWeight: "800",
    fontSize: 16,
  },
});

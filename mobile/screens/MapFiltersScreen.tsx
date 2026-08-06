import React, { useState } from "react";
import {
  Pressable,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import {
  AppScreen,
  Card,
  PrimaryButton,
  ScreenTitle,
  colors,
} from "../components/MiSenderoUI";
import { Ionicons } from "@expo/vector-icons";

export default function MapFiltersScreen() {
  const [onlySmallMaps, setOnlySmallMaps] = useState(true);
  const [region, setRegion] = useState("Patagonia");

  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle
        eyebrow="Filtros"
        title="Filtrar mapas"
        subtitle="Refiná la búsqueda por zona y tamaño de descarga."
      />

      <Card tone="green">
        <View style={styles.activeFilters}>
          <Ionicons
            name="options-outline"
            size={18}
            color={colors.primary}
          />

          <View>
            <Text style={styles.activeLabel}>
              Filtros activos
            </Text>

            <Text style={styles.activeValue}>
              2 seleccionados
            </Text>
          </View>
        </View>
      </Card>

      <Card>

        <Text style={styles.sectionTitle}>REGIÓN</Text>

        <View style={styles.tags}>

          <FilterChip
            label="Patagonia"
            selected={region === "Patagonia"}
            onPress={() => setRegion("Patagonia")}
          />

          <FilterChip
            label="Cuyo"
            selected={region === "Cuyo"}
            onPress={() => setRegion("Cuyo")}
          />

          <FilterChip
            label="NOA"
            selected={region === "NOA"}
            onPress={() => setRegion("NOA")}
          />

        </View>

        <Text style={styles.helper}>
          Río Negro y Neuquén
        </Text>

        <View style={styles.separator} />

        <Text style={styles.sectionTitle}>TAMAÑO</Text>

        <View style={styles.switchRow}>
          <View>
            <Text style={styles.switchTitle}>
              Hasta 500 MB
            </Text>

            <Text style={styles.switchSubtitle}>
              Ideal para guardar en el teléfono
            </Text>
          </View>

          <Switch
            value={onlySmallMaps}
            onValueChange={setOnlySmallMaps}
            thumbColor="#fff"
            trackColor={{
              false: "#ddd",
              true: colors.primary,
            }}
          />
        </View>

        <View style={styles.separator} />

        <Text style={styles.sectionTitle}>
          RANGO (MB)
        </Text>

        <View style={styles.sliderTrack}>
          <View style={styles.sliderProgress} />
          <View style={styles.sliderThumb} />
        </View>

        <View style={styles.rangeLabels}>
          <Text style={styles.rangeText}>0 MB</Text>
          <Text style={styles.rangeText}>500 MB</Text>
        </View>

      </Card>

      <View style={styles.bottomButtons}>

        <PrimaryButton
          label="Aplicar 2 filtros"
          icon="download-outline"
          href="/offline-buscar"
        />

        <Pressable
          style={styles.secondaryButton}
          onPress={() => {
            setOnlySmallMaps(false);
            setRegion("");
          }}
        >
          <Text style={styles.secondaryText}>
            Limpiar filtros
          </Text>
        </Pressable>

      </View>

    </AppScreen>
  );
}

function FilterChip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.chip,
        selected && styles.chipSelected,
      ]}
    >
      <Ionicons
        name="map-outline"
        size={14}
        color={
          selected
            ? colors.primary
            : colors.muted
        }
      />

      <Text
        style={[
          styles.chipText,
          selected && styles.chipTextSelected,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({

  activeFilters: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },

  activeLabel: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "700",
  },

  activeValue: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },

  sectionTitle: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
    marginBottom: 12,
  },

  tags: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
  },

  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
  },

  chipSelected: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },

  chipText: {
    color: colors.ink,
    fontWeight: "700",
    fontSize: 13,
  },

  chipTextSelected: {
    color: colors.primary,
  },

  helper: {
    color: colors.muted,
    marginTop: 14,
    fontSize: 13,
  },

  separator: {
    height: 1,
    backgroundColor: colors.line,
    marginVertical: 18,
  },

  switchRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },

  switchTitle: {
    color: colors.ink,
    fontWeight: "700",
    fontSize: 15,
  },

  switchSubtitle: {
    color: "#D97706",
    marginTop: 4,
    fontSize: 12,
  },

  sliderTrack: {
    height: 12,
    borderRadius: 8,
    backgroundColor: "#DDE9E0",
    marginTop: 12,
    overflow: "hidden",
  },

  sliderProgress: {
    width: "52%",
    height: "100%",
    backgroundColor: colors.primary,
  },

  sliderThumb: {
    position: "absolute",
    right: "2%",
    top: -5,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.white,
    borderWidth: 3,
    borderColor: colors.primary,
  },

  rangeLabels: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 8,
  },

  rangeText: {
    color: colors.primary,
    fontSize: 12,
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
    borderRadius: 28,
    borderWidth: 1.5,
    borderColor: colors.primary,
    backgroundColor: colors.white,
    justifyContent: "center",
    alignItems: "center",
  },

  secondaryText: {
    color: colors.primary,
    fontWeight: "800",
    fontSize: 16,
  },

});

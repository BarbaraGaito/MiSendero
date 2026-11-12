import { Ionicons } from "@expo/vector-icons";
import { useState } from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import type { DistanceFilter, TrailAreaFilter } from "../../services/trailFilters";
import { colors, typography } from "./MiSenderoUI";

const areas = [
  { id: "all", label: "Todos" },
  { id: "national_parks", label: "Parques nacionales" },
  { id: "other_trails", label: "Otros senderos" },
] as const;
const difficulties = [
  { id: "Todas", label: "Todas" },
  { id: "Baja", label: "Baja" },
  { id: "Media", label: "Media" },
  { id: "Alta", label: "Alta" },
] as const;
const distances = [
  { id: "Todas", label: "Cualquiera" },
  { id: "Corta", label: "Hasta 5 km" },
  { id: "Media", label: "Más de 5 y hasta 10 km" },
  { id: "Larga", label: "Más de 10 km" },
  { id: "Sin dato", label: "Sin dato" },
] as const;

export type CatalogFilters = {
  area: TrailAreaFilter;
  difficulty: (typeof difficulties)[number]["id"];
  distance: DistanceFilter;
};

export const defaultCatalogFilters: CatalogFilters = { area: "all", difficulty: "Todas", distance: "Todas" };

export function TrailCatalogFilters({
  filters, setFilters, query, setQuery, favoritesOnly, onToggleFavorites, expanded, onToggleExpanded, onViewResults,
}: {
  filters: CatalogFilters;
  setFilters: (filters: CatalogFilters) => void;
  query: string;
  setQuery: (query: string) => void;
  favoritesOnly: boolean;
  onToggleFavorites: () => void;
  expanded: boolean;
  onToggleExpanded: () => void;
  onViewResults: () => void;
}) {
  const [searchFocused, setSearchFocused] = useState(false);
  const activeFilters = ([
    { key: "area", label: areas.find((area) => area.id === filters.area)?.label },
    { key: "difficulty", label: `Dificultad: ${filters.difficulty}` },
    { key: "distance", label: distances.find((distance) => distance.id === filters.distance)?.label },
  ] as const).filter(({ key }) => filters[key] !== defaultCatalogFilters[key]);

  return (
    <View style={styles.filters}>
      <View style={styles.toolbar}>
        <View style={[styles.search, searchFocused && styles.searchFocused]}>
          <Ionicons aria-hidden accessible={false} name="search-outline" size={20} color={colors.muted} />
          <TextInput
            accessibilityLabel="Buscar senderos por nombre o lugar"
            autoCorrect={false}
            onBlur={() => setSearchFocused(false)}
            onChangeText={setQuery}
            onFocus={() => setSearchFocused(true)}
            placeholder="Nombre o lugar"
            placeholderTextColor={colors.muted}
            returnKeyType="search"
            style={styles.searchInput}
            value={query}
          />
          {query ? (
            <Pressable accessibilityLabel="Limpiar búsqueda" accessibilityRole="button"
              onPress={() => setQuery("")} style={({ pressed }) => [styles.clearSearch, pressed && styles.pressed]}>
              <Ionicons aria-hidden accessible={false} name="close" size={19} color={colors.green} />
            </Pressable>
          ) : null}
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Filtrar senderos"
          accessibilityHint={activeFilters.length ? `${activeFilters.length} filtros activos` : undefined}
          accessibilityState={{ expanded }}
          aria-expanded={expanded}
          onPress={onToggleExpanded}
          style={({ pressed }) => [
            styles.filterTrigger, (expanded || activeFilters.length > 0) && styles.triggerActive,
            pressed && styles.pressed,
          ]}
        >
          <Ionicons aria-hidden accessible={false} name="options-outline" size={19} color={colors.green} />
          <Text style={styles.triggerLabel}>Filtros</Text>
          {activeFilters.length > 0 ? (
            <View style={styles.filterBadge}><Text style={styles.filterBadgeText}>{activeFilters.length}</Text></View>
          ) : null}
        </Pressable>
      </View>

      {expanded ? (
        <View style={styles.panel}>
          <View style={styles.panelHeading}>
            <Text accessibilityRole="header" style={styles.panelTitle}>Ajustá tu búsqueda</Text>
            {activeFilters.length ? (
              <Pressable accessibilityRole="button" onPress={() => setFilters(defaultCatalogFilters)}
                style={({ pressed }) => [styles.reset, pressed && styles.pressed]}>
                <Text style={styles.resetLabel}>Limpiar filtros</Text>
              </Pressable>
            ) : null}
          </View>
          <FilterGroup title="Tipo de sendero" options={areas} value={filters.area}
            onChange={(area) => setFilters({ ...filters, area })} />
          <FilterGroup title="Dificultad" options={difficulties} value={filters.difficulty}
            onChange={(difficulty) => setFilters({ ...filters, difficulty })} />
          <FilterGroup title="Distancia" options={distances} value={filters.distance}
            onChange={(distance) => setFilters({ ...filters, distance })} />
          <Pressable accessibilityRole="button" onPress={onViewResults}
            style={({ pressed }) => [styles.viewResults, pressed && styles.pressed]}>
            <Text style={styles.viewResultsLabel}>Ver resultados</Text>
            <Ionicons aria-hidden accessible={false} name="arrow-forward" size={17} color={colors.white} />
          </Pressable>
        </View>
      ) : null}

      <View style={styles.chipRow}>
        <Pressable
          accessibilityRole="button" accessibilityState={{ selected: favoritesOnly }} aria-pressed={favoritesOnly}
          onPress={onToggleFavorites}
          style={({ pressed }) => [styles.chip, favoritesOnly && styles.chipSelected, pressed && styles.pressed]}
        >
          <Ionicons aria-hidden accessible={false} name={favoritesOnly ? "star" : "star-outline"} size={16}
            color={favoritesOnly ? colors.white : colors.green} />
          <Text style={[styles.chipLabel, favoritesOnly && styles.chipLabelSelected]}>Favoritos</Text>
        </Pressable>
        {!expanded && activeFilters.map(({ key, label }) => (
          <Pressable key={key} accessibilityRole="button" accessibilityLabel={`Quitar filtro: ${label}`}
            onPress={() => setFilters({ ...filters, [key]: defaultCatalogFilters[key] })}
            style={({ pressed }) => [styles.chip, styles.activeChip, pressed && styles.pressed]}>
            <Text style={[styles.chipLabel, styles.activeChipLabel]}>{label}</Text>
            <Ionicons aria-hidden accessible={false} name="close" size={15} color={colors.green} />
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function FilterGroup<T extends string>({ title, options, value, onChange }: {
  title: string;
  options: readonly { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <View style={styles.group}>
      <Text style={styles.groupLabel}>{title}</Text>
      <View style={styles.chipRow}>
        {options.map(({ id, label }) => (
          <Pressable key={id} accessibilityRole="button" accessibilityState={{ selected: id === value }}
            aria-pressed={id === value} onPress={() => onChange(id)}
            style={({ pressed }) => [styles.chip, id === value && styles.chipSelected, pressed && styles.pressed]}>
            {id === value ? <Ionicons aria-hidden accessible={false} name="checkmark" size={15} color={colors.white} /> : null}
            <Text style={[styles.chipLabel, id === value && styles.chipLabelSelected]}>{label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  filters: { gap: 10 },
  toolbar: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  search: {
    alignItems: "center", backgroundColor: colors.surface, borderColor: colors.line, borderRadius: 14,
    borderWidth: 2, flex: 1, flexBasis: 132, flexDirection: "row", gap: 8, minHeight: 52, paddingLeft: 11,
  },
  searchFocused: { borderColor: colors.green },
  searchInput: {
    color: colors.ink, flex: 1, fontFamily: typography.regular, fontSize: 16, minWidth: 0, paddingVertical: 12,
    ...(Platform.OS === "web" ? { outlineWidth: 0 } : {}),
  },
  clearSearch: { alignItems: "center", justifyContent: "center", minHeight: 44, width: 40 },
  filterTrigger: {
    alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14,
    borderWidth: 1, flexDirection: "row", gap: 6, justifyContent: "center", minHeight: 52, paddingHorizontal: 12,
  },
  triggerActive: { backgroundColor: colors.primarySoft, borderColor: colors.green },
  triggerLabel: { color: colors.green, fontFamily: typography.bold, fontSize: 15, lineHeight: 21 },
  filterBadge: {
    alignItems: "center", backgroundColor: colors.green, borderRadius: 999, justifyContent: "center",
    minHeight: 20, minWidth: 20, paddingHorizontal: 4,
  },
  filterBadgeText: { color: colors.white, fontFamily: typography.bold, fontSize: 12, lineHeight: 16 },
  panel: {
    backgroundColor: colors.surface, borderColor: colors.line, borderRadius: 18, borderWidth: 1,
    gap: 14, paddingHorizontal: 15, paddingVertical: 14,
  },
  panelHeading: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", columnGap: 8, justifyContent: "space-between" },
  panelTitle: { color: colors.ink, fontFamily: typography.extraBold, fontSize: 18, lineHeight: 24 },
  reset: { justifyContent: "center", minHeight: 44 },
  resetLabel: { color: colors.green, fontFamily: typography.bold, fontSize: 14, textDecorationLine: "underline" },
  group: { gap: 6 },
  groupLabel: { color: colors.ink, fontFamily: typography.bold, fontSize: 14, lineHeight: 20 },
  chipRow: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 7 },
  chip: {
    alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 999,
    borderWidth: 1, flexDirection: "row", gap: 5, maxWidth: "100%", minHeight: 44, paddingHorizontal: 12,
  },
  chipSelected: { backgroundColor: colors.green, borderColor: colors.green },
  activeChip: { backgroundColor: colors.primarySoft, borderColor: colors.primarySoft },
  chipLabel: { color: colors.muted, flexShrink: 1, fontFamily: typography.medium, fontSize: 14, lineHeight: 19 },
  chipLabelSelected: { color: colors.white },
  activeChipLabel: { color: colors.green },
  viewResults: {
    alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.green, borderRadius: 12,
    flexDirection: "row", gap: 8, justifyContent: "center", minHeight: 44, paddingHorizontal: 14,
  },
  viewResultsLabel: { color: colors.white, fontFamily: typography.bold, fontSize: 14, lineHeight: 20 },
  pressed: { opacity: 0.75 },
});

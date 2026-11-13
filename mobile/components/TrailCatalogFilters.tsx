import { Ionicons } from "@expo/vector-icons";
import { useState } from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import type { DistanceFilter, TrailAreaFilter } from "../../services/trailFilters";
import { colors, typography } from "./MiSenderoUI";
import { surfaceShadows } from "./surfaceShadows";

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
  favoritesOnly: boolean;
};

export const defaultCatalogFilters: CatalogFilters = {
  area: "all", difficulty: "Todas", distance: "Todas", favoritesOnly: false,
};

export function TrailCatalogFilters({
  filters, setFilters, query, setQuery, draft, setDraft, onApply,
}: {
  filters: CatalogFilters;
  setFilters: (filters: CatalogFilters) => void;
  query: string;
  setQuery: (query: string) => void;
  draft: CatalogFilters | null;
  setDraft: (draft: CatalogFilters | null) => void;
  onApply: (filters: CatalogFilters) => void;
}) {
  const [searchFocused, setSearchFocused] = useState(false);
  const expanded = draft !== null;
  const activeFilters = ([
    { key: "area", label: areas.find((area) => area.id === filters.area)?.label },
    { key: "difficulty", label: `Dificultad: ${filters.difficulty}` },
    { key: "distance", label: distances.find((distance) => distance.id === filters.distance)?.label },
  ] as const).filter(({ key }) => filters[key] !== defaultCatalogFilters[key]);
  const activeCount = activeFilters.length + Number(filters.favoritesOnly);

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
          accessibilityHint={activeCount ? `${activeCount} ${activeCount === 1 ? "filtro activo" : "filtros activos"}` : undefined}
          accessibilityState={{ expanded }}
          aria-expanded={expanded}
          onPress={() => setDraft(expanded ? null : filters)}
          style={({ pressed }) => [
            styles.filterTrigger, (expanded || activeCount > 0) && styles.triggerActive,
            pressed && styles.pressed,
          ]}
        >
          <Ionicons aria-hidden accessible={false} name="options-outline" size={19} color={colors.green} />
          <Text style={styles.triggerLabel}>Filtros</Text>
          {activeCount > 0 ? (
            <View style={styles.filterBadge}><Text style={styles.filterBadgeText}>{activeCount}</Text></View>
          ) : null}
        </Pressable>
      </View>

      {draft ? <FilterPanel filters={draft} setFilters={setDraft} onApply={() => onApply(draft)} /> : null}

      {!expanded && activeFilters.length > 0 ? (
        <View style={styles.chipRow}>
          {activeFilters.map(({ key, label }) => (
            <Pressable key={key} accessibilityRole="button" accessibilityLabel={`Quitar filtro: ${label}`}
              onPress={() => setFilters({ ...filters, [key]: defaultCatalogFilters[key] })}
              style={({ pressed }) => [styles.chip, styles.activeChip, pressed && styles.pressed]}>
              <Text style={[styles.chipLabel, styles.activeChipLabel]}>{label}</Text>
              <Ionicons aria-hidden accessible={false} name="close" size={15} color={colors.green} />
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function FilterPanel({ filters, setFilters, onApply }: {
  filters: CatalogFilters;
  setFilters: (filters: CatalogFilters) => void;
  onApply: () => void;
}) {
  const [openGroup, setOpenGroup] = useState<"area" | "difficulty" | "distance" | null>(null);
  const toggleGroup = (group: typeof openGroup) => setOpenGroup((current) => current === group ? null : group);
  const hasSelection = filters.area !== defaultCatalogFilters.area || filters.difficulty !== defaultCatalogFilters.difficulty ||
    filters.distance !== defaultCatalogFilters.distance || filters.favoritesOnly;

  return (
    <View style={styles.panel}>
      <FilterGroup title="Tipo de sendero" options={areas} value={filters.area}
        expanded={openGroup === "area"} onToggle={() => toggleGroup("area")}
        onChange={(area) => { setFilters({ ...filters, area }); setOpenGroup(null); }} />
      <FilterGroup title="Dificultad" options={difficulties} value={filters.difficulty}
        expanded={openGroup === "difficulty"} onToggle={() => toggleGroup("difficulty")}
        onChange={(difficulty) => { setFilters({ ...filters, difficulty }); setOpenGroup(null); }} />
      <FilterGroup title="Distancia" options={distances} value={filters.distance}
        expanded={openGroup === "distance"} onToggle={() => toggleGroup("distance")}
        onChange={(distance) => { setFilters({ ...filters, distance }); setOpenGroup(null); }} />
      <Pressable accessibilityRole="checkbox" accessibilityLabel="Favoritos" accessibilityState={{ checked: filters.favoritesOnly }}
        onPress={() => setFilters({ ...filters, favoritesOnly: !filters.favoritesOnly })}
        style={({ pressed }) => [styles.filterRow, pressed && styles.pressed]}>
        <Ionicons aria-hidden accessible={false} name={filters.favoritesOnly ? "star" : "star-outline"} size={17} color={colors.green} />
        <Text style={[styles.rowLabel, styles.favoriteLabel]}>Favoritos</Text>
        <Ionicons aria-hidden accessible={false} name={filters.favoritesOnly ? "checkbox" : "square-outline"} size={19} color={colors.green} />
      </Pressable>
      <View style={styles.panelActions}>
        {hasSelection ? (
          <Pressable accessibilityRole="button" onPress={() => { setFilters(defaultCatalogFilters); setOpenGroup(null); }}
            style={({ pressed }) => [styles.reset, pressed && styles.pressed]}>
            <Text style={styles.resetLabel}>Limpiar filtros</Text>
          </Pressable>
        ) : null}
        <Pressable accessibilityRole="button" onPress={onApply}
          style={({ pressed }) => [styles.apply, pressed && styles.pressed]}>
          <Text style={styles.applyLabel}>Aplicar</Text>
        </Pressable>
      </View>
    </View>
  );
}

function FilterGroup<T extends string>({ title, options, value, expanded, onToggle, onChange }: {
  title: string;
  options: readonly { id: T; label: string }[];
  value: T;
  expanded: boolean;
  onToggle: () => void;
  onChange: (id: T) => void;
}) {
  const selectedLabel = options.find(({ id }) => id === value)?.label;
  return (
    <View style={styles.group}>
      <Pressable accessibilityRole="button" accessibilityLabel={title} accessibilityState={{ expanded }}
        accessibilityValue={{ text: selectedLabel }} onPress={onToggle}
        style={({ pressed }) => [styles.filterRow, pressed && styles.pressed]}>
        <Text style={styles.rowLabel}>{title}</Text>
        <Text style={styles.rowValue}>{selectedLabel}</Text>
        <Ionicons aria-hidden accessible={false} name={expanded ? "chevron-up" : "chevron-down"} size={16} color={colors.green} />
      </Pressable>
      {expanded ? <View style={[styles.chipRow, styles.options]}>
        {options.map(({ id, label }) => (
          <Pressable key={id} accessibilityRole="button" accessibilityState={{ selected: id === value }}
            aria-pressed={id === value} onPress={() => onChange(id)}
            style={({ pressed }) => [styles.chip, id === value && styles.chipSelected, pressed && styles.pressed]}>
            {id === value ? <Ionicons aria-hidden accessible={false} name="checkmark" size={15} color={colors.white} /> : null}
            <Text style={[styles.chipLabel, id === value && styles.chipLabelSelected]}>{label}</Text>
          </Pressable>
        ))}
      </View> : null}
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
    ...surfaceShadows.card,
    alignItems: "center", backgroundColor: colors.surface, borderRadius: 14,
    flexDirection: "row", gap: 6, justifyContent: "center", minHeight: 52, paddingHorizontal: 12,
  },
  triggerActive: { backgroundColor: colors.primarySoft },
  triggerLabel: { color: colors.green, fontFamily: typography.bold, fontSize: 15, lineHeight: 21 },
  filterBadge: {
    alignItems: "center", backgroundColor: colors.green, borderRadius: 999, justifyContent: "center",
    minHeight: 20, minWidth: 20, paddingHorizontal: 4,
  },
  filterBadgeText: { color: colors.white, fontFamily: typography.bold, fontSize: 12, lineHeight: 16 },
  panel: {
    ...surfaceShadows.card,
    backgroundColor: colors.surface, borderRadius: 18,
    gap: 4, padding: 8,
  },
  filterRow: { alignItems: "center", backgroundColor: colors.softer, borderRadius: 10, flexDirection: "row",
    gap: 8, minHeight: 44, paddingHorizontal: 10, paddingVertical: 6 },
  rowLabel: { color: colors.ink, flexShrink: 1, fontFamily: typography.bold, fontSize: 14, lineHeight: 20 },
  favoriteLabel: { flex: 1 },
  rowValue: { color: colors.greenDark, flex: 1, fontFamily: typography.medium, fontSize: 14, lineHeight: 20, textAlign: "right" },
  group: { gap: 4 },
  options: { paddingHorizontal: 4, paddingBottom: 4 },
  chipRow: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 7 },
  chip: {
    alignItems: "center", backgroundColor: colors.soft, borderRadius: 999,
    flexDirection: "row", gap: 5, maxWidth: "100%", minHeight: 44, paddingHorizontal: 12,
  },
  chipSelected: { backgroundColor: colors.green },
  activeChip: { backgroundColor: colors.primarySoft },
  chipLabel: { color: colors.muted, flexShrink: 1, fontFamily: typography.medium, fontSize: 14, lineHeight: 19 },
  chipLabelSelected: { color: colors.white },
  activeChipLabel: { color: colors.green },
  panelActions: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "flex-end", marginTop: 4 },
  reset: { justifyContent: "center", minHeight: 44, paddingHorizontal: 10 },
  resetLabel: { color: colors.green, fontFamily: typography.bold, fontSize: 14, lineHeight: 20 },
  apply: {
    alignItems: "center", backgroundColor: colors.green, borderRadius: 10, justifyContent: "center",
    minHeight: 44, paddingHorizontal: 18, paddingVertical: 6,
  },
  applyLabel: { color: colors.white, fontFamily: typography.bold, fontSize: 14, lineHeight: 20 },
  pressed: { opacity: 0.75 },
});

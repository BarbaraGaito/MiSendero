import type { ComponentProps } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, typography } from "./MiSenderoUI";

type Metric = { label: string; value: string; icon: ComponentProps<typeof Ionicons>["name"] };

export function TrailMetrics({ items, columns = 3 }: { items: Metric[]; columns?: 2 | 3 }) {
  return <View style={styles.grid}>
    {items.map(item => <View key={item.label} style={[styles.metric, { flexBasis: columns === 2 ? "44%" : "28%" }]}>
      <View style={styles.labelRow}>
        <Ionicons name={item.icon} size={15} color={colors.muted} />
        <Text style={styles.label}>{item.label}</Text>
      </View>
      <Text style={styles.value}>{item.value}</Text>
    </View>)}
  </View>;
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginVertical: 18 },
  metric: { flexGrow: 1, minWidth: 92, paddingVertical: 12, paddingHorizontal: 8, gap: 8, backgroundColor: colors.softer, borderRadius: 14 },
  labelRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 5 },
  label: { fontFamily: typography.regular, fontSize: 12, lineHeight: 17, color: colors.muted },
  value: { fontFamily: typography.medium, fontSize: 15, lineHeight: 22, color: colors.greenDark },
});

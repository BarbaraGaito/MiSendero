import type { ComponentProps } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, typography } from "./MiSenderoUI";

type Metric = { label: string; value: string; icon: ComponentProps<typeof Ionicons>["name"] };

export function TrailMetrics({ items, columns = 3 }: { items: Metric[]; columns?: 2 | 3 }) {
  return <View style={styles.grid}>
    {items.map(item => <View key={item.label} style={[styles.metric, { flexBasis: columns === 2 ? "44%" : "28%" }]}>
      <Ionicons aria-hidden accessible={false} name={item.icon} size={15} color={colors.greenDark} />
      <View style={styles.metricCopy}>
        <Text style={styles.label}>{item.label}</Text>
        <Text style={styles.value}>{item.value}</Text>
      </View>
    </View>)}
  </View>;
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginVertical: 18 },
  metric: { flexDirection: "row", alignItems: "center", flexGrow: 1, minWidth: 92, paddingVertical: 8,
    paddingHorizontal: 8, gap: 5, backgroundColor: colors.softer, borderRadius: 14 },
  metricCopy: { flex: 1, minWidth: 0 },
  label: { fontFamily: typography.regular, fontSize: 12, lineHeight: 17, color: colors.muted },
  value: { fontFamily: typography.medium, fontSize: 15, lineHeight: 22, color: colors.greenDark },
});

import { useState, type ComponentProps, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, typography } from "./MiSenderoUI";

/** Secondary information stays available without competing with the route summary. */
export function ExpandableSection({ title, summary, icon, children, tone = "default" }: {
  title: string;
  summary?: string;
  icon?: ComponentProps<typeof Ionicons>["name"];
  children: ReactNode;
  tone?: "default" | "info";
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <View style={[styles.section, tone === "info" && styles.info]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={title}
        accessibilityState={{ expanded }}
        aria-expanded={expanded}
        onPress={() => setExpanded(value => !value)}
        style={({ pressed }) => [styles.header, pressed && styles.pressed]}
      >
        {icon ? <Ionicons name={icon} size={20} color={colors.greenDark} /> : null}
        <View style={styles.heading}>
          <Text style={styles.title}>{title}</Text>
          {!expanded && summary ? <Text style={styles.summary}>{summary}</Text> : null}
        </View>
        <Ionicons name={expanded ? "chevron-up" : "chevron-down"} size={18} color={colors.greenDark} />
      </Pressable>
      {expanded ? <View style={styles.content}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { borderTopWidth: 1, borderColor: colors.line },
  info: { backgroundColor: colors.sky, borderTopWidth: 0, borderRadius: 18 },
  header: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 56, paddingVertical: 16, paddingHorizontal: 12 },
  heading: { flex: 1, minWidth: 0, gap: 4 },
  title: { fontFamily: typography.medium, fontSize: 16, lineHeight: 22, color: colors.greenDark },
  summary: { fontFamily: typography.regular, fontSize: 13, lineHeight: 19, color: colors.muted },
  content: { paddingHorizontal: 12, paddingBottom: 18, gap: 12 },
  pressed: { opacity: 0.72 },
});

import type { ComponentProps } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Card, colors } from "../../components/MiSenderoUI";

export type IconName = ComponentProps<typeof Ionicons>["name"];

export function DownloadedMapCard({
  title,
  meta,
  action,
  secondaryAction,
  tone,
  onPress,
  onSecondaryPress,
}: {
  title: string;
  meta: string;
  action: string;
  secondaryAction?: string;
  tone?: "danger";
  onPress?: () => void;
  onSecondaryPress?: () => void;
}) {
  return (
    <Card>
      <View style={styles.mapRow}>
        <View style={styles.mapInfo}>
          <View style={styles.inlineTitle}>
            <Ionicons name="map-outline" size={18} color={colors.primary} />
            <Text style={styles.cardTitle}>{title}</Text>
          </View>
          <Text style={styles.meta}>{meta}</Text>
        </View>
        <View style={styles.mapActions}>
          <Pressable
            accessibilityRole="button"
            disabled={!onPress}
            onPress={onPress}
            style={({ pressed }) => pressed && { opacity: 0.72 }}
          >
            <Text style={[styles.pillAction, tone === "danger" && styles.pillDanger]}>
              {action}
            </Text>
          </Pressable>
          {secondaryAction && onSecondaryPress ? (
            <Pressable
              accessibilityRole="button"
              onPress={onSecondaryPress}
              style={({ pressed }) => pressed && { opacity: 0.72 }}
            >
              <Text style={styles.pillSecondary}>{secondaryAction}</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
    </Card>
  );
}

export function Chip({ label, active }: { label: string; active?: boolean }) {
  return (
    <View style={[styles.chip, active && styles.chipActive]}>
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </View>
  );
}

export function InfoRow({
  icon,
  label,
  value,
}: {
  icon: IconName;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.infoRow}>
      <View style={styles.infoLeft}>
        <Ionicons name={icon} size={18} color={colors.primary} />
        <Text style={styles.infoLabel}>{label}</Text>
      </View>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

export function ProgressHero({
  percent,
  status,
  tone,
}: {
  percent: string;
  status: string;
  tone: "green" | "orange" | "red";
}) {
  return (
    <Card style={styles.progressHero}>
      <View
        style={[
          styles.ring,
          tone === "orange" && styles.ringOrange,
          tone === "red" && styles.ringRed,
        ]}
      >
        <Text style={styles.percent}>{percent}</Text>
        <Text style={styles.ringStatus}>{status}</Text>
      </View>

    </Card>
  );
}

export const styles = StyleSheet.create({
  searchBox: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 18,
    flexDirection: "row",
    gap: 10,
    minHeight: 54,
    marginBottom: 16,
    paddingHorizontal: 14,
  },
  searchText: {
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    fontWeight: "800",
  },
  inlineTitle: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  cardTitle: {
    color: colors.ink,
    flex: 1,
    fontSize: 17,
    fontWeight: "800",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
  meta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  sectionLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "900",
    marginBottom: 12,
  },
  chips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    backgroundColor: colors.white,
    borderColor: colors.line,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  chipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "800",
  },
  chipTextActive: {
    color: colors.white,
  },
  helper: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "700",
    marginTop: 12,
  },
  infoRow: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 12,
  },
  infoLeft: {
    alignItems: "center",
    flex: 1,
    flexDirection: "row",
    gap: 9,
  },
  infoLabel: {
    color: colors.ink,
    flex: 1,
    fontSize: 14,
    fontWeight: "700",
  },
  infoValue: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: "900",
  },
  mapPreview: {
    backgroundColor: "#E8F2E9",
    borderRadius: 28,
    height: 238,
    marginBottom: 16,
    overflow: "hidden",
    position: "relative",
  },
  contour: {
    borderColor: "#C8DED0",
    borderRadius: 999,
    borderWidth: 2,
    height: 92,
    position: "absolute",
    transform: [{ rotate: "-12deg" }],
  },
  contourOne: {
    left: 38,
    top: 54,
    width: 256,
  },
  contourTwo: {
    left: 72,
    top: 86,
    width: 198,
  },
  routeLine: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: 9,
    position: "absolute",
  },
  routeOne: {
    left: 70,
    top: 152,
    transform: [{ rotate: "-32deg" }],
    width: 132,
  },
  routeTwo: {
    left: 168,
    top: 126,
    transform: [{ rotate: "24deg" }],
    width: 110,
  },
  mapPin: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: 42,
    justifyContent: "center",
    position: "absolute",
    right: 72,
    top: 98,
    width: 42,
  },
  bottomActions: {
    gap: 10,
    marginTop: "auto",
  },
  successCircle: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.successSoft,
    borderRadius: 999,
    height: 92,
    justifyContent: "center",
    marginBottom: 18,
    width: 92,
  },
  progressTrack: {
    backgroundColor: colors.surface,
    borderRadius: 999,
    height: 10,
    marginTop: 12,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: "100%",
  },
  mapRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  mapInfo: {
    flex: 1,
    minWidth: 0,
  },
  mapActions: {
    alignItems: "flex-end",
    gap: 8,
  },
  pillAction: {
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    color: colors.primary,
    fontSize: 12,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  pillDanger: {
    backgroundColor: colors.redSoft,
    color: colors.red,
  },
  pillSecondary: {
    backgroundColor: colors.surface,
    borderRadius: 999,
    color: colors.red,
    fontSize: 12,
    fontWeight: "900",
    overflow: "hidden",
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  progressHero: {
    alignItems: "center",
    gap: 16,
  },
  ring: {
    alignItems: "center",
    borderColor: colors.primary,
    borderRadius: 999,
    borderWidth: 16,
    height: 160,
    justifyContent: "center",
    width: 160,
  },
  ringOrange: {
    borderColor: colors.orange,
  },
  ringRed: {
    borderColor: colors.red,
  },
  percent: {
    color: colors.ink,
    fontSize: 34,
    fontWeight: "900",
  },
  ringStatus: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
  },
  statsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    width: "100%",
  },
  statRight: {
    alignItems: "flex-end",
  },
  statValue: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
    marginTop: 2,
  },
  activityRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    width: "100%",
  },
  activityDot: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    height: 10,
    width: 10,
  },
});

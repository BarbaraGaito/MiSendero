import React from "react";
import { router } from "expo-router";

import {
  ActivityIndicator,
  ImageBackground,
  Pressable,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

export const colors = {
  ink: "#10201A",
  muted: "#6E7A73",
  soft: "#EEF7F0",
  softer: "#F6FAF7",
  line: "#DDE9E0",
  green: "#0D7A45",
  greenDark: "#075E36",
  mint: "#DFF3E7",
  danger: "#D84C3F",
  warning: "#F1B84B",
  white: "#FFFFFF",
  primary: "#0D7A45",
  surface: "#EEF7F0",
  primaryDark: "#075E36",
  primarySoft: "#DFF3E7",
  orange: "#D97706",
  orangeSoft: "#FEF3C7",
  red:  "#D84C3F",
  redSoft: "#f9bcb7",
  border : "#c8efd2",
  successSoft: "#b8f3cf",
  page: "#F6FAF7",
};

export const trailImages = {
  forest:
    "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?q=80&w=1200&auto=format&fit=crop",
  mountain:
    "https://images.unsplash.com/photo-1501785888041-af3ef285b470?q=80&w=1200&auto=format&fit=crop",
  lake:
    "https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?q=80&w=1200&auto=format&fit=crop",
};

type IconName = React.ComponentProps<typeof Ionicons>["name"];
type ButtonTone = "green" | "danger" | "light" | "secondary";
type BottomTab = "inicio" | "explorar" | "actividad" | "perfil";

const getButtonStyle = (tone: ButtonTone) => [
  styles.primaryButton,
  tone === "danger" && styles.dangerButton,
  tone === "light" && styles.lightButton,
  tone === "secondary" && styles.secondaryButton,
];

const getButtonLabelStyle = (tone: ButtonTone) => [
  styles.primaryLabel,
  tone === "light" && styles.lightButtonLabel,
  tone === "secondary" && styles.secondaryButtonLabel,
];

const getButtonIconColor = (tone: ButtonTone) =>
  tone === "light" || tone === "secondary" ? colors.green : colors.white;

export function ScreenShell({
  children,
  footer,
  style,
}: {
  children: React.ReactNode;
  footer?: React.ReactNode;
  style?: ViewStyle;
}) {
  return (
    <SafeAreaView edges={["top", "bottom"]} style={[styles.shell, style]}>
      <View style={styles.content}>{children}</View>
      {footer}
    </SafeAreaView>
  );
}

export function AppScreen({
  children,
  activeTab,
  withBottomNav = true,
}: {
  children: React.ReactNode;
  activeTab?: BottomTab;
  withBottomNav?: boolean;
}) {
  return (
    <ScreenShell
      footer={
        withBottomNav && activeTab ? (
          <BottomNav active={activeTab} />
        ) : undefined
      }
    >
      {children}
    </ScreenShell>
  );
}

export function Card({
  children,
  tone = "default",
  style,
}: {
  children: React.ReactNode;
  tone?: "default" | "green" | "orange" | "white" | "secondary" | "red";
  style?: ViewStyle;
}) {
  return (
    <View
      style={[
        styles.card,
        tone === "green" && styles.cardGreen,
        tone === "orange" && styles.cardOrange,
        tone === "white" && styles.cardWhite,
        tone === "secondary" && styles.cardSecondary,
        tone === "red" && styles.cardRed,
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function ScreenTitle({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <View style={styles.screenTitle}>
      {eyebrow ? (
        <Text style={styles.eyebrow}>{eyebrow}</Text>
      ) : null}

      <Text style={styles.screenTitleText}>
        {title}
      </Text>

      {subtitle ? (
        <Text style={styles.screenSubtitle}>
          {subtitle}
        </Text>
      ) : null}
    </View>
  );
}

export function TopBar({
  title,
  subtitle,
  onBack,
}: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
}) {
  return (
    <View style={styles.topBar}>
      {onBack ? (
        <Pressable
          accessibilityLabel="Volver"
          accessibilityRole="button"
          hitSlop={10}
          onPress={onBack}
          style={({ pressed }) => [
            styles.iconButton,
            pressed && styles.pressed,
          ]}
        >
          <Ionicons name="chevron-back" size={22} color={colors.ink} />
        </Pressable>
      ) : (
        <View style={styles.mark}>
          <Ionicons name="leaf-outline" size={22} color={colors.green} />
        </View>
      )}
      <View style={styles.topText}>
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      <Pressable
        accessibilityLabel="Notificaciones"
        accessibilityRole="button"
        hitSlop={10}
        style={({ pressed }) => [
          styles.iconButton,
          pressed && styles.pressed,
        ]}
      >
        <Ionicons name="notifications-outline" size={21} color={colors.ink} />
      </Pressable>
    </View>
  );
}

export function PrimaryButton({
  label,
  icon,
  onPress,
  href,
  tone = "green",
  disabled = false,
  isLoading = false,
  loadingLabel,
  accessibilityLabel,
}: {
  label: string;
  icon?: IconName;
  onPress?: () => void;
  href?: string;
  tone?: "green" | "danger" | "light" | "secondary";
  disabled?: boolean;
  isLoading?: boolean;
  loadingLabel?: string;
  accessibilityLabel?: string;
}) {
  const isDisabled = disabled || isLoading;
  const labelText = isLoading && loadingLabel ? loadingLabel : label;
  const foreground =
    tone === "light" || tone === "secondary" ? colors.green : colors.white;

  return (
    <Pressable
      accessibilityLabel={accessibilityLabel || labelText}
      accessibilityRole="button"
      accessibilityState={{ busy: isLoading, disabled: isDisabled }}
      disabled={isDisabled}
      hitSlop={6}
      style={({ pressed }) => [
          styles.primaryButton,
          tone === "danger" && styles.dangerButton,
          tone === "light" && styles.lightButton,
          tone === "secondary" && styles.secondaryButton,
          pressed && !isDisabled && styles.pressed,
          isDisabled && styles.disabled,
        ]}
      onPress={() => {
        if (onPress) onPress();
        else if (href) router.push(href as any);
      }}
    >
      {isLoading ? (
        <ActivityIndicator color={foreground} size="small" />
      ) : icon ? (
        <Ionicons
          name={icon}
          size={19}
          color={foreground}
        />
      ) : null}
      <Text
        style={[
          styles.primaryLabel,
          tone === "light" && styles.lightButtonLabel,
          tone === "secondary" && styles.secondaryButtonLabel,
        ]}
      >
        {labelText}
      </Text>
    </Pressable>
  );
}

type BottomNavItem = { id: BottomTab; label: string; icon: IconName; href: string };

export function BottomNav({ active }: { active: BottomTab }) {
  const items: BottomNavItem[] = [
    { id: "inicio", label: "Inicio", icon: "home-outline", href: "/inicio" },
    { id: "explorar", label: "Explorar", icon: "compass-outline", href: "/explorar-rutas" },
    { id: "actividad", label: "Actividad", icon: "pulse-outline", href: "/mis-actividades" },
    { id: "perfil", label: "Perfil", icon: "person-outline", href: "/perfil" },
  ];

  return (
    <View style={styles.bottomNav}>
      {items.map((item) => {
        const selected = item.id === active;
        return (
         <Pressable
            accessibilityLabel={item.label}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            hitSlop={8}
            key={item.id}
            onPress={() => router.push(item.href as any)}
            style={({ pressed }) => [
              styles.navItem,
              selected && styles.navItemActive,
              pressed && styles.pressed,
            ]}
          >

            <Ionicons
              name={item.icon}
              size={25}
              color={selected ? colors.green : colors.muted}
            />
            <Text style={[styles.navLabel, selected && styles.navLabelActive]}>
              {item.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function BottomNavButton({
  item,
  selected,
}: {
  item: BottomNavItem;
  selected: boolean;
}) {
  return (
    <Pressable
      style={styles.navItem}
      onPress={() => router.push(item.href as any)}
    >
      <Ionicons
        name={item.icon}
        size={25}
        color={selected ? colors.green : colors.muted}
      />
      <Text style={[styles.navLabel, selected && styles.navLabelActive]}>
        {item.label}
      </Text>
    </Pressable>
  );
}

export function StatPill({
  icon,
  label,
}: {
  icon: IconName;
  label: string;
}) {
  return (
    <View style={styles.statPill}>
      <Ionicons name={icon} size={15} color={colors.greenDark} />
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

export function TrailCard({
  title,
  location,
  image,
  difficulty,
  distance = "4,2 km",
  duration = "1h 35m",
  onPress,
}: {
  title: string;
  location: string;
  image: string;
  difficulty: string;
  distance?: string;
  duration?: string;
  onPress?: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={styles.trailCard}>
      <ImageBackground source={{ uri: image }} style={styles.trailImage} imageStyle={styles.trailImageRadius}>
        <View style={styles.trailBadge}>
          <Text style={styles.trailBadgeText}>{difficulty}</Text>
        </View>
      </ImageBackground>
      <View style={styles.trailBody}>
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardMuted}>{location}</Text>
        <View style={styles.statRow}>
          <StatPill icon="walk-outline" label={distance} />
          <StatPill icon="time-outline" label={duration} />
        </View>
      </View>
    </Pressable>
  );
}

export function InfoCard({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.infoCard, style]}>{children}</View>;
}

export function Metric({
  value,
  label,
}: {
  value: string;
  label: string;
}) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

export function SettingRow({
  label,
  value,
  onPress,
}: {
  label: string;
  value: string;
  onPress?: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityLabel={`${label}: ${value}`}
      accessibilityRole={onPress ? "button" : "text"}
      disabled={!onPress}
      hitSlop={4}
      style={({ pressed }) => [
        styles.settingRow,
        pressed && onPress && styles.pressed,
      ]}
    >
      <Text style={styles.settingLabel}>{label}</Text>

      <View style={styles.settingRight}>
        <Text style={styles.settingValue}>{value}</Text>
        {onPress ? (
          <Ionicons
            name="chevron-forward"
            size={18}
            color={colors.muted}
          />
        ) : null}
      </View>
    </Pressable>
  );
}

export function StatusNotice({
  tone = "info",
  title,
  message,
  actionLabel,
  onAction,
  isLoading = false,
}: {
  tone?: "info" | "success" | "warning" | "error";
  title?: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  isLoading?: boolean;
}) {
  const iconColor =
    tone === "error"
      ? colors.danger
      : tone === "warning"
        ? colors.orange
        : colors.green;
  const iconName: IconName =
    tone === "error"
      ? "alert-circle-outline"
      : tone === "success"
        ? "checkmark-circle-outline"
        : tone === "warning"
          ? "warning-outline"
          : "information-circle-outline";

  return (
    <View
      accessibilityLiveRegion="polite"
      style={[
        styles.statusNotice,
        tone === "error" && styles.statusNoticeError,
        tone === "warning" && styles.statusNoticeWarning,
        tone === "success" && styles.statusNoticeSuccess,
      ]}
    >
      <View style={styles.statusIcon}>
        {isLoading ? (
          <ActivityIndicator color={iconColor} size="small" />
        ) : (
          <Ionicons name={iconName} size={21} color={iconColor} />
        )}
      </View>
      <View style={styles.statusBody}>
        {title ? <Text style={styles.statusTitle}>{title}</Text> : null}
        <Text style={styles.statusMessage}>{message}</Text>
        {actionLabel && onAction ? (
          <Pressable
            accessibilityRole="button"
            hitSlop={6}
            onPress={onAction}
            style={({ pressed }) => [
              styles.statusAction,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.statusActionText}>{actionLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

export const styles = StyleSheet.create({
  shell: {
    flex: 1,
    backgroundColor: colors.softer,
  },
  content: {
    flex: 1,
    minHeight: 0,
    paddingHorizontal: 22,
    paddingBottom: 12,
    paddingTop: 12,
  },
  topBar: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    marginBottom: 22,
  },
  iconButton: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 18,
    height: 42,
    justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 10,
    width: 42,
  },
  pressed: {
    opacity: 0.72,
  },
  disabled: {
    opacity: 0.58,
  },
  mark: {
    alignItems: "center",
    backgroundColor: colors.mint,
    borderRadius: 18,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  topText: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    color: colors.ink,
    fontSize: 21,
    fontWeight: "800",
  },
  subtitle: {
    color: colors.muted,
    fontSize: 13,
    marginTop: 2,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.green,
    borderRadius: 20,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 54,
    paddingHorizontal: 18,
  },
  dangerButton: {
    backgroundColor: colors.danger,
  },
  lightButton: {
    backgroundColor: colors.mint,
  },
  secondaryButton: {
    backgroundColor: colors.primarySoft,
  },
  primaryLabel: {
    color: colors.white,
    fontSize: 16,
    fontWeight: "800",
  },
  lightButtonLabel: {
    color: colors.greenDark,
  },
  secondaryButtonLabel: {
    color: colors.greenDark,
  },
  bottomNav: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.white,
    borderRadius: 34,
    elevation: 8,
    flexDirection: "row",
    gap: 4,
    justifyContent: "space-between",
    marginBottom: 12,
    marginTop: 8,
    paddingHorizontal: 14,
    paddingVertical: 13,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 18,
    width: "88%",
  },
  navItem: {
    alignItems: "center",
    borderRadius: 22,
    flex: 1,
    minWidth: 0,
    minHeight: 54,
    justifyContent: "center",
    paddingVertical: 5,
  },
  navItemActive: {
    backgroundColor: colors.primarySoft,
  },
  navLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    marginTop: 4,
  },
  navLabelActive: {
    color: colors.green,
  },
  trailCard: {
    backgroundColor: colors.white,
    borderRadius: 24,
    marginBottom: 16,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 14,
  },
  trailImage: {
    height: 142,
    justifyContent: "flex-start",
    padding: 14,
  },
  trailImageRadius: {
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  trailBadge: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.92)",
    borderRadius: 14,
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  trailBadgeText: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "800",
  },
  trailBody: {
    padding: 16,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  cardMuted: {
    color: colors.muted,
    fontSize: 13,
    marginTop: 4,
  },
  statRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 13,
  },
  statPill: {
    alignItems: "center",
    backgroundColor: colors.soft,
    borderRadius: 14,
    flexDirection: "row",
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  statLabel: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "800",
  },
  infoCard: {
    backgroundColor: colors.white,
    borderRadius: 22,
    padding: 18,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 12,
  },
  card: {
  backgroundColor: colors.white,
  borderRadius: 22,
  padding: 18,
  marginBottom: 16,
  shadowColor: "#000",
  shadowOpacity: 0.05,
  shadowRadius: 12,
},

cardGreen: {
  backgroundColor: colors.mint,
},

screenTitle: {
  marginBottom: 22,
},

eyebrow: {
  color: colors.green,
  fontSize: 13,
  fontWeight: "800",
  marginBottom: 4,
  textTransform: "uppercase",
},

screenTitleText: {
  color: colors.ink,
  fontSize: 28,
  fontWeight: "900",
},

screenSubtitle: {
  color: colors.muted,
  fontSize: 15,
  lineHeight: 22,
  marginTop: 6,
},

metric: {
  alignItems: "center",
  flex: 1,
},

metricValue: {
  color: colors.greenDark,
  fontSize: 24,
  fontWeight: "900",
},

metricLabel: {
  color: colors.muted,
  fontSize: 13,
  fontWeight: "600",
  marginTop: 4,
},

settingRow: {
  alignItems: "center",
  borderBottomColor: colors.line,
  borderBottomWidth: 1,
  flexDirection: "row",
  justifyContent: "space-between",
  paddingVertical: 14,
},

settingLabel: {
  color: colors.ink,
  flex: 1,
  fontSize: 15,
  fontWeight: "600",
},

settingRight: {
  alignItems: "center",
  flexDirection: "row",
  gap: 6,
},

settingValue: {
  color: colors.green,
  fontSize: 14,
  fontWeight: "700",
},
statusNotice: {
  alignItems: "flex-start",
  backgroundColor: colors.white,
  borderColor: colors.border,
  borderRadius: 18,
  borderWidth: 1,
  flexDirection: "row",
  gap: 10,
  marginBottom: 14,
  padding: 14,
},

statusNoticeError: {
  backgroundColor: "#FFF4F2",
  borderColor: "#F2B8B2",
},

statusNoticeWarning: {
  backgroundColor: colors.orangeSoft,
  borderColor: "#F7D48A",
},

statusNoticeSuccess: {
  backgroundColor: colors.mint,
  borderColor: colors.border,
},

statusIcon: {
  alignItems: "center",
  height: 26,
  justifyContent: "center",
  width: 26,
},

statusBody: {
  flex: 1,
  minWidth: 0,
},

statusTitle: {
  color: colors.ink,
  fontSize: 14,
  fontWeight: "900",
  marginBottom: 3,
},

statusMessage: {
  color: colors.muted,
  fontSize: 13,
  fontWeight: "700",
  lineHeight: 19,
},

statusAction: {
  alignSelf: "flex-start",
  marginTop: 10,
},

statusActionText: {
  color: colors.greenDark,
  fontSize: 13,
  fontWeight: "900",
},
cardWhite: {
  backgroundColor: colors.white,
},

cardOrange: {
  backgroundColor: colors.orangeSoft,
},

cardSecondary: {
  backgroundColor: colors.primarySoft,
}, 

cardRed: {
  backgroundColor: colors.redSoft,
},
});

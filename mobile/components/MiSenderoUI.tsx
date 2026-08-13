import React from "react";
import { router } from "expo-router";

import {
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
  activeTab?: "inicio" | "explorar" | "actividad" | "perfil";
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
        <Pressable onPress={onBack} style={styles.iconButton}>
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
      <Pressable style={styles.iconButton}>
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
}: {
  label: string;
  icon?: IconName;
  onPress?: () => void;
  href?: string;
  tone?: "green" | "danger" | "light" | "secondary";
}) {
  return (
    <Pressable
      style={[
        styles.primaryButton,
        tone === "danger" && styles.dangerButton,
        tone === "light" && styles.lightButton,
        tone === "secondary" && styles.secondaryButton,
      ]}
      onPress={() => {
        if (onPress) onPress();
        else if (href) router.push(href as any);
      }}
    >
      {icon ? (
        <Ionicons
          name={icon}
          size={19}
          color={tone === "light" || tone === "secondary" ? colors.green : colors.white}
        />
      ) : null}
      <Text
        style={[
          styles.primaryLabel,
          tone === "light" && styles.lightButtonLabel,
          tone === "secondary" && styles.secondaryButtonLabel,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function BottomNav({ active }: { active: "inicio" | "explorar" | "actividad" | "perfil" }) {
  const items: Array<{ id: typeof active; label: string; icon: IconName; href: string }> = [
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
    key={item.id}
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
      })}
    </View>
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
          <StatPill icon="star-outline" label="4.8" />
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
      style={styles.settingRow}
      disabled={!onPress}
    >
      <Text style={styles.settingLabel}>{label}</Text>

      <View style={styles.settingRight}>
        <Text style={styles.settingValue}>{value}</Text>
        <Ionicons
          name="chevron-forward"
          size={18}
          color={colors.muted}
        />
      </View>
    </Pressable>
  );
}

export const styles = StyleSheet.create({
  shell: {
    flex: 1,
    backgroundColor: colors.softer,
  },
  content: {
    flex: 1,
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
    flex: 1,
    minWidth: 0,
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

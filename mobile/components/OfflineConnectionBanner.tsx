import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { Pressable, StyleSheet, Text, type StyleProp, type ViewStyle } from "react-native";
import { useIsOffline } from "../../services/ConnectivityProvider";
import { surfaceShadows } from "./surfaceShadows";

export function OfflineConnectionBanner({ style }: { style?: StyleProp<ViewStyle> }) {
  const offline = useIsOffline();
  if (!offline) return null;
  return <Pressable
    accessibilityRole="button"
    accessibilityLabel="No hay conexión. Ver mapas descargados"
    accessibilityHint="Abre los mapas guardados para consultarlos sin Internet"
    accessibilityLiveRegion="polite"
    onPress={() => router.navigate("/offline-mapas-descargados")}
    style={({ pressed }) => [styles.banner, style, pressed && { opacity: 0.75 }]}
  >
    <Ionicons name="cloud-offline-outline" size={20} color="#795000" />
    <Text style={styles.message}>No hay conexión</Text>
    <Text style={styles.action}>Ver mapas descargados</Text>
    <Ionicons name="chevron-forward" size={16} color="#795000" />
  </Pressable>;
}

const styles = StyleSheet.create({
  banner: {
    ...surfaceShadows.card,
    backgroundColor: "#FFF1D3",
    borderRadius: 14, flexDirection: "row", alignItems: "center", gap: 8,
    minHeight: 48, paddingHorizontal: 12, paddingVertical: 10,
    marginHorizontal: 20, marginBottom: 12,
  },
  message: { color: "#795000", fontSize: 13, fontWeight: "700", flex: 1 },
  action: { color: "#795000", fontSize: 12, fontWeight: "700", flexShrink: 1 },
});

import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import * as Network from "expo-network";
import { Alert, Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { NationalParkProfile } from "../../types";
import { getParkRegistration, getRegistrationLabel } from "../../services/nationalParks";
import { colors } from "./MiSenderoUI";

export async function openOfficialUrl(url: string) {
  try {
    if (!url.startsWith("https://")) throw new Error("Enlace institucional no valido.");
    const state = await Network.getNetworkStateAsync();
    if (state.isConnected === false || state.isInternetReachable === false) {
      Alert.alert("Sin conexion", "Para consultar avisos actuales o completar el registro oficial necesitas internet.");
      return;
    }
    await Linking.openURL(url);
  } catch {
    Alert.alert("No se pudo abrir la fuente", "Revisa la conexion e intenta nuevamente. El formulario puede consultarse tambien desde la pagina del parque.");
  }
}

export function OfficialLink({ label, url }: { label: string; url: string }) {
  return <Pressable accessibilityRole="link" onPress={() => void openOfficialUrl(url)}
    style={({ pressed }) => [styles.link, pressed && styles.pressed]}>
    <Ionicons name="open-outline" size={18} color={colors.greenDark} />
    <Text style={styles.linkText}>{label}</Text>
  </Pressable>;
}

export function NationalParkEntry({ park, trailId, trailName, beforeStart = false }: {
  park: NationalParkProfile; trailId: number; trailName?: string; beforeStart?: boolean;
}) {
  return <View style={styles.section}>
    <Text style={styles.title}>{beforeStart ? "Requisitos del parque" : "Parques Nacionales"}</Text>
    <Text style={styles.name}>{park.name}</Text>
    {beforeStart && <>
      <Text style={styles.requirement}>{getRegistrationLabel(park, new Date(), trailName)}</Text>
      <Text style={styles.body}>{getParkRegistration(park, trailName).summary}</Text>
      <Text style={styles.body}>Consulta los avisos del parque y confirma la habilitacion del sendero antes de iniciar.</Text>
    </>}
    <Pressable accessibilityRole="button" onPress={() => router.push({
      pathname: "/parque-nacional", params: { slug: park.slug, trailId: String(trailId) },
    })} style={({ pressed }) => [styles.link, pressed && styles.pressed]}>
      <Ionicons name="shield-checkmark-outline" size={21} color={colors.greenDark} />
      <Text style={styles.linkText}>Informacion oficial y registro</Text>
      <Ionicons name="chevron-forward" size={18} color={colors.greenDark} />
    </Pressable>
  </View>;
}

const styles = StyleSheet.create({
  section: { paddingVertical: 18, borderTopWidth: 1, borderColor: colors.line, marginBottom: 12, gap: 8 },
  title: { color: colors.ink, fontSize: 19, fontWeight: "800" },
  name: { color: colors.muted, fontSize: 14, lineHeight: 21 },
  requirement: { color: colors.orange, fontSize: 15, fontWeight: "700" },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21 },
  link: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 10 },
  linkText: { color: colors.greenDark, fontSize: 14, fontWeight: "700", flexShrink: 1, lineHeight: 21 },
  pressed: { opacity: 0.65 },
});

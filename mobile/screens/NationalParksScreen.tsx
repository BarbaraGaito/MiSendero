import { Ionicons } from "@expo/vector-icons";
import { userMessage } from "../../services/userMessages";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { getNationalParks, ParkResult } from "../../services/nationalParks";
import { NationalPark } from "../../types";
import { AppScreen, colors, TopBar, StatusNotice as SharedStatusNotice } from "../components/MiSenderoUI";
import { surfaceShadows } from "../components/surfaceShadows";

export default function NationalParksScreen() {
  const [result, setResult] = useState<ParkResult<NationalPark[]> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setResult(await getNationalParks()); }
    catch (e) { setError(userMessage(e, "No se pudieron consultar los parques. Intentá nuevamente.")); }
    finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  return <AppScreen activeTab="explorar">
    <TopBar title="Parques Nacionales" onBack={() => router.back()} />
    <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <Text style={styles.title}>Parques Nacionales</Text>
      <Text style={styles.subtitle}>Informacion institucional de los senderos del catalogo</Text>
      {loading && <SharedStatusNotice title="Consultando parques" message="Cargando fichas oficiales." isLoading />}
      {error && <SharedStatusNotice title="No se pudo actualizar" message={error} tone="error" actionLabel="Reintentar" onAction={load} />}
      {result?.fromCache && <SharedStatusNotice title="Informacion guardada" message="Conectate para consultar los avisos actuales en la pagina oficial de cada parque." tone="warning" />}
      {result?.data.map((park) => <Pressable key={park.slug} accessibilityRole="button"
        accessibilityLabel={`Ver ${park.name}`} style={({ pressed }) => [styles.item, pressed && styles.pressed]}
        onPress={() => router.push({ pathname: "/parque-nacional", params: { slug: park.slug } })}>
        <ParkImage uri={park.trails.find((trail) => trail.image_url)?.image_url ?? null} />
        <View style={styles.itemBody}>
          <Text style={styles.name}>{park.name}</Text>
          <Text style={styles.meta}>{park.provinces.join(" / ")}</Text>
          <View style={styles.row}>
            <Text style={styles.count}>{park.trails.length} {park.trails.length === 1 ? "sendero" : "senderos"}</Text>
            <Ionicons name="chevron-forward" size={20} color={colors.greenDark} />
          </View>
        </View>
      </Pressable>)}
      {result?.data.length === 0 && !loading && <Text style={styles.subtitle}>Todavía no hay parques para mostrar. Volvé a consultar más adelante.</Text>}
    </ScrollView>
  </AppScreen>;
}

function ParkImage({ uri }: { uri: string | null }) {
  const [failed, setFailed] = useState(false);
  return uri && !failed ? <Image source={{ uri }} style={styles.image} onError={() => setFailed(true)} />
    : <View style={[styles.image, styles.placeholder]}><Ionicons name="leaf-outline" size={32} color={colors.muted} /></View>;
}

const styles = StyleSheet.create({
  content: { paddingBottom: 120, width: "100%", maxWidth: 720, alignSelf: "center" },
  title: { fontSize: 26, fontWeight: "800", color: colors.ink, marginBottom: 8 },
  subtitle: { fontSize: 14, lineHeight: 21, color: colors.muted, marginBottom: 20 },
  item: { ...surfaceShadows.card, borderRadius: 18, backgroundColor: colors.white, marginBottom: 18 },
  image: { width: "100%", height: 160, borderTopLeftRadius: 18, borderTopRightRadius: 18, backgroundColor: colors.soft },
  placeholder: { alignItems: "center", justifyContent: "center" },
  itemBody: { padding: 16, gap: 8 },
  name: { fontSize: 18, lineHeight: 25, fontWeight: "800", color: colors.ink },
  meta: { fontSize: 14, color: colors.muted },
  count: { fontSize: 13, fontWeight: "700", color: colors.greenDark, flex: 1 },
  row: { flexDirection: "row", alignItems: "center" },
  pressed: { opacity: 0.72 },
});

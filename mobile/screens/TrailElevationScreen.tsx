import { useCallback, useEffect, useState } from "react";
import { router, useLocalSearchParams } from "expo-router";
import * as Network from "expo-network";
import { ScrollView, StyleSheet, Text } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ScreenShell, StatusNotice, TopBar, colors } from "../components/MiSenderoUI";
import ElevationProfile from "../components/ElevationProfile";
import { getTrailById } from "../../services/trailRepository";
import { parseRouteCoordinates } from "../../services/geoUtils";
import { loadTerrainElevationState } from "../hooks/useTerrainElevation";
import { trailElevationFromTerrain } from "../../services/trailElevationFromTerrain";
import { Trail } from "../../types";

export default function TrailElevationScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const insets = useSafeAreaInsets();
  const [trail, setTrail] = useState<Trail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const trailId = Number(id);
      if (!Number.isInteger(trailId) || trailId <= 0) throw new Error("invalid-trail");
      const loadedTrail = await getTrailById(trailId);
      let elevation = loadedTrail.elevation;
      if ((elevation?.points?.length ?? 0) < 2) {
        const route = parseRouteCoordinates(loadedTrail.route_coordinates);
        if (route.length >= 2) {
          const network = await Network.getNetworkStateAsync().catch(() => null);
          const offline = network?.isConnected === false || network?.isInternetReachable === false;
          const terrain = await loadTerrainElevationState(trailId, route, offline).catch(() => null);
          if (terrain?.status === "ready") {
            elevation = trailElevationFromTerrain(trailId, route, terrain.data);
          }
        }
      }
      setTrail({ ...loadedTrail, elevation });
    } catch {
      setError("No pudimos consultar la altimetria de este sendero.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  return (
    <ScreenShell>
      <TopBar title="Altimetria" onBack={() => router.back()} />
      <ScrollView showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: Math.max(28, insets.bottom + 24) }}>
        {loading ? <StatusNotice isLoading title="Consultando elevacion" message="Cargando el perfil del sendero." /> : null}
        {error ? <StatusNotice title="Altimetria no disponible" message={error} tone="error" actionLabel="Reintentar" onAction={load} /> : null}
        {!loading && !error && trail ? (
          <>
            <Text style={styles.name}>{trail.name}</Text>
            <Text style={styles.location}>{trail.location}</Text>
            <ElevationProfile elevation={trail.elevation} onRetry={load} />
          </>
        ) : null}
      </ScrollView>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  name: { fontSize: 22, lineHeight: 28, fontWeight: "800", color: colors.ink, marginTop: 8 },
  location: { fontSize: 14, lineHeight: 20, color: colors.muted, marginTop: 6 },
});

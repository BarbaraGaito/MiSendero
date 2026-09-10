import { useCallback, useState } from "react";
import { router, useFocusEffect } from "expo-router";
import { Text } from "react-native";
import { getActiveRouteSession, RouteSessionState } from "../../services/routeSession";
import { Card, PrimaryButton, colors } from "./MiSenderoUI";

export function ResumeRouteCard() {
  const [route, setRoute] = useState<RouteSessionState | null>(null);
  useFocusEffect(useCallback(() => {
    let active = true;
    void getActiveRouteSession().then((value) => { if (active) setRoute(value); }).catch(() => undefined);
    return () => { active = false; };
  }, []));
  if (!route) return null;
  return <Card tone="orange">
    <Text style={{ color: colors.ink, fontSize: 17, fontWeight: "700" }}>Tenés un recorrido {route.state === "paused" ? "en pausa" : "abierto"}</Text>
    <Text style={{ color: colors.muted, marginVertical: 8 }}>Conservamos el inicio y los puntos GPS guardados. El registro requiere la app abierta.</Text>
    <PrimaryButton label="Volver a mi recorrido" onPress={() => router.push({
      pathname: route.state === "paused" ? "/descanso" : "/route-map",
      params: { id: String(route.trail_id), startedAt: String(route.started_at), active: "1" },
    })} />
  </Card>;
}

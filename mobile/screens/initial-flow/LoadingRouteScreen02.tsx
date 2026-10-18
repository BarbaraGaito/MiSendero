import { Redirect, useLocalSearchParams } from "expo-router";

// Keep older links connected to the current trail detail.
export default function LoadingRouteScreen02() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id);
  return <Redirect href={Number.isInteger(trailId) && trailId > 0
    ? { pathname: "/trail-detail", params: { id: String(trailId) } }
    : "/explorar-rutas"} />;
}
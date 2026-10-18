import { Redirect, useLocalSearchParams } from "expo-router";

export default function OfflineZoneDetail20Screen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id);
  return <Redirect href={Number.isInteger(trailId) && trailId > 0
    ? { pathname: "/trail-detail", params: { id: String(trailId) } }
    : "/offline-buscar"} />;
}
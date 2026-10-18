import { Redirect, useLocalSearchParams } from "expo-router";

export default function DownloadMapScreen03() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id);
  return <Redirect href={Number.isInteger(trailId) && trailId > 0
    ? { pathname: "/offline-descarga", params: { id: String(trailId) } }
    : "/offline-buscar"} />;
}
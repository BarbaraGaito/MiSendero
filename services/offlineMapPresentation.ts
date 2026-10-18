import type { OfflineMap } from "./offlineMaps";

export function offlineMapStatusLabel(map: OfflineMap): string {
  if (map.status === "disponible" && map.totalTiles > 0 && map.downloadedTiles >= map.totalTiles && map.verifiedAt != null) return "Disponible sin conexión";
  if (map.status === "error") return "Reintentar descarga";
  if (map.totalTiles > 0 && map.downloadedTiles < map.totalTiles) return `Descarga sin finalizar · ${Math.max(0, Math.min(99, Math.round(map.downloadedTiles / map.totalTiles * 100)))}%`;
  return "Revisar descarga";
}

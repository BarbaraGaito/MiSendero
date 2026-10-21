import * as FileSystem from "expo-file-system/legacy";
import type { Trail } from "../types";
import { parseRouteCoordinates } from "./geoUtils";
import type { Coordinate } from "./geoUtils";

export type BasicMapFeature = {
  id: string;
  kind: "forest" | "water" | "river" | "road" | "path" | "place";
  name?: string;
  closed?: boolean;
  points: Coordinate[];
};
export type BasicMapRegion = {
  id: string;
  bounds: { south: number; north: number; west: number; east: number };
  sourceDate: string;
  features: BasicMapFeature[];
};
export type BasicOfflineMap = BasicMapRegion & {
  version: 1;
  routeKey: string;
  attribution: string;
  license: string;
  licenseUrl: string;
};
const catalog = require("../assets/offline-maps/catalog.json") as { maps: BasicMapRegion[]; attribution: string; license: string; licenseUrl: string };
const directory = `${FileSystem.documentDirectory || ""}misendero-basic-maps/`;
const uriFor = (trail: Trail) => `${directory}${trail.id}.json`;
const routeKey = (trail: Trail) => JSON.stringify([trail.route_coordinates, trail.center_lat, trail.center_lng]);
const pointsFor = (trail: Trail): Coordinate[] => {
  const route = parseRouteCoordinates(trail.route_coordinates);
  return route.length ? route : typeof trail.center_lat === "number" && typeof trail.center_lng === "number"
    ? [[trail.center_lat, trail.center_lng]] : [];
};
export function containsMapCoordinate(region: BasicMapRegion, [lat,lon]: Coordinate) {
  return lat >= region.bounds.south && lat <= region.bounds.north && lon >= region.bounds.west && lon <= region.bounds.east;
}
export async function readBasicOfflineMap(trail: Trail): Promise<BasicOfflineMap | null> {
  if (!FileSystem.documentDirectory) return null;
  try {
    const info = await FileSystem.getInfoAsync(uriFor(trail));
    if (!info.exists) return null;
    const data = JSON.parse(await FileSystem.readAsStringAsync(uriFor(trail))) as BasicOfflineMap;
    const points = pointsFor(trail);
    if (data.version !== 1 || data.routeKey !== routeKey(trail) || !points.length ||
        data.license !== catalog.license || data.licenseUrl !== catalog.licenseUrl || data.attribution !== catalog.attribution ||
        !Number.isFinite(Date.parse(data.sourceDate)) ||
        !Array.isArray(data.features) || !data.features.length || !points.every(p => containsMapCoordinate(data,p)) ||
        !data.features.every(f => ["forest","water","river","road","path","place"].includes(f.kind) &&
          (f.name === undefined || typeof f.name === "string") &&
          Array.isArray(f.points) && f.points.length > 0 && f.points.every(p => Array.isArray(p) && p.length === 2 &&
            Number.isFinite(p[0]) && Number.isFinite(p[1]) && Math.abs(p[0]) <= 85 && Math.abs(p[1]) <= 180))) return null;
    return data;
  } catch { return null; }
}

// The source data is prepared once, ahead of release. A download unpacks only
// the selected region into persistent app storage; no public API, key or 3D data.
export async function saveBasicOfflineMap(trail: Trail, onProgress?: (done: number,total: number) => void,
  options: { shouldCancel?: () => boolean } = {}) {
  if (!FileSystem.documentDirectory) {
    throw Object.assign(new Error("Este dispositivo no permite guardar mapas sin conexión."), {code:"storage-unavailable"});
  }
  const checkCancelled = () => {
    if (options.shouldCancel?.()) throw Object.assign(new Error("Descarga cancelada."),{code:"download-cancelled"});
  };
  checkCancelled();
  const points = pointsFor(trail);
  const region = points.length ? catalog.maps.filter(r => points.every(p => containsMapCoordinate(r,p)))
    .sort((a,b) => (a.bounds.north-a.bounds.south)*(a.bounds.east-a.bounds.west) -
      (b.bounds.north-b.bounds.south)*(b.bounds.east-b.bounds.west))[0] : null;
  if (!region) throw Object.assign(new Error("Todavía no hay un mapa básico disponible para esta zona."), {code:"basic-map-unavailable"});
  onProgress?.(0,3);
  const data: BasicOfflineMap = { ...region,version:1,routeKey:routeKey(trail),
    attribution:catalog.attribution,license:catalog.license,licenseUrl:catalog.licenseUrl };
  const json = JSON.stringify(data);
  await FileSystem.makeDirectoryAsync(directory,{intermediates:true});
  const uri = uriFor(trail);
  const temporary = `${uri}.download`;
  let committed = false;
  try {
    checkCancelled();
    onProgress?.(1,3);
    await FileSystem.writeAsStringAsync(temporary,json);
    // Verify the bytes on disk before replacing a previous package.
    if (await FileSystem.readAsStringAsync(temporary) !== json) throw new Error("basic-map-write-failed");
    checkCancelled();
    onProgress?.(2,3);
    await FileSystem.moveAsync({from:temporary,to:uri});
    committed = true;
    checkCancelled();
    if (!await readBasicOfflineMap(trail)) throw new Error("basic-map-verification-failed");
    const info = await FileSystem.getInfoAsync(uri);
    onProgress?.(3,3);
    return {downloadedTiles:1,totalTiles:1,sizeMb: info.exists ? (info.size || 0)/1024/1024 : 0};
  } catch (error) {
    if (committed) await FileSystem.deleteAsync(uri,{idempotent:true}).catch(() => undefined);
    throw error;
  } finally {
    await FileSystem.deleteAsync(temporary,{idempotent:true}).catch(() => undefined);
  }
}
export async function deleteBasicOfflineMap(trail: Trail) {
  if (!FileSystem.documentDirectory) return;
  await FileSystem.deleteAsync(uriFor(trail),{idempotent:true});
  await FileSystem.deleteAsync(`${uriFor(trail)}.download`,{idempotent:true});
}

export async function getBasicOfflineMapSizeMb(trail: Trail) {
  const info = await FileSystem.getInfoAsync(uriFor(trail));
  return info.exists ? (info.size || 0) / 1024 / 1024 : 0;
}

import { ScrollView, Text } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import * as Linking from "expo-linking";
import { Card, PrimaryButton, ScreenShell, TopBar } from "../components/MiSenderoUI";
import { OPEN_METEO_ELEVATION_ATTRIBUTION } from "../../services/terrainElevation";
import { TERRAIN_TILES_ATTRIBUTION } from "../../services/terrainTiles";
import { getTrailById } from "../../services/trailRepository";
import type { Trail } from "../../types";

const links = [
  ["OpenStreetMap: licencia de los datos", "https://www.openstreetmap.org/copyright"],
  ["OpenStreetMap: política de tiles", "https://operations.osmfoundation.org/policies/tiles/"],
  ["Open-Meteo: elevación GLO-90", "https://open-meteo.com/en/docs/elevation-api"],
  ["Mapzen Terrain Tiles: datos DEM públicos en AWS", "https://registry.opendata.aws/terrain-tiles/"],
  ["Mapzen Terrain Tiles: fuentes y atribuciones", "https://github.com/tilezen/joerd/blob/master/docs/attribution.md"],
  ["Copernicus: condiciones y avisos del producto (GLO-90, artículo 6)", "https://dataspace.copernicus.eu/sites/default/files/media/files/2025-06/copernicus_contributing_mission_data_access_v2_cop_dem_licenses.pdf"],
  ["Esri: atribuciones de mapas", "https://support.esri.com/en-us/knowledge-base/what-is-the-correct-way-to-cite-an-arcgis-online-basema-000012040"],
  ["Esri World Imagery: fuentes y créditos", "https://doc.arcgis.com/en/data-appliance/2024/maps/world-imagery.htm"],
] as const;
export default function AttributionsScreen() {
  const { trailId } = useLocalSearchParams<{ trailId?: string }>();
  const [trail, setTrail] = useState<Trail | null>(null);
  useEffect(() => {
    let active = true;
    setTrail(null);
    const id = Number(trailId);
    if (Number.isSafeInteger(id) && id > 0) {
      void getTrailById(id).then(value => { if (active) setTrail(value); }).catch(() => {});
    }
    return () => { active = false; };
  }, [trailId]);
  const photo = trail?.provenance?.photo;
  return <ScreenShell>
    <TopBar title="Fuentes y licencias" onBack={() => router.back()} />
    <ScrollView contentContainerStyle={{ paddingBottom: 30 }}>
      {trail?.provenance?.mapping ? <Card>
        <Text>{trail.name}</Text>
        <Text>Cartografía: {trail.provenance.mapping.source} · {trail.provenance.mapping.license}</Text>
        <PrimaryButton label="Fuente del trazado" tone="secondary" onPress={() => { void Linking.openURL(trail.provenance!.mapping!.source_url); }} />
      </Card> : null}
      {photo ? <Card>
        <Text>Fotografía: {photo.author} · {photo.license}</Text>
        {photo.context ? <Text>{photo.context}</Text> : null}
        <PrimaryButton label="Fuente de la fotografía" tone="secondary" onPress={() => { void Linking.openURL(photo.page_url); }} />
      </Card> : null}
      <Card><Text>{TERRAIN_TILES_ATTRIBUTION}</Text><Text>El relieve 3D usa mosaicos DEM reales. La fuente y el detalle disponible pueden variar según la zona; la interpolación no agrega precisión al relevamiento original.</Text></Card>
      <Card><Text>{OPEN_METEO_ELEVATION_ATTRIBUTION}</Text><Text>Los perfiles y las grillas antiguas pueden usar alturas de Open-Meteo/Copernicus. Las entidades responsables del programa Copernicus no asumen responsabilidad por el uso de WorldDEM-90. El uso de estos datos no implica que respalden MiSendero.</Text></Card>
      <Card><Text>Datos OpenStreetMap: © colaboradores de OpenStreetMap, ODbL. Topografía Esri: Esri, DeLorme, HERE, TomTom, Intermap, increment P Corp., GEBCO, USGS, FAO, NPS, NRCAN, GeoBase, IGN, Kadaster NL, Ordnance Survey, Esri Japan, METI, Esri China, swisstopo, MapmyIndia y comunidad GIS. Imágenes: Esri, Maxar, Earthstar Geographics y comunidad GIS. La procedencia específica de cada trazado se conserva en los créditos del sendero. Las fuentes pueden variar según la zona; consultá los créditos del servicio.</Text></Card>
      <Card><Text>Los créditos de cada foto y trazado están disponibles en la ficha del sendero. Las fuentes de los mapas pueden variar según la zona.</Text></Card>
      {process.env.EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION ? <Card><Text>{process.env.EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION}</Text></Card> : null}
      {links.map(([label, url]) => <PrimaryButton key={url} label={label} tone="secondary" onPress={() => { void Linking.openURL(url); }} />)}
    </ScrollView>
  </ScreenShell>;
}

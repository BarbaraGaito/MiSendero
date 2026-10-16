import { ScrollView, Text } from "react-native";
import { router } from "expo-router";
import * as Linking from "expo-linking";
import { Card, PrimaryButton, ScreenShell, TopBar } from "../components/MiSenderoUI";
import { OPEN_METEO_ELEVATION_ATTRIBUTION } from "../../services/terrainElevation";

const links = [
  ["OpenStreetMap: licencia de los datos", "https://www.openstreetmap.org/copyright"],
  ["OpenStreetMap: política de tiles", "https://operations.osmfoundation.org/policies/tiles/"],
  ["Open-Meteo: elevación GLO-90", "https://open-meteo.com/en/docs/elevation-api"],
  ["Copernicus: condiciones y avisos del producto (GLO-90, artículo 6)", "https://dataspace.copernicus.eu/sites/default/files/media/files/2025-06/copernicus_contributing_mission_data_access_v2_cop_dem_licenses.pdf"],
  ["Esri: atribuciones de mapas", "https://support.esri.com/en-us/knowledge-base/what-is-the-correct-way-to-cite-an-arcgis-online-basema-000012040"],
  ["Esri World Imagery: fuentes y créditos", "https://doc.arcgis.com/en/data-appliance/2024/maps/world-imagery.htm"],
] as const;
export default function AttributionsScreen() {
  return <ScreenShell>
    <TopBar title="Fuentes y licencias" onBack={() => router.back()} />
    <ScrollView contentContainerStyle={{ paddingBottom: 30 }}>
      <Card><Text>{OPEN_METEO_ELEVATION_ATTRIBUTION}</Text><Text>El perfil y la vista de terreno se calculan a partir de alturas recibidas del proveedor. Las entidades responsables del programa Copernicus no asumen responsabilidad por el uso de WorldDEM-90. El uso de estos datos no implica que respalden MiSendero.</Text></Card>
      <Card><Text>Mapa y trazados: © colaboradores de OpenStreetMap, ODbL. Topografía Esri: Esri, DeLorme, HERE, TomTom, Intermap, increment P Corp., GEBCO, USGS, FAO, NPS, NRCAN, GeoBase, IGN, Kadaster NL, Ordnance Survey, Esri Japan, METI, Esri China, swisstopo, MapmyIndia y comunidad GIS. Imágenes: Esri, Maxar, Earthstar Geographics y comunidad GIS. Las fuentes pueden variar según la zona; consultá los créditos del servicio.</Text></Card>
      <Card><Text>Las fotos y fuentes de cada sendero se detallan en su ficha. La descarga de mapas requiere un proveedor con uso offline autorizado. Las licencias de datos y las condiciones del servicio son independientes.</Text></Card>
      {process.env.EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION ? <Card><Text>{process.env.EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION}</Text></Card> : null}
      {links.map(([label, url]) => <PrimaryButton key={url} label={label} tone="secondary" onPress={() => { void Linking.openURL(url); }} />)}
    </ScrollView>
  </ScreenShell>;
}

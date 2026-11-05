import { Stack } from "expo-router";
import { useFonts } from "expo-font";
import {
  BricolageGrotesque_400Regular,
  BricolageGrotesque_500Medium,
  BricolageGrotesque_700Bold,
  BricolageGrotesque_800ExtraBold,
} from "@expo-google-fonts/bricolage-grotesque";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { SyncCoordinator } from "../services/SyncCoordinator";
import { RouteTrackingCoordinator } from "../services/RouteTrackingCoordinator";
import { FallDetectionCoordinator } from "../services/fallDetection/FallDetectionCoordinator";
import { StoragePrivacyGuard } from "../services/StoragePrivacyGuard";
import { ConnectivityProvider } from "../services/ConnectivityProvider";

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    BricolageGrotesque_400Regular,
    BricolageGrotesque_500Medium,
    BricolageGrotesque_700Bold,
    BricolageGrotesque_800ExtraBold,
  });

  if (!fontsLoaded && !fontError) {
    return null;
  }

  return (
    <SafeAreaProvider>
      <ConnectivityProvider>
      <StoragePrivacyGuard>
      <SyncCoordinator />
      <RouteTrackingCoordinator />
      <FallDetectionCoordinator />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="explore" />
        <Stack.Screen name="descubri-tu-sendero" />
        <Stack.Screen name="trail-detail" />
        <Stack.Screen name="sendero-opiniones" />
        <Stack.Screen name="route-map" />
        <Stack.Screen name="trail-start" />
        <Stack.Screen name="terminos-condiciones" />
        <Stack.Screen name="alerta-ruta" />
        <Stack.Screen name="actualizacion-fallida" />
        <Stack.Screen name="buscar-mapas-offline" />
        <Stack.Screen name="confirmar-sos" />
        <Stack.Screen name="caida-detectada" options={{ gestureEnabled: false }} />
        <Stack.Screen name="contacto-seguridad" />
        <Stack.Screen name="conexion-perdida" />
        <Stack.Screen name="cargando-ruta" />
        <Stack.Screen name="descargar-mapa" />
        <Stack.Screen name="descanso" />
        <Stack.Screen name="recorrido-finalizado" />
        <Stack.Screen name="reloj-salud" />
        <Stack.Screen name="explorar-rutas" />
        <Stack.Screen name="parques-nacionales" />
        <Stack.Screen name="parque-nacional" />
        <Stack.Screen name="explorar-skeletons" />
        <Stack.Screen name="filtros-mapas" />
        <Stack.Screen name="history" />
        <Stack.Screen name="inicio" />
        <Stack.Screen name="onboarding-experiencia" />
        <Stack.Screen name="mapas-offline" />
        <Stack.Screen name="mis-actividades" />
        <Stack.Screen name="offline-buscar" />
        <Stack.Screen name="offline-descarga" />
        <Stack.Screen name="offline-descarga-completa" />
        <Stack.Screen name="offline-detalle-zona" />
        <Stack.Screen name="offline-filtros" />
        <Stack.Screen name="offline-mapas-descargados" />
        <Stack.Screen name="reportar-terreno" />
        <Stack.Screen name="reporte-guardado" />
        <Stack.Screen name="perfil" />
      </Stack>
      </StoragePrivacyGuard>
      </ConnectivityProvider>
    </SafeAreaProvider>
  );
}

import React, { useEffect } from "react";
import { Stack } from "expo-router";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { initDB } from "../database/database";

export default function RootLayout() {
  useEffect(() => {
    initDB();
  }, []);

  return (
    <SafeAreaProvider>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="explore" />
        <Stack.Screen name="trail-detail" />
        <Stack.Screen name="route-map" />
        <Stack.Screen name="trail-start" />
        <Stack.Screen name="alerta-ruta" />
        <Stack.Screen name="actualizacion-fallida" />
        <Stack.Screen name="buscar-mapas-offline" />
        <Stack.Screen name="confirmar-sos" />
        <Stack.Screen name="contacto-seguridad" />
        <Stack.Screen name="conexion-perdida" />
        <Stack.Screen name="cargando-ruta" />
        <Stack.Screen name="descargar-mapa" />
        <Stack.Screen name="descanso" />
        <Stack.Screen name="recorrido-finalizado" />
        <Stack.Screen name="explorar-rutas" />
        <Stack.Screen name="explorar-skeletons" />
        <Stack.Screen name="filtros-mapas" />
        <Stack.Screen name="history" />
        <Stack.Screen name="inicio" />
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
    </SafeAreaProvider>
  );
}

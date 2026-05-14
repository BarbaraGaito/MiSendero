# MiSendero MVP

MVP de una app de trekking con enfoque **wearable-first** y **offline-first**:

- `watch`: interfaz principal simulada estilo smartwatch
- `mobile`: logica principal y vistas del celular
- `services`: Bluetooth simulado, GPS/tracking y sync offline
- `database`: persistencia local con SQLite
- `ai`: clasificacion simple de fatiga

## Estructura

```text
.
|-- App.tsx
|-- ai/
|   `-- fatigue.ts
|-- database/
|   `-- trekkingDb.ts
|-- mobile/
|   |-- components/
|   |   |-- HistoryList.tsx
|   |   `-- PhoneDashboard.tsx
|   `-- hooks/
|       `-- useTrekkingController.ts
|-- services/
|   |-- bluetoothSimulator.ts
|   |-- locationTracker.ts
|   |-- simulationProfile.ts
|   `-- syncService.ts
|-- types/
|   `-- index.ts
|-- utils/
|   `-- format.ts
`-- watch/
    |-- components/
    |   `-- WatchFace.tsx
    `-- hooks/
        `-- useWatchBridge.ts
```

## Modulos

- `watch/components/WatchFace.tsx`
  Simula la UI del smartwatch con HR, tiempo, fatiga, alertas y botones `Iniciar`, `Detener`, `SOS`.

- `watch/hooks/useWatchBridge.ts`
  Escucha la respuesta del celular y actualiza el estado visible del reloj.

- `mobile/hooks/useTrekkingController.ts`
  Orquesta todo el flujo: inicio de sesion, recepcion de HR, calculo de fatiga, tracking, guardado en SQLite y cierre de sesion.

- `mobile/components/PhoneDashboard.tsx`
  Vista principal del celular con metricas live, modo offline y logs de sincronizacion simulada.

- `mobile/components/HistoryList.tsx`
  Historial de sesiones con duracion, distancia y fatiga promedio.

- `services/bluetoothSimulator.ts`
  Simula la comunicacion reloj -> celular y celular -> reloj, con envio de datos cada 5 segundos.

- `services/locationTracker.ts`
  Usa `expo-location` si hay permisos. Si no, cae automaticamente a una ruta simulada para seguir funcionando offline.

- `services/simulationProfile.ts`
  Perfil base de la simulacion: HR y velocidad para probar fatiga alta y periodos de detencion.

- `services/syncService.ts`
  Genera mensajes de sincronizacion local y eventos offline/SOS.

- `database/trekkingDb.ts`
  Crea tablas `sessions` y `samples`, guarda datos HR y resuelve el historial.

- `ai/fatigue.ts`
  Implementa la regla simple de fatiga:
  - HR alto + velocidad baja => `alto`
  - HR moderado / esfuerzo sostenido => `medio`
  - HR controlado + buen ritmo => `bajo`

## Flujo del MVP

1. El usuario inicia el trekking desde el reloj.
2. El reloj simulado envia HR cada 5 segundos por el puente Bluetooth local.
3. El celular recibe HR, calcula fatiga, actualiza tracking y persiste muestras en SQLite.
4. El celular responde al reloj con el estado de fatiga y alertas visuales.
5. Al detener la sesion, se guarda el resumen y aparece en historial.

## Arranque

1. Instalar dependencias:

```bash
npm install
```

2. Si Expo ajusta versiones recomendadas, ejecutar:

```bash
npx expo install expo-location expo-sqlite
```

3. Iniciar la app:

```bash
npm start
```

> Recomendado: correr en Android/Expo Go o emulador para probar el flujo tipo reloj + celular.

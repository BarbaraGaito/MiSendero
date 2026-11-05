# Protocolo de pruebas en dispositivo — detección de caídas (pendiente)

Estas pruebas **no se ejecutaron** (no hay Android SDK ni teléfono en el entorno de desarrollo). Hasta completarlas, ninguna de las capacidades siguientes puede darse por validada. **No realizar caídas físicas peligrosas**: usar movimientos seguros (caminar, sentarse, dejar caer el teléfono sobre una cama a baja altura) solo para verificar captura y calidad de señal, no sensibilidad.

Prerrequisito: build de desarrollo (`npx eas-cli build --profile development`) o preview con `expo-sensors` ya incluido.

| # | Prueba | Cómo | Resultado esperado | Estado |
|---|---|---|---|---|
| 1 | Sensor disponible y permiso | Activar el interruptor en *Antes de salir* | Aviso de limitaciones; si hay acelerómetro queda activado; si no, mensaje claro | Pendiente |
| 2 | Captura real con la app visible | Iniciar recorrido con la función activa; observar la línea de estado | “Monitoreo activo (~50 Hz)”. Registrar la frecuencia medida por modelo de teléfono | Pendiente |
| 3 | Frecuencia de muestreo | Revisar `counters.skipped` y `measuredRateHz` tras 10 min caminando | `skipped` bajo; si hay muchos, recalibrar `LOOSE_SPACING_MS` (hoy 45 ms, criterio de ingeniería) | Pendiente |
| 4 | Inferencia en el dispositivo | Registrar tiempo por ventana con `performance.now()` en un build de depuración | ≪ 20 ms; Node de escritorio mide 0,47 ms | Pendiente |
| 5 | Sin Internet | Modo avión durante todo el recorrido | Detección, asistencia y registro local funcionan | Pendiente |
| 6 | Pantalla bloqueada | Bloquear 2 min con la función activa; volver | Estado “interrumpido… sin protección” si el sistema detuvo el sensor; documentar por marca/versión de Android | Pendiente |
| 7 | Segundo plano | Cambiar a otra app 2 min | Igual que 6 (esperable: sin datos en iOS y en Android sin servicio en primer plano) | Pendiente |
| 8 | Ahorro de batería / Doze | Activar ahorro de batería y repetir 6 | Documentar si se interrumpe | Pendiente |
| 9 | Interrupciones | Llamada entrante, apertura de la cámara | Estado correcto y recuperación sin reiniciar la app | Pendiente |
| 10 | Estoy bien / SOS | Provocar la pantalla de asistencia con una compilación de depuración que fuerce el evento (nunca en producción) | “Estoy bien” guarda la respuesta; “Solicitar ayuda” abre `/confirmar-sos` sin enviar nada | Pendiente |
| 11 | SOS con SIM | Desde el SOS, SMS a un contacto de prueba, con y sin datos móviles | SMS sale por cobertura celular aunque no haya Internet; el texto distingue ambas cosas | Pendiente |
| 12 | Energía | 60 min con y sin monitoreo, misma pantalla y ruta; `adb shell dumpsys batterystats --reset` antes y `dumpsys batterystats` después | Diferencia de consumo atribuible a MiSendero | Pendiente |
| 13 | Posiciones | Registrar (sin caídas) los falsos positivos al caminar/saltar con el teléfono en bolsillo, mochila y mano | Informar por posición; solo el bolsillo tiene respaldo de entrenamiento | Pendiente |

## Implementación pendiente: servicio en primer plano de Android

Diseño propuesto (no implementado): módulo Expo local con un `Service` que muestre una notificación persistente y tome un `PARTIAL_WAKE_LOCK` mientras haya un recorrido con la detección activa, más un config plugin que agregue `FOREGROUND_SERVICE` y el tipo de servicio permitido en Android 14 (`specialUse` con justificación, o `health` si se solicita `ACTIVITY_RECOGNITION`). El JS (expo-sensors + el pipeline actual) seguiría procesando; el servicio solo evita que el proceso quede suspendido. Debe compilarse y probarse en dispositivos reales (pruebas 6–9 y 12) antes de afirmar protección con pantalla bloqueada, y revisarse contra las políticas de Google Play. En iOS no existe un camino equivalente sin un modo de fondo (p. ej. ubicación continua).

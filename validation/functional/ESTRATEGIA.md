# Estrategia de pruebas funcionales de MiSendero

La validación se organiza por comportamientos de navegación, orientación y asistencia con conectividad limitada. Cada escenario posee un identificador MF, trazabilidad al catálogo RF/RNF y resultados separados por nivel. La cobertura de código y la cantidad de pruebas aprobadas son indicadores independientes de la validación funcional y del comportamiento en dispositivos.

El catálogo ejecutable está en [cases.cjs](../../testing/functional/cases.cjs). La matriz de cada ejecución desarrolla objetivo, precondiciones, datos, pasos, resultado esperado, resultado obtenido, evidencia, estado y observaciones para los 15 escenarios. Los resultados se obtienen de las aserciones individuales informadas por Jest; una suite aprobada por sí sola no acredita un escenario completo.

| Nivel | Unidad de validación | Entorno de ejecución | Alcance de la evidencia |
|---|---|---|---|
| Unitarias | Conversión y validación de lecturas, ubicación, inferencia y reglas de estado | Jest; entradas y relojes controlados | Lógica y contratos de entrada/salida |
| Integración | Servicios y SQL; pantallas y servicios; rutas HTTP y persistencia | SQLite en Node; React Test Renderer; Express, Supertest y pg-mem | Interacciones entre los componentes ejecutados; se identifican los límites sustituidos |
| End-to-end | Interfaz de una build instalada, servicios locales y backend de prueba conectados | Aplicación instalada y servidor dedicado | Flujo completo real, sin reemplazar los componentes que se pretende acreditar |
| Manuales | Lectura de estados, recuperación visible y acciones mediante interfaz | Sesión guiada con operador y datos de ensayo | Resultado observado, fecha y evidencia de cada paso |
| Dispositivo físico | GPS, permisos del sistema, almacenamiento nativo, salud, batería y restricciones de ejecución | Teléfono identificado; wearable cuando corresponda | Comportamiento del hardware y sistema operativo concretos |

React Test Renderer no ejecuta una aplicación nativa ni se clasifica como end-to-end. Supertest con pg-mem no acredita una instalación de PostgreSQL. Los archivos SQLite de ensayo sí contienen escrituras reales del motor SQLite de Node; la recuperación entre procesos conserva la sustitución del límite nativo de Expo y de la identidad de prueba. Ninguna de estas categorías constituye una evaluación de usabilidad o un ensayo de campo.

Los escenarios críticos son MF07 (efecto único de los reintentos), MF12 (SOS y confirmaciones) y MF15 (eliminación de cuenta). La disponibilidad offline y la persistencia tienen prioridad alta. El estado final de cada escenario conserva las verificaciones aprobadas, las fallidas y las que no se ejecutaron; no se transforma una validación parcial en una aprobación global.

## Preparación reproducible

Desde la raíz del repositorio, con Node 24 y las dependencias fijadas en los lockfiles:

```powershell
npm.cmd ci --legacy-peer-deps --ignore-scripts
npm.cmd ci --prefix backend --ignore-scripts
npm.cmd run test:functional -- --output=validation/functional/mi-ejecucion --seed=20261017
```

El directorio de salida debe estar vacío. El comando registra versiones instaladas y lockfiles, fecha UTC y calendario de Buenos Aires, revisión Git y cambios locales, inventario de herramientas nativas, comandos y códigos de salida. Ejecuta comprobación de tipos, compilación del módulo de IA del backend, controles del agregador de cobertura, las suites completas del cliente y backend y la sonda de aceptación MF07. No utiliza una cuenta operativa, un proveedor de IA pago ni un servicio de mapas real.

La sonda de aceptación forma parte de `test:functional`; las suites convencionales continúan disponibles mediante `test` y `test:coverage`. Un fallo de aceptación hace que `test:functional` termine con código 1 aunque las suites convencionales aprueben. El nombre `.probe.js` distingue este ensayo de aceptación, que se selecciona explícitamente en el comando y se incluye en los totales de la campaña. No se marca como omisión ni como fallo esperado.

Para repetir con otro orden:

```powershell
npm.cmd run test:functional -- --output=validation/functional/mi-repeticion --seed=73
```

Las bases y las cuentas de cada suite están aisladas. La prueba de recuperación utiliza un directorio temporal exclusivo y lo elimina al finalizar; no abre la base de una instalación del usuario. Los casos de batería y SOS desmontan las pantallas y los listeners. La suite de preparación dispone de 30 segundos para la inicialización de componentes nativos bajo instrumentación: es un presupuesto del arnés, sin modificar sus aserciones funcionales ni acreditar latencia del producto. La cola se vacía antes de cada caso; el tiempo del backoff se avanza mediante su dato persistido, sin esperas arbitrarias. La reproducción compara estados, contenido e identidad, sin exigir tokens, tiempos de duración o IDs globales idénticos.

La campaña registra la cobertura de líneas, sentencias, ramas y funciones del inventario completo del producto JS/TS. El objetivo interno es al menos 85% de líneas ejecutables con agregación ponderada de cliente y backend. La ejecución de MF07 se informa por separado de la medición de cobertura de las suites convencionales. Las pruebas Python de investigación poseen su propio procedimiento y no se suman a esta campaña funcional.

## Protocolo de end-to-end y dispositivo

Los pasos específicos están definidos en cada fila de la matriz. Antes de una sesión se identifica operador, fecha, modelo, sistema operativo, estado de batería, permisos, conectividad, versión de la build y hash del código. Se utiliza un backend y cuentas desechables con datos conocidos, incluido un usuario de control para verificar aislamiento. La ejecución real requiere un proveedor de mapas autorizado y configurado; las descargas automatizadas actuales utilizan fixtures.

Cada escenario se ejecuta primero con sus precondiciones cumplidas y luego con la condición adversa indicada. Para offline se desactivan Wi-Fi y datos; para ausencia de cobertura celular se registra además la situación del servicio celular. Se conserva el permiso GPS cuando el escenario sólo altera conectividad. Para MF05 se distinguen cierre y reapertura, reinicio del sistema y terminación durante una escritura: son ensayos distintos. La prueba automatizada realizada sólo acredita escrituras confirmadas y lectura desde otro proceso Node.

En MF07, el servidor recibe la primera petición y se descarta su respuesta antes del reintento; se cuentan las filas por observación y se comparan los IDs. El control se realiza por tipo de entidad: el resultado de SOS no se extrapola a reportes. En MF08, una corrección o retiro del servidor debe reemplazar la copia local. La carrera de ediciones entre instalaciones conserva un registro separado de peticiones, orden de aceptación y estado final; no se atribuye al sistema una fusión de versiones no observada.

En MF10 se utiliza un volumen o instalación de ensayo limitado para producir el error de espacio; se observa el error de escritura y el estado posterior del paquete. El error ENOSPC inyectado no acredita agotamiento de almacenamiento nativo. En MF11 se documenta qué restricción de batería se aplicó y por cuánto tiempo; el retiro del watcher en segundo plano es el comportamiento previsto por RNF-06. No se presupone tracking continuo con la pantalla bloqueada.

Los ensayos de SOS emplean un contacto ficticio o un canal dedicado de prueba y no llaman ni avisan a servicios de emergencia reales. Se registran por separado guardado local, aceptación de la API, apertura o cancelación de Mensajes y cualquier confirmación del canal. Abrir el compositor o aceptar una petición HTTP no constituye entrega al contacto. La eliminación de MF15 se ejecuta únicamente sobre las cuentas desechables preparadas para ese escenario.

## Registro y criterios de cierre

Por cada variante manual, E2E o física se completa: ID del escenario y variante, build y entorno, datos de entrada, marcas horarias, pasos efectivamente realizados, resultado observado, evidencia y estado. Un caso se aprueba sólo cuando se observa todo su resultado esperado en ese nivel. Un impedimento de preparación se registra como bloqueado; la ausencia de ejecución se registra como no ejecutado. Los campos sin observación no reciben una aprobación por inferencia.

Las evidencias reales pueden consistir en capturas de la interfaz, registros del dispositivo, peticiones y respuestas del backend y consultas sobre las bases de ensayo. Se preserva la relación entre esas evidencias y el ID de caso. Los archivos JSON y TXT de la campaña automatizada son salidas efectivamente producidas; no se proporcionan capturas ni registros de dispositivos que no se utilizaron.

Los entregables por ejecución son `matrix.md`, `matrix.csv`, `matrix.json`, `summary.json`, resultados Jest por componente y sonda, salidas TXT, entorno y comandos, contadores de cobertura por archivo y manifiestos SHA-256. Los reportes HTML y LCOV completos se generan localmente bajo `coverage/`. Los archivos entregados en `validation/functional/` no requieren acceso a una carpeta `docs/`.

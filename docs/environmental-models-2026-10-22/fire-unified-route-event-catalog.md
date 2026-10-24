# Catálogo unificado de evidencia de incendios cerca de senderos argentinos

Este artefacto integra evidencia positiva de partes SNMF, detecciones activas INPE/AQUA-MODIS y eventos del Global Fire Atlas. El resultado es un catálogo común con procedencia; todavía no es un dataset listo para entrenar ni para afirmar precisión.

## Reglas de unificación

- Se filtran puntos a no más de 10 km de las polilíneas completas de los ocho senderos argentinos.
- Las detecciones INPE próximas se agrupan si son de la misma ruta, están separadas por hasta 2 días y sus coordenadas distan hasta 3 km.
- Dos fuentes distintas se fusionan solo si el par es único en ambos sentidos y cumple esa misma tolerancia temporal y espacial. Las coincidencias posibles hasta 10 km se muestran aparte.
- Cada evento conserva los registros e identificadores fuente. El acuerdo INPE–Global Fire Atlas se marca como productos de la familia MODIS, no como corroboración independiente.
- No se inventan negativos: solo se mantiene por separado la evidencia de partes SNMF con frase explícita de ausencia nacional.

## Resultado

El catálogo contiene **101 grupos de evidencia**, a partir de 23 registros de incidente SNMF cerca de ruta, 20 eventos GFA y 67 grupos espaciales de detecciones INPE. Se formaron 8 grupos con más de una fuente (9 vínculos únicos); quedaron 18 coincidencias posibles sin fusionar.

Hay 32 días con parte nacional explícito sin incendios reportados (256 pares día-sector), pero esos registros no significan ausencia física certificada ni completan toda la serie.

## Eventos por sendero

- Bosque Tallado desde la plataforma del Piltriquitron: 24
- Cerro Ventana - Hueco de la Ventana: 6
- Quebrada del Condorito - Balcon Norte: 4
- Refugio Frey desde Villa Catedral: 9
- Sendero Che Roga - Mburucuyá: 52
- Sendero Namuncura: 6

## Límite para el modelo

El catálogo unifica cuándo y dónde las fuentes aportan evidencia de fuego. No une automáticamente esos eventos con pronósticos meteorológicos: para construir ejemplos de predicción hay que asociar cada evento a un pronóstico archivado antes de su fecha, y asociar cada negativo a cobertura observable. Por eso `training_ready` sigue en `false`; la precisión del modelo no se modifica ni se recalcula con este catálogo.

El JSON reproducible incluye hashes de entradas, reglas, eventos, posibles coincidencias y procedencia completa.

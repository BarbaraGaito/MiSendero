# Catálogo para principiantes — 12/11/2026

> Esta página conserva la primera medición sobre el catálogo del repositorio. La [verificación de la API pública y la revisión posterior de tiempos](catalogo-produccion-2026-11-12/README.md) documentan el lote final que se preparó para cargar.

Se incorporan 11 fichas de dificultad baja al [lote del repositorio](../backend/src/data/beginnerCatalog20261112.js). Son fichas para planificar la visita: no se agregaron trazas, coordenadas, fotos ni desniveles calculados. La app muestra las fuentes y no ofrece mapa, navegación ni descarga para estas fichas. La dificultad es la de la fuente para el recorrido indicado; hay que consultar al administrador la habilitación y las condiciones.

| Ficha | Destino | Alcance del tiempo | Fuente |
| --- | --- | --- | --- |
| Senda de la Baliza | PN Tierra del Fuego | 30 min, ida y vuelta | [INFUETUR](https://findelmundo.tur.ar/es/senderos/4752) |
| Laguna Negra | PN Tierra del Fuego | 30 min, ida y vuelta | [INFUETUR](https://findelmundo.tur.ar/es/senderos/6544) |
| Sendero Verde | PN Iguazú | 15 min, solo ida | [Iguazú Argentina](https://iguazuargentina.com/area-cataratas/sendero-verde/) y [mapa del operador](https://iguazuargentina.com/wp-content/uploads/2026/05/Mapa_Web1-1.pdf) |
| Claro Oscuro | PP Ernesto Tornquist | 30 min, circuito completo | [Ministerio de Ambiente PBA](https://www.ambiente.gba.gob.ar/node/3063) y [Comarca Turística](https://comarcaturistica.com.ar/sendero-claroscuro/) |
| Cascada de los Duendes | PN Nahuel Huapi, desde la seccional Lago Gutiérrez | 1 h, ida y vuelta; sin el acceso desde Villa Los Coihues | [Bariloche Trekking](https://barilochetrekking.com/sendero-08/) |
| Cascada El Rincón | PN El Leoncito | Sin tiempo publicado para la variante corta | [APN](https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-el-leoncito/actividades) |
| Mirador Lago Volcán | PN Perito Moreno | Sin tiempo publicado | [APN](https://www.argentina.gob.ar/parquesnacionales/patagonia-austral/parque-nacional-perito-moreno/actividades) |
| Sendero El Bosque | PN Lanín, Huechulafquen | Sin tiempo publicado por el parque; distancia del relevamiento de campo | [PN Lanín](https://www.pnlanin.com.ar/img/32_Accesibilidad%20Parque%20Nacional%20Lan%C3%83%C2%ADn%20%281%29.pdf) y [Universidad Nacional del Comahue](https://rdi.uncoma.edu.ar/bitstream/handle/uncomaid/17926/importancia_del_sistema_de_informaci%C3%B3n_a_visitantes_en_areas_protegidas_sanchez-pascal%20-%20rdi.pdf?isAllowed=y&sequence=1) |
| Rincón de las Aves | Laguna La Zeta, Esquel | 21 min de referencia, regreso no confirmado | [Turismo Esquel](https://www.esquel.tur.ar/blog/otono-pleno-en-esquel-guia-de-senderos-para-que-elijas-tu-propia-aventura/) |
| Cerro San Bernardo–Ala Delta | Ciudad de Salta | Sin tiempo publicado; la fuente exige buen estado físico | [Turismo Ciudad de Salta](https://saltaciudad.travel/posts/trekking-cerro-san-bernardo-y-ala-delta) |
| Sendero El Funicular, cuarto puente | Sierra de San Javier, Horco Molle | 1 h 15 min de referencia, regreso no confirmado | [Tucumán Turismo](https://www.tucumanturismo.gob.ar/articulos/articulo/97/ecosendas) |

**Corrección de una ficha existente:** Cerro Leoncito pasa de `3 h` a `3 a 4 h`. La [ficha de actividades](https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-el-leoncito/actividades) y el [manual para guías de APN](https://www.argentina.gob.ar/sites/default/files/material_de_estudio_examen_de_guias_pn_el_leoncito-_2.0.pdf) se refieren a los mismos 8 km de ida y vuelta, pero publican 3 y 4 horas respectivamente. Se guardan las dos referencias, se conserva la traza existente y se exige que el rango completo encaje en el tiempo elegido.

Las fichas con tiempo ausente o de alcance dudoso no cuentan como coincidencia cuando se elige un rango. Si no existe una opción del nivel indicado, el resultado muestra «Sin opciones para tu nivel» y, en una ficha aparte, «Supera tu nivel» y «Ver ficha» para consultar la alternativa local. Las versiones anteriores de la app siguen recibiendo minutos numéricos en recomendaciones; la versión actual anuncia que admite fichas sin ese dato.

## Carga y verificación

Con el esquema ya instalado y `backend/.env` apuntando a una base local de trabajo:

```powershell
npm.cmd --prefix backend run db:catalog:beginner:preview
npm.cmd --prefix backend run db:catalog:beginner:apply
npm.cmd --prefix backend run build
node backend/scripts/auditCatalogRecommendationFit.js --baseline
node backend/scripts/auditCatalogRecommendationFit.js
```

La vista previa es de solo lectura. La carga es transaccional, omite duplicados por nombre o clave y actualiza Cerro Leoncito solo si la ficha del lote original conserva el valor de 3 h. La repetición no crea copias ni vuelve a editar esa ficha. Se verificó la carga y su repetición sobre el esquema del backend en una base de pruebas. No se modificó producción.

La auditoría compara las mismas 38 ubicaciones y 19.152 consultas del [estudio original](auditoria-metricas-ia-2026-11-12.md). `--all-destinations` incluye además las nuevas etiquetas geográficas del catálogo. La grilla da el mismo peso a cada consulta y sirve para medir cobertura, sin estimar demanda o satisfacción de personas.

| Indicador funcional | Antes | Después |
| --- | ---: | ---: |
| Fichas disponibles | 51 | 62 |
| Ubicaciones originales sin opción para principiantes | 21/38 | 9/38 |
| Alternativas que superan el nivel de principiante | 3.528/6.384 (55,3 %) | 1.512/6.384 (23,7 %) |
| Coincidencia con todas las preferencias, todos los niveles | 1.433/19.152 (7,5 %) | 1.772/19.152 (9,3 %) |
| Coincidencias de principiantes | 240/6.384 | 372/6.384 |
| Duración fuera de rango o sin alcance suficiente | 11.872/19.152 (62,0 %) | 12.040/19.152 (62,9 %) |
| Fichas con tiempo para el recorrido completo (incluye estimaciones identificadas) | 38/51 | 42/62 |
| Fichas con tiempo explícito de solo ida | 4/51 | 5/62 |
| Resultados fuera del destino | 0 | 0 |

La cobertura por nivel mejoró aun cuando se verificaron pocos tiempos nuevos. La falta de coincidencia temporal aumentó: algunas fichas fáciles pasan a tener prioridad aun cuando su tiempo total sigue pendiente. No se promovieron a coincidencia los tiempos dudosos. Pasaron las 94 pruebas del backend y las 68 de app/servicios ejecutadas para este cambio, además de la compilación del backend y el chequeo TypeScript.

Quedaron sin opción de nivel principiante en la grilla original: Capilla del Monte, Cerro Piltriquitrón, Aconcagua, Ischigualasto, Reserva Florofaunística de Merlo, Sierra de la Ventana, Tilcara, Valle de Tierra Mayor y Villa Pehuenia. Por ejemplo, el [turnero provincial de Aconcagua](https://actividadesanp.mendoza.gov.ar/anp/reservas/PARQUEACONCAGUA) clasifica el itinerario a Horcones como dificultad media; no se lo rebajó para cubrir el destino. El sendero Claro Oscuro pertenece al parque Tornquist y no se cargó como si estuviera en la localidad de Sierra de la Ventana. El tramo fácil al inicio de la [ruta a Laguna Submarino](https://findelmundo.tur.ar/es/senderos/3263) no se confundió con el itinerario completo, que tiene dificultad media.

// Source facts for planning. These records do not provide GPS navigation.
const batch = "beginner-catalog-2026-11-12";
const checkedAt = "2026-11-12";
const source = (title, url) => ({ title, url });
const apn = (title, path) => source(`APN — ${title}`, `https://www.argentina.gob.ar/${path}`);
const fuego = apn("Senderos del Parque Nacional Tierra del Fuego", "node/306176");
const leoncito = apn("El Leoncito: actividades", "parquesnacionales/centro/parque-nacional-el-leoncito/actividades");
const leoncitoGuides = apn("El Leoncito: material para guías", "sites/default/files/material_de_estudio_examen_de_guias_pn_el_leoncito-_2.0.pdf");
const esquel = source("Turismo Esquel — Guía de senderos", "https://www.esquel.tur.ar/blog/otono-pleno-en-esquel-guia-de-senderos-para-que-elijas-tu-propia-aventura/");
const perito = apn("Perito Moreno: actividades", "parquesnacionales/patagonia-austral/parque-nacional-perito-moreno/actividades");
const fuegoArea = "Parque Nacional Tierra del Fuego, Ushuaia";

const definitions = [
  { key: "fuego-la-baliza", name: "Senda de la Baliza - Tierra del Fuego", area: fuegoArea, province: "Tierra del Fuego",
    km: 1.2, minutes: 30, route: "out_and_back", basis: "official_round_trip", landscapes: ["naturaleza", "bosques"], park: "tierra-del-fuego",
    sources: [source("INFUETUR — Senda de la Baliza", "https://findelmundo.tur.ar/es/senderos/4752"), fuego],
    description: "Desde las pasarelas de Bahía Lapataia, atraviesa bosque costero y pastizal hasta la baliza junto al Canal Beagle.",
    access: "Cartel de inicio junto a las pasarelas de Bahía Lapataia.", precautions: "Sin señal telefónica según INFUETUR. Respetá el límite de la reserva estricta." },
  { key: "fuego-laguna-negra", name: "Laguna Negra - Tierra del Fuego", area: fuegoArea, province: "Tierra del Fuego",
    km: 1, minutes: 30, route: "out_and_back", basis: "official_round_trip", landscapes: ["naturaleza", "bosques", "lagos", "miradores"], park: "tierra-del-fuego",
    sources: [source("INFUETUR — Sendero Laguna Negra", "https://findelmundo.tur.ar/es/senderos/6544"), fuego],
    description: "Paseo corto entre lengas y ñires hasta el mirador de la laguna, junto a una turbera.",
    access: "Cabecera después del río Ovando, dentro del parque.", precautions: "Sin señal telefónica según INFUETUR. Permanecé en el sendero señalizado." },
  { key: "iguazu-sendero-verde", name: "Sendero Verde - Iguazú", area: "Parque Nacional Iguazu", province: "Misiones",
    km: 0.65, minutes: 15, route: "point_to_point", basis: "official_one_way", distanceScope: "one_way", landscapes: ["naturaleza", "bosques"], park: "iguazu",
    sources: [source("Iguazú Argentina — Sendero Verde", "https://iguazuargentina.com/area-cataratas/sendero-verde/"), source("Iguazú Argentina — Mapa del Área Cataratas", "https://iguazuargentina.com/wp-content/uploads/2026/05/Mapa_Web1-1.pdf")],
    description: "Conexión peatonal por la selva entre el Patio de Servicios y la Estación Cataratas del área de visita.",
    access: "Patio de Servicios, Área Cataratas.", precautions: "El tiempo publicado es solo de ida. Coordiná el regreso dentro del parque." },
  { key: "tornquist-claro-oscuro", name: "Sendero Claro Oscuro - Parque Tornquist", area: "Parque Provincial Ernesto Tornquist", province: "Buenos Aires",
    km: 0.6, minutes: 30, route: "loop", basis: "official_circuit", landscapes: ["naturaleza", "bosques", "miradores"],
    sources: [source("Ministerio de Ambiente PBA — Actividades del parque", "https://www.ambiente.gba.gob.ar/node/3063"), source("Comarca Turística — Sendero Claroscuro", "https://comarcaturistica.com.ar/sendero-claroscuro/")],
    description: "Circuito autoguiado de esfuerzo bajo, con un mirador del pastizal serrano y un tramo de bosque.",
    access: "Sector Base Cerro Bahía Blanca del parque provincial.", precautions: "El acceso está sujeto a cupo y condiciones del parque." },
  { key: "nahuel-huapi-cascada-duendes", name: "Cascada de los Duendes - Lago Gutiérrez", area: "Parque Nacional Nahuel Huapi, Bariloche", province: "Río Negro",
    km: 1.2, nativeKm: 0.6, minutes: 60, route: "out_and_back", basis: "official_round_trip", landscapes: ["naturaleza", "bosques", "cascadas"], park: "nahuel-huapi",
    sources: [source("Bariloche Trekking — Seccional Lago Gutiérrez a Cascada de los Duendes", "https://barilochetrekking.com/sendero-08/"), apn("Nahuel Huapi: actividades", "parquesnacionales/regionpatagonia/parque-nacional-nahuel-huapi/actividades")],
    description: "Desde la Seccional Lago Gutiérrez, la senda bordea el arroyo Pescadero hasta la cascada y vuelve por el mismo camino.",
    access: "Seccional de Guardaparques Lago Gutiérrez.", precautions: "La hora publicada no incluye caminar desde Villa Los Coihues. Prestá atención al cruce con la bicisenda." },
  { key: "leoncito-cascada-rincon", name: "Cascada El Rincón - El Leoncito", area: "Parque Nacional El Leoncito", province: "San Juan",
    km: 1, nativeKm: 0.5, minutes: null, route: "out_and_back", basis: "not_published", landscapes: ["naturaleza", "cascadas", "miradores"], park: "el-leoncito",
    sources: [leoncito, leoncitoGuides], description: "Paseo desde el estacionamiento a la terraza natural donde se observa la cascada.",
    access: "Estacionamiento de la cascada El Rincón.", precautions: "La distancia corresponde a volver por el mismo sendero. Confirmá con el parque el tiempo para esta variante." },
  { key: "perito-moreno-mirador-volcan", name: "Mirador Lago Volcán - Perito Moreno", area: "Parque Nacional Perito Moreno", province: "Santa Cruz",
    km: 1.2, nativeKm: 0.6, minutes: null, route: "out_and_back", basis: "not_published", landscapes: ["naturaleza", "lagos", "miradores"], park: "perito-moreno",
    sources: [perito, apn("Perito Moreno: material para guías", "sites/default/files/material_estudio_examen_guias_pn_perito_moreno_2025.pdf")],
    description: "Paseo al mirador del lago Volcán y de los ríos Lácteo y Volcán, con regreso por el mismo camino.",
    access: "Sector Mirador Lago Volcán. No incluye el sendero de la Pasarela Histórica.", precautions: "Consultá la duración y registrá la visita en el Centro Operativo Onelli." },
  { key: "lanin-sendero-el-bosque", name: "Sendero El Bosque - Puerto Canoa", area: "Parque Nacional Lanín, Huechulafquen", province: "Neuquén",
    km: 0.45, minutes: 30, route: "loop", basis: "planning_estimate", landscapes: ["naturaleza", "bosques"], park: "lanin",
    sources: [source("Parque Nacional Lanín — Accesibilidad", "https://www.pnlanin.com.ar/img/32_Accesibilidad%20Parque%20Nacional%20Lan%C3%83%C2%ADn%20%281%29.pdf"), source("Universidad Nacional del Comahue — Estudio de campo de Huechulafquen (2007)", "https://rdi.uncoma.edu.ar/bitstream/handle/uncomaid/17926/importancia_del_sistema_de_informaci%C3%B3n_a_visitantes_en_areas_protegidas_sanchez-pascal%20-%20rdi.pdf?isAllowed=y&sequence=1")],
    description: "Circuito interpretativo corto de escasa pendiente, con carteles sobre la flora del bosque en Puerto Canoa.",
    access: "Junto a la seccional Puerto Canoa, camino al muelle.", precautions: "Los 30 minutos del circuito completo son una referencia del relevamiento de campo de 2007, no un tiempo actualizado por el parque." },
  { key: "esquel-rincon-aves", name: "Rincón de las Aves - Laguna La Zeta", area: "Esquel", province: "Chubut",
    km: 3.06, nativeKm: 1.53, minutes: 42, nativeMinutes: 21, route: "out_and_back", basis: "round_trip_from_official_one_way", landscapes: ["naturaleza", "lagos", "miradores"],
    sources: [esquel, source("Turismo Esquel — Recorré Esquel en zapatillas", "https://www.esquel.tur.ar/disfruta/excursiones-aventura/recorre-esquel-en-zapatillas"),
      source("Subsecretaría de Turismo de Esquel — Traza de ida Rincón de las Aves", "https://es.wikiloc.com/rutas-senderismo/recorre-esquel-en-zapatillas-sendero-rincon-de-las-aves-59935218")],
    description: "Senda de terreno blando, sin pendiente, que bordea la laguna hasta el observatorio de aves.",
    access: "Estacionamiento La Glorieta, acceso 1 de la Reserva Natural Urbana Laguna La Zeta.", precautions: "La traza municipal registra 21 minutos solo de ida. Los 42 minutos de ida y vuelta son una estimación al duplicar esa referencia; el regreso no se midió." },
  { key: "salta-san-bernardo-ala-delta", name: "Cerro San Bernardo - Ala Delta", area: "Ciudad de Salta", province: "Salta",
    km: 5, minutes: null, route: "out_and_back", basis: "not_published", landscapes: ["naturaleza", "montaña"],
    sources: [source("Turismo Ciudad de Salta — Cerro San Bernardo y Ala Delta", "https://saltaciudad.travel/posts/trekking-cerro-san-bernardo-y-ala-delta")],
    description: "Caminata de ida y vuelta al Cerro Ala Delta pasando por San Bernardo, fácil para personas en buen estado físico según la ficha municipal.",
    access: "Punto de encuentro publicado: Monumento a Güemes.", precautions: "El desnivel indicado en la ficha es de 200 m. Consultá tiempo y modalidad con el prestador." },
  { key: "san-javier-funicular-cuarto-puente", name: "Sendero El Funicular - Cuarto puente", area: "Sierra de San Javier, Horco Molle", province: "Tucumán",
    km: 5.16, nativeKm: 2.58, minutes: 75, route: "out_and_back", basis: "official_reference", landscapes: ["naturaleza", "bosques"],
    sources: [source("Tucumán Turismo — Ecosendas: El Funicular", "https://www.tucumanturismo.gob.ar/articulos/articulo/97/ecosendas")],
    description: "Desde Horco Molle hasta el cuarto puente del antiguo funicular en la Sierra de San Javier.",
    access: "Centro Asistencial Primario de Salud (CAPS) de Horco Molle, Yerba Buena.", precautions: "La distancia total corresponde a volver por el mismo camino. El Ente publica 1 h 15 min sin aclarar si ese tiempo incluye el regreso." },
];

const formatMinutes = minutes => minutes === null ? null : minutes < 60 ? `${minutes} min`
  : minutes % 60 === 0 ? `${minutes / 60} h` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
const trails = definitions.map(d => ({
  name: d.name, location: `${d.area}, ${d.province}`, difficulty: "Baja", duration: formatMinutes(d.minutes), distance_km: d.km,
  description: d.description, image_url: null, center_lat: null, center_lng: null, map_zoom: null, route_coordinates: null,
  parkSlug: d.park ?? null,
  provenance: {
    catalog_batch: batch, catalog_key: d.key, checked_at: checkedAt, province: d.province, area: d.area,
    route_type: d.route, duration_basis: d.basis,
    distance_basis: d.nativeKm ? "round_trip_from_official_one_way" : d.distanceScope === "one_way" ? "official_one_way" : "official_itinerary",
    official_distance_km: d.nativeKm ?? d.km, duration_minutes_min: d.minutes, duration_minutes_max: d.minutes,
    duration_is_derived: d.basis === "round_trip_from_official_one_way",
    native: { distance_km: d.nativeKm ?? d.km, distance_scope: d.nativeKm || d.distanceScope === "one_way" ? "one_way" : "total_itinerary",
      duration_minutes_min: d.nativeMinutes ?? d.minutes, duration_minutes_max: d.nativeMinutes ?? d.minutes,
      duration_scope: { official_round_trip: "total_itinerary", official_circuit: "total_itinerary", official_one_way: "one_way", official_reference: "unspecified", not_published: "not_published", planning_estimate: "total_itinerary", round_trip_from_official_one_way: "one_way" }[d.basis] },
    sources: d.sources, aliases: [], access: d.access, precautions: `${d.precautions} Consultá la habilitación y las condiciones con el administrador.`,
    recommendation: { trail_types: d.landscapes, terrain: null, source_url: d.sources[0].url },
    review: { confirmed_fields: ["identity", "difficulty", "distance"],
      unconfirmed_fields: d.minutes === null ? ["duration"] : d.basis === "official_reference" ? ["duration_scope"]
        : ["planning_estimate", "round_trip_from_official_one_way"].includes(d.basis) ? ["current_official_round_trip_duration"] : [],
      finding: d.precautions, warning: ["official_reference", "planning_estimate", "round_trip_from_official_one_way"].includes(d.basis) ? d.precautions : null },
    photo: null, mapping: null, mapping_pending_reason: "Ficha informativa sin traza disponible en MiSendero.",
    missing_fields: ["gps_trace", "photo", "accumulated_ascent"],
    training: { record_type: "verified_catalog_features", relevance_label: null, synthetic: false },
  },
}));

function reviewCerroLeoncito(row) {
  const previous = row.provenance;
  if (previous?.catalog_key !== "leoncito-cerro" || row.duration !== "3 h" || previous.duration_basis !== "official_round_trip") return row;
  const finding = "APN publica 3 h en la ficha de actividades y 4 h en el manual para guías, ambos para los 8 km de ida y vuelta.";
  return { ...row, duration: "3 a 4 h", provenance: { ...previous,
    checked_at: checkedAt, duration_minutes_min: 180, duration_minutes_max: 240,
    sources: [...previous.sources, leoncitoGuides],
    review: { confirmed_fields: ["duration_scope"], unconfirmed_fields: ["duration_single_value"], finding,
      warning: `${finding} Planificá con margen para el regreso.` },
    duration_references: [{ minutes: 180, scope: "round_trip", source_url: leoncito.url }, { minutes: 240, scope: "round_trip", source_url: leoncitoGuides.url }],
  } };
}

module.exports = { batch, trails, reviewCerroLeoncito };

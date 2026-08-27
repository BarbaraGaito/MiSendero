const { query } = require("./db");

const commonsImage = (fileName) =>
  `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(fileName)}?width=1400`;

const seedTrailData = [
  {
    name: "Sendero a Confluencia",
    location: "Parque Provincial Aconcagua, Mendoza",
    difficulty: "Media",
    duration: "4 a 5 h",
    distance_km: 14,
    description:
      "Trekking clasico de aproximacion al Aconcagua desde Horcones hasta el campamento Confluencia, con vistas de alta montana.",
    image_url: commonsImage("Aconcagua confluencia.jpg"),
    center_lat: -32.8117,
    center_lng: -69.9496,
    map_zoom: 12,
    route_coordinates: [
      [-32.8245, -69.9403],
      [-32.8201, -69.9489],
      [-32.8158, -69.9587],
      [-32.8096, -69.9676],
      [-32.8005, -69.9736],
    ],
  },
  {
    name: "Base del Volcan Lanin",
    location: "Parque Nacional Lanin, Neuquen",
    difficulty: "Alta",
    duration: "6 a 8 h",
    distance_km: 12,
    description:
      "Sendero de alta montana hacia la base del volcan Lanin, en ambiente andino con bosques de araucarias y vistas al cono volcanico.",
    image_url: commonsImage("Argentina - Neuquén - Volcán Lanín.jpg"),
    center_lat: -39.6372,
    center_lng: -71.5015,
    map_zoom: 12,
    route_coordinates: [
      [-39.5878, -71.4637],
      [-39.6044, -71.4754],
      [-39.6197, -71.4888],
      [-39.6346, -71.5021],
      [-39.6492, -71.5146],
    ],
  },
  {
    name: "Garganta del Diablo de Tilcara",
    location: "Tilcara, Jujuy",
    difficulty: "Media",
    duration: "3 a 4 h",
    distance_km: 7.5,
    description:
      "Recorrido desde Tilcara hacia la quebrada y cascada de la Garganta del Diablo, con vistas de la Quebrada de Humahuaca.",
    image_url: commonsImage("Quebrada de Humahuaca 01.jpg"),
    center_lat: -23.5759,
    center_lng: -65.3768,
    map_zoom: 13,
    route_coordinates: [
      [-23.5779, -65.3933],
      [-23.5769, -65.3874],
      [-23.5756, -65.3811],
      [-23.5736, -65.3747],
      [-23.5714, -65.3684],
    ],
  },
  {
    name: "Garganta del Diablo - Quebrada de las Conchas",
    location: "Cafayate, Salta",
    difficulty: "Baja",
    duration: "1 a 2 h",
    distance_km: 3,
    description:
      "Caminata corta entre paredones rojizos y formaciones naturales de la Quebrada de las Conchas, en los Valles Calchaquies.",
    image_url: commonsImage("Quebrada de las Conchas- Salta-.jpg"),
    center_lat: -25.9201,
    center_lng: -65.7208,
    map_zoom: 13,
    route_coordinates: [
      [-25.9138, -65.7138],
      [-25.9162, -65.7164],
      [-25.9187, -65.7192],
      [-25.9213, -65.7224],
      [-25.924, -65.7252],
    ],
  },
  {
    name: "Alerce Milenario",
    location: "Parque Nacional Los Alerces, Chubut",
    difficulty: "Baja",
    duration: "2 a 3 h",
    distance_km: 4,
    description:
      "Sendero interpretativo entre bosque andino patagonico hacia sectores de alerces antiguos del Parque Nacional Los Alerces.",
    image_url: commonsImage("Alerce milenario.jpg"),
    center_lat: -42.8274,
    center_lng: -71.8667,
    map_zoom: 13,
    route_coordinates: [
      [-42.8224, -71.8602],
      [-42.8247, -71.8634],
      [-42.8276, -71.8669],
      [-42.8304, -71.8708],
      [-42.8321, -71.8752],
    ],
  },
  {
    name: "Sendero El Palmar",
    location: "Parque Nacional El Palmar, Entre Rios",
    difficulty: "Baja",
    duration: "2 h",
    distance_km: 5,
    description:
      "Circuito entre palmares de yatay, pastizales y miradores del rio Uruguay dentro del Parque Nacional El Palmar.",
    image_url: commonsImage("Parque nacional El Palmar Entre Ríos.JPG"),
    center_lat: -31.8668,
    center_lng: -58.2566,
    map_zoom: 13,
    route_coordinates: [
      [-31.8548, -58.2449],
      [-31.8606, -58.2504],
      [-31.8668, -58.2566],
      [-31.8722, -58.2631],
      [-31.8781, -58.2693],
    ],
  },
  {
    name: "Ascenso Cerro Tres Picos",
    location: "Sierra de la Ventana, Buenos Aires",
    difficulty: "Alta",
    duration: "8 a 10 h",
    distance_km: 20,
    description:
      "Ascenso al punto mas alto de la provincia de Buenos Aires, con pendientes sostenidas y amplias vistas serranas.",
    image_url: commonsImage("Cerro Tres Picos.jpg"),
    center_lat: -38.1556,
    center_lng: -61.9501,
    map_zoom: 12,
    route_coordinates: [
      [-38.0957, -61.9284],
      [-38.1155, -61.9362],
      [-38.1348, -61.9445],
      [-38.1512, -61.9521],
      [-38.1561, -61.95],
    ],
  },
  {
    name: "Circuito Valle de la Luna",
    location: "Parque Provincial Ischigualasto, San Juan",
    difficulty: "Baja",
    duration: "2 a 3 h",
    distance_km: 4,
    description:
      "Recorrido por geoformas y paisajes deserticos del Valle de la Luna, dentro del Parque Provincial Ischigualasto.",
    image_url: commonsImage("Ischigualasto, prov. de San Juan, Argentina.jpg"),
    center_lat: -30.1209,
    center_lng: -67.9118,
    map_zoom: 12,
    route_coordinates: [
      [-30.1095, -67.9028],
      [-30.1142, -67.9075],
      [-30.1196, -67.9124],
      [-30.1252, -67.9183],
      [-30.1304, -67.9246],
    ],
  },
  {
    name: "Campo de Piedra Pomez",
    location: "Antofagasta de la Sierra, Catamarca",
    difficulty: "Baja",
    duration: "1 a 2 h",
    distance_km: 2,
    description:
      "Caminata corta entre formaciones de piedra pomez, paisaje de puna y suelos volcanicos en Antofagasta de la Sierra.",
    image_url: commonsImage("Campo de Piedra Pomez.jpg"),
    center_lat: -26.6597,
    center_lng: -67.5142,
    map_zoom: 13,
    route_coordinates: [
      [-26.6548, -67.5074],
      [-26.6571, -67.5101],
      [-26.6595, -67.5139],
      [-26.6617, -67.5173],
      [-26.6642, -67.5205],
    ],
  },
  {
    name: "Laguna del Tesoro - Aconquija",
    location: "Parque Nacional Aconquija, Tucuman",
    difficulty: "Alta",
    duration: "8 a 10 h",
    distance_km: 24,
    description:
      "Sendero exigente desde el portal Cochuna hacia Laguna del Tesoro, atravesando yungas y ambiente de montana del Aconquija.",
    image_url: commonsImage("VistadeTafidelValle.jpg"),
    center_lat: -27.1938,
    center_lng: -65.9576,
    map_zoom: 12,
    route_coordinates: [
      [-27.2362, -65.9298],
      [-27.2246, -65.9396],
      [-27.2117, -65.9514],
      [-27.1983, -65.9633],
      [-27.1852, -65.9762],
    ],
  },
];

const seedReports = [
  {
    trailName: "Sendero a Confluencia",
    issue_summary: "Barro y rocas sueltas",
    severity: "Media",
    trail_state: "Precaucion",
    cause: "Lluvia",
    details: "Tramo humedo en sectores de bosque.",
    daysAgo: 1,
  },
  {
    trailName: "Base del Volcan Lanin",
    issue_summary: "Sendero transitable",
    severity: "Leve",
    trail_state: "Transitable",
    cause: "Mantenimiento",
    details: "Buena senalizacion en los cruces principales.",
    daysAgo: 2,
  },
  {
    trailName: "Garganta del Diablo de Tilcara",
    issue_summary: "Nieve o hielo",
    severity: "Alta",
    trail_state: "Paso dificil",
    cause: "Deshielo",
    details: "Precaucion en el ascenso final.",
    daysAgo: 3,
  },
  {
    trailName: "Ascenso Cerro Tres Picos",
    issue_summary: "Viento fuerte",
    severity: "Media",
    trail_state: "Precaucion",
    cause: "Viento",
    details: "Rafagas cerca del mirador.",
    daysAgo: 4,
  },
  {
    trailName: "Sendero El Palmar",
    issue_summary: "Barro",
    severity: "Media",
    trail_state: "Precaucion",
    cause: "Lluvia",
    details: "Piso resbaladizo en bajadas.",
    daysAgo: 5,
  },
  {
    trailName: "Circuito Valle de la Luna",
    issue_summary: "Transitable con mucha humedad",
    severity: "Leve",
    trail_state: "Transitable",
    cause: "Lluvia",
    details: "Pasarelas humedas.",
    daysAgo: 6,
  },
];

const seedTrails = async () => {
  for (const trail of seedTrailData) {
    await query(
      `
        INSERT INTO trails (
          name, location, difficulty, duration, distance_km, description,
          image_url, center_lat, center_lng, map_zoom, route_coordinates
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        ON CONFLICT (name) DO UPDATE SET
          location = EXCLUDED.location,
          difficulty = EXCLUDED.difficulty,
          duration = EXCLUDED.duration,
          distance_km = EXCLUDED.distance_km,
          description = EXCLUDED.description,
          image_url = EXCLUDED.image_url,
          center_lat = EXCLUDED.center_lat,
          center_lng = EXCLUDED.center_lng,
          map_zoom = EXCLUDED.map_zoom,
          route_coordinates = EXCLUDED.route_coordinates
      `,
      [
        trail.name,
        trail.location,
        trail.difficulty,
        trail.duration,
        trail.distance_km,
        trail.description,
        trail.image_url,
        trail.center_lat,
        trail.center_lng,
        trail.map_zoom,
        JSON.stringify(trail.route_coordinates),
      ]
    );
  }
};

const seedTrailReports = async () => {
  const { rows: existing } = await query("SELECT COUNT(*)::int AS count FROM trail_reports");

  if (existing[0].count > 0) return;

  for (const report of seedReports) {
    const { rows: trailRows } = await query("SELECT id FROM trails WHERE name = $1", [
      report.trailName,
    ]);
    const trail = trailRows[0];

    if (!trail) continue;

    await query(
      `
        INSERT INTO trail_reports (
          trail_id, issue_summary, severity, trail_state, cause,
          blocks_path, details, reporter_name, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now() - ($9 || ' days')::interval)
      `,
      [
        trail.id,
        report.issue_summary,
        report.severity,
        report.trail_state,
        report.cause,
        false,
        report.details,
        "Senderista verificado",
        report.daysAgo,
      ]
    );
  }
};

const seedDatabase = async () => {
  await seedTrails();
  await seedTrailReports();
};

module.exports = seedDatabase;

if (require.main === module) {
  seedDatabase()
    .then(() => {
      console.log("Datos de ejemplo cargados correctamente");
      process.exit(0);
    })
    .catch((error) => {
      console.error("Error al cargar los datos de ejemplo", error);
      process.exit(1);
    });
}

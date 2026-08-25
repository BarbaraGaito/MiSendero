const db = require("./db");

function initDb() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'user',
      terms_version TEXT,
      terms_accepted_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS trails (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      location TEXT NOT NULL,
      difficulty TEXT NOT NULL,
      duration TEXT,
      distance_km REAL,
      description TEXT,
      image_url TEXT,
      center_lat REAL,
      center_lng REAL,
      map_zoom INTEGER,
      route_coordinates TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS activities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      trail_id INTEGER,
      started_at TEXT NOT NULL,
      ended_at TEXT,
      distance_km REAL,
      duration_minutes INTEGER,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (trail_id) REFERENCES trails(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS trail_reports (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      trail_id INTEGER NOT NULL,
      issue_summary TEXT NOT NULL,
      severity TEXT NOT NULL,
      trail_state TEXT NOT NULL,
      cause TEXT,
      blocks_path INTEGER NOT NULL DEFAULT 0,
      details TEXT,
      reporter_name TEXT NOT NULL DEFAULT 'Senderista',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (trail_id) REFERENCES trails(id) ON DELETE CASCADE
    );
  `);

  const userColumns = db
    .prepare("PRAGMA table_info(users)")
    .all()
    .map((column) => column.name);

  if (!userColumns.includes("role")) {
    db.exec("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'");
  }

  if (!userColumns.includes("terms_version")) {
    db.exec("ALTER TABLE users ADD COLUMN terms_version TEXT");
  }

  if (!userColumns.includes("terms_accepted_at")) {
    db.exec("ALTER TABLE users ADD COLUMN terms_accepted_at TEXT");
  }

  const adminUser = db
    .prepare("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    .get();
  const firstUser = db
    .prepare("SELECT id FROM users ORDER BY id ASC LIMIT 1")
    .get();

  if (!adminUser && firstUser) {
    db.prepare("UPDATE users SET role = 'admin' WHERE id = ?").run(firstUser.id);
  }

  const trailColumns = db
    .prepare("PRAGMA table_info(trails)")
    .all()
    .map((column) => column.name);

  const addTrailColumn = (name, definition) => {
    if (!trailColumns.includes(name)) {
      db.exec(`ALTER TABLE trails ADD COLUMN ${name} ${definition}`);
    }
  };

  addTrailColumn("center_lat", "REAL");
  addTrailColumn("center_lng", "REAL");
  addTrailColumn("map_zoom", "INTEGER");
  addTrailColumn("route_coordinates", "TEXT");

  const commonsImage = (fileName) =>
    `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(fileName)}?width=1400`;

  const realMapData = [
    {
      name: "Refugio Frey desde Villa Catedral",
      center_lat: -41.1734,
      center_lng: -71.4752,
      map_zoom: 13,
      route_coordinates: [
        [-41.1697, -71.4387],
        [-41.1798, -71.4499],
        [-41.1817, -71.4648],
        [-41.1773, -71.4846],
        [-41.1731, -71.5006]
      ]
    },
    {
      name: "Cerro Llao Llao y Villa Tacul",
      center_lat: -41.0649,
      center_lng: -71.5378,
      map_zoom: 14,
      route_coordinates: [
        [-41.0616, -71.5319],
        [-41.0646, -71.5356],
        [-41.0674, -71.5395],
        [-41.0664, -71.5444],
        [-41.0623, -71.5432]
      ]
    },
    {
      name: "Laguna de los Tres",
      center_lat: -49.2846,
      center_lng: -72.9265,
      map_zoom: 12,
      route_coordinates: [
        [-49.3314, -72.8867],
        [-49.3129, -72.8985],
        [-49.2917, -72.9233],
        [-49.2758, -72.9544],
        [-49.2725, -72.9792]
      ]
    },
    {
      name: "Laguna Torre",
      center_lat: -49.3086,
      center_lng: -72.9581,
      map_zoom: 12,
      route_coordinates: [
        [-49.3314, -72.8867],
        [-49.3232, -72.9091],
        [-49.3148, -72.9405],
        [-49.312, -72.9772],
        [-49.2959, -73.0005]
      ]
    },
    {
      name: "Laguna Capri",
      center_lat: -49.3055,
      center_lng: -72.9115,
      map_zoom: 13,
      route_coordinates: [
        [-49.3314, -72.8867],
        [-49.3216, -72.8958],
        [-49.3136, -72.9076],
        [-49.3046, -72.9181]
      ]
    },
    {
      name: "Senda Costera",
      center_lat: -54.8364,
      center_lng: -68.4784,
      map_zoom: 13,
      route_coordinates: [
        [-54.8397, -68.5691],
        [-54.8412, -68.5353],
        [-54.8369, -68.4938],
        [-54.8282, -68.4357],
        [-54.8275, -68.3911]
      ]
    },
    {
      name: "Hito XXIV",
      center_lat: -54.8496,
      center_lng: -68.6218,
      map_zoom: 13,
      route_coordinates: [
        [-54.8383, -68.5798],
        [-54.8456, -68.6031],
        [-54.8522, -68.6322],
        [-54.8573, -68.6658]
      ]
    },
    {
      name: "Cerro Guanaco",
      center_lat: -54.8317,
      center_lng: -68.5942,
      map_zoom: 13,
      route_coordinates: [
        [-54.8383, -68.5798],
        [-54.8309, -68.5885],
        [-54.8238, -68.5979],
        [-54.8158, -68.6071]
      ]
    },
    {
      name: "Pampa Alta",
      center_lat: -54.8217,
      center_lng: -68.5186,
      map_zoom: 13,
      route_coordinates: [
        [-54.8397, -68.5691],
        [-54.8313, -68.545],
        [-54.8236, -68.5189],
        [-54.8152, -68.4932]
      ]
    },
    {
      name: "Sendero Macuco",
      center_lat: -25.6695,
      center_lng: -54.4367,
      map_zoom: 13,
      route_coordinates: [
        [-25.6851, -54.4445],
        [-25.6769, -54.4418],
        [-25.6688, -54.4389],
        [-25.6606, -54.436],
        [-25.6529, -54.4328]
      ]
    },
    {
      name: "Sendero Principal al Balcon Norte",
      aliases: ["Sendero Principal al Balcón Norte"],
      center_lat: -31.6597,
      center_lng: -64.7292,
      map_zoom: 13,
      route_coordinates: [
        [-31.6378, -64.7127],
        [-31.6478, -64.7202],
        [-31.6576, -64.7287],
        [-31.6688, -64.7359],
        [-31.6784, -64.7431]
      ]
    },
    {
      name: "Canon de Talampaya",
      aliases: ["Cañón de Talampaya"],
      center_lat: -29.7832,
      center_lng: -67.8451,
      map_zoom: 12,
      route_coordinates: [
        [-29.7896, -67.8348],
        [-29.7841, -67.8437],
        [-29.7782, -67.853],
        [-29.7718, -67.8628]
      ]
    },
    {
      name: "Paseo Inferior",
      center_lat: -25.6926,
      center_lng: -54.4388,
      map_zoom: 15,
      route_coordinates: [
        [-25.6908, -54.4412],
        [-25.6926, -54.4401],
        [-25.6939, -54.4384],
        [-25.6931, -54.4365]
      ]
    },
    {
      name: "Paseo Superior",
      center_lat: -25.6911,
      center_lng: -54.4372,
      map_zoom: 15,
      route_coordinates: [
        [-25.6897, -54.4392],
        [-25.6908, -54.4376],
        [-25.692, -54.4358],
        [-25.6928, -54.4345]
      ]
    }
  ];

  const normalize = (value) =>
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/ñ/g, "n")
      .replace(/Ñ/g, "N");

  const seedTrailData = [
    {
      name: "Sendero a Confluencia",
      location: "Parque Provincial Aconcagua, Mendoza",
      difficulty: "Media",
      duration: "4 a 5 h",
      distance_km: 14,
      description: "Trekking clasico de aproximacion al Aconcagua desde Horcones hasta el campamento Confluencia, con vistas de alta montana.",
      image_url: commonsImage("Aconcagua confluencia.jpg"),
      center_lat: -32.8117,
      center_lng: -69.9496,
      map_zoom: 12,
      route_coordinates: [
        [-32.8245, -69.9403],
        [-32.8201, -69.9489],
        [-32.8158, -69.9587],
        [-32.8096, -69.9676],
        [-32.8005, -69.9736]
      ]
    },
    {
      name: "Base del Volcan Lanin",
      location: "Parque Nacional Lanin, Neuquen",
      difficulty: "Alta",
      duration: "6 a 8 h",
      distance_km: 12,
      description: "Sendero de alta montana hacia la base del volcan Lanin, en ambiente andino con bosques de araucarias y vistas al cono volcanico.",
      image_url: commonsImage("Argentina - Neuquén - Volcán Lanín.jpg"),
      center_lat: -39.6372,
      center_lng: -71.5015,
      map_zoom: 12,
      route_coordinates: [
        [-39.5878, -71.4637],
        [-39.6044, -71.4754],
        [-39.6197, -71.4888],
        [-39.6346, -71.5021],
        [-39.6492, -71.5146]
      ]
    },
    {
      name: "Garganta del Diablo de Tilcara",
      location: "Tilcara, Jujuy",
      difficulty: "Media",
      duration: "3 a 4 h",
      distance_km: 7.5,
      description: "Recorrido desde Tilcara hacia la quebrada y cascada de la Garganta del Diablo, con vistas de la Quebrada de Humahuaca.",
      image_url: commonsImage("Quebrada de Humahuaca 01.jpg"),
      center_lat: -23.5759,
      center_lng: -65.3768,
      map_zoom: 13,
      route_coordinates: [
        [-23.5779, -65.3933],
        [-23.5769, -65.3874],
        [-23.5756, -65.3811],
        [-23.5736, -65.3747],
        [-23.5714, -65.3684]
      ]
    },
    {
      name: "Garganta del Diablo - Quebrada de las Conchas",
      location: "Cafayate, Salta",
      difficulty: "Baja",
      duration: "1 a 2 h",
      distance_km: 3,
      description: "Caminata corta entre paredones rojizos y formaciones naturales de la Quebrada de las Conchas, en los Valles Calchaquies.",
      image_url: commonsImage("Quebrada de las Conchas- Salta-.jpg"),
      center_lat: -25.9201,
      center_lng: -65.7208,
      map_zoom: 13,
      route_coordinates: [
        [-25.9138, -65.7138],
        [-25.9162, -65.7164],
        [-25.9187, -65.7192],
        [-25.9213, -65.7224],
        [-25.924, -65.7252]
      ]
    },
    {
      name: "Alerce Milenario",
      location: "Parque Nacional Los Alerces, Chubut",
      difficulty: "Baja",
      duration: "2 a 3 h",
      distance_km: 4,
      description: "Sendero interpretativo entre bosque andino patagonico hacia sectores de alerces antiguos del Parque Nacional Los Alerces.",
      image_url: commonsImage("Alerce milenario.jpg"),
      center_lat: -42.8274,
      center_lng: -71.8667,
      map_zoom: 13,
      route_coordinates: [
        [-42.8224, -71.8602],
        [-42.8247, -71.8634],
        [-42.8276, -71.8669],
        [-42.8304, -71.8708],
        [-42.8321, -71.8752]
      ]
    },
    {
      name: "Sendero El Palmar",
      location: "Parque Nacional El Palmar, Entre Rios",
      difficulty: "Baja",
      duration: "2 h",
      distance_km: 5,
      description: "Circuito entre palmares de yatay, pastizales y miradores del rio Uruguay dentro del Parque Nacional El Palmar.",
      image_url: commonsImage("Parque nacional El Palmar Entre Ríos.JPG"),
      center_lat: -31.8668,
      center_lng: -58.2566,
      map_zoom: 13,
      route_coordinates: [
        [-31.8548, -58.2449],
        [-31.8606, -58.2504],
        [-31.8668, -58.2566],
        [-31.8722, -58.2631],
        [-31.8781, -58.2693]
      ]
    },
    {
      name: "Ascenso Cerro Tres Picos",
      location: "Sierra de la Ventana, Buenos Aires",
      difficulty: "Alta",
      duration: "8 a 10 h",
      distance_km: 20,
      description: "Ascenso al punto mas alto de la provincia de Buenos Aires, con pendientes sostenidas y amplias vistas serranas.",
      image_url: commonsImage("Cerro Tres Picos.jpg"),
      center_lat: -38.1556,
      center_lng: -61.9501,
      map_zoom: 12,
      route_coordinates: [
        [-38.0957, -61.9284],
        [-38.1155, -61.9362],
        [-38.1348, -61.9445],
        [-38.1512, -61.9521],
        [-38.1561, -61.95]
      ]
    },
    {
      name: "Circuito Valle de la Luna",
      location: "Parque Provincial Ischigualasto, San Juan",
      difficulty: "Baja",
      duration: "2 a 3 h",
      distance_km: 4,
      description: "Recorrido por geoformas y paisajes deserticos del Valle de la Luna, dentro del Parque Provincial Ischigualasto.",
      image_url: commonsImage("Ischigualasto, prov. de San Juan, Argentina.jpg"),
      center_lat: -30.1209,
      center_lng: -67.9118,
      map_zoom: 12,
      route_coordinates: [
        [-30.1095, -67.9028],
        [-30.1142, -67.9075],
        [-30.1196, -67.9124],
        [-30.1252, -67.9183],
        [-30.1304, -67.9246]
      ]
    },
    {
      name: "Campo de Piedra Pomez",
      location: "Antofagasta de la Sierra, Catamarca",
      difficulty: "Baja",
      duration: "1 a 2 h",
      distance_km: 2,
      description: "Caminata corta entre formaciones de piedra pomez, paisaje de puna y suelos volcanicos en Antofagasta de la Sierra.",
      image_url: commonsImage("Campo de Piedra Pomez.jpg"),
      center_lat: -26.6597,
      center_lng: -67.5142,
      map_zoom: 13,
      route_coordinates: [
        [-26.6548, -67.5074],
        [-26.6571, -67.5101],
        [-26.6595, -67.5139],
        [-26.6617, -67.5173],
        [-26.6642, -67.5205]
      ]
    },
    {
      name: "Laguna del Tesoro - Aconquija",
      location: "Parque Nacional Aconquija, Tucuman",
      difficulty: "Alta",
      duration: "8 a 10 h",
      distance_km: 24,
      description: "Sendero exigente desde el portal Cochuna hacia Laguna del Tesoro, atravesando yungas y ambiente de montana del Aconquija.",
      image_url: commonsImage("VistadeTafidelValle.jpg"),
      center_lat: -27.1938,
      center_lng: -65.9576,
      map_zoom: 12,
      route_coordinates: [
        [-27.2362, -65.9298],
        [-27.2246, -65.9396],
        [-27.2117, -65.9514],
        [-27.1983, -65.9633],
        [-27.1852, -65.9762]
      ]
    }
  ];

  const findTrailByName = db.prepare("SELECT id FROM trails WHERE name = ?");
  const insertTrail = db.prepare(`
    INSERT INTO trails (
      name,
      location,
      difficulty,
      duration,
      distance_km,
      description,
      image_url,
      center_lat,
      center_lng,
      map_zoom,
      route_coordinates
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  const updateSeedTrail = db.prepare(`
    UPDATE trails
    SET location = ?,
        difficulty = ?,
        duration = ?,
        distance_km = ?,
        description = ?,
        image_url = ?,
        center_lat = ?,
        center_lng = ?,
        map_zoom = ?,
        route_coordinates = ?
    WHERE id = ?
  `);

  for (const trail of seedTrailData) {
    const existingTrail = findTrailByName.get(trail.name);
    const values = [
      trail.location,
      trail.difficulty,
      trail.duration,
      trail.distance_km,
      trail.description,
      trail.image_url,
      trail.center_lat,
      trail.center_lng,
      trail.map_zoom,
      JSON.stringify(trail.route_coordinates)
    ];

    if (existingTrail) {
      updateSeedTrail.run(...values, existingTrail.id);
    } else {
      insertTrail.run(trail.name, ...values);
    }
  }

  const updateTrailMap = db.prepare(`
    UPDATE trails
    SET center_lat = ?,
        center_lng = ?,
        map_zoom = ?,
        route_coordinates = ?
    WHERE name = ?
  `);

  for (const trailMap of realMapData) {
    const names = [
      trailMap.name,
      normalize(trailMap.name),
      ...(trailMap.aliases || []),
      ...(trailMap.aliases || []).map(normalize)
    ];

    for (const name of [...new Set(names)]) {
      updateTrailMap.run(
        trailMap.center_lat,
        trailMap.center_lng,
        trailMap.map_zoom,
        JSON.stringify(trailMap.route_coordinates),
        name
      );
    }
  }

  const realPhotoData = [
    {
      name: "Refugio Frey desde Villa Catedral",
      image_url: commonsImage("Argentina - Bariloche trekking 055 - Refugio Frey (6797813783).jpg")
    },
    {
      name: "Cerro Llao Llao y Villa Tacul",
      image_url: commonsImage("Llao Llao Peninsula.jpg")
    },
    {
      name: "Laguna de los Tres",
      image_url: commonsImage("Laguna de los Tres.jpg")
    },
    {
      name: "Laguna Torre",
      image_url: commonsImage("Laguna Torre - panoramio.jpg")
    },
    {
      name: "Laguna Capri",
      image_url: commonsImage("Laguna Capri - panoramio.jpg")
    },
    {
      name: "Senda Costera",
      image_url: commonsImage("TDFNP-SendaCostera.jpg")
    },
    {
      name: "Hito XXIV",
      image_url: commonsImage("Lago Roca, Parque Nacional Tierra del Fuego 20181110 150751.jpg")
    },
    {
      name: "Cerro Guanaco",
      image_url: commonsImage("A day trip from Ushuaia into Parque Nacional Tierra del Fuego - (25187872535).jpg")
    },
    {
      name: "Pampa Alta",
      image_url: commonsImage("PN Tierra del Fuego (View Costera).jpg")
    },
    {
      name: "Sendero Macuco",
      image_url: commonsImage("Cachoeira do Macuco.jpg")
    },
    {
      name: "Sendero Principal al Balcon Norte",
      aliases: ["Sendero Principal al BalcÃ³n Norte", "Sendero Principal al Balcón Norte"],
      image_url: commonsImage("Balcon Sur-Condoritos 069.jpg")
    },
    {
      name: "Canon de Talampaya",
      aliases: ["CaÃ±Ã³n de Talampaya", "Cañón de Talampaya"],
      image_url: commonsImage("Talampaya road.jpg")
    },
    {
      name: "Paseo Inferior",
      image_url: commonsImage("Circuito Inferior - Iguazu (4811646447).jpg")
    },
    {
      name: "Paseo Superior",
      image_url: commonsImage("J37 939 paseo superior, Trennung Hin- und Rückweg.jpg")
    }
  ];

  const updateTrailPhoto = db.prepare(`
    UPDATE trails
    SET image_url = ?
    WHERE name = ?
  `);

  for (const trailPhoto of realPhotoData) {
    const names = [
      trailPhoto.name,
      normalize(trailPhoto.name),
      ...(trailPhoto.aliases || []),
      ...(trailPhoto.aliases || []).map(normalize)
    ];

    for (const name of [...new Set(names)]) {
      updateTrailPhoto.run(trailPhoto.image_url, name);
    }
  }

  const existingReports = db
    .prepare("SELECT COUNT(*) AS count FROM trail_reports")
    .get().count;

  if (existingReports === 0) {
    const seedReports = [
      {
        trailName: "Refugio Frey desde Villa Catedral",
        issue_summary: "Barro y rocas sueltas",
        severity: "Media",
        trail_state: "Precaucion",
        cause: "Lluvia",
        details: "Tramo humedo en sectores de bosque."
      },
      {
        trailName: "Cerro Llao Llao y Villa Tacul",
        issue_summary: "Sendero transitable",
        severity: "Leve",
        trail_state: "Transitable",
        cause: "Mantenimiento",
        details: "Buena senalizacion en los cruces principales."
      },
      {
        trailName: "Laguna de los Tres",
        issue_summary: "Nieve o hielo",
        severity: "Alta",
        trail_state: "Paso dificil",
        cause: "Deshielo",
        details: "Precaucion en el ascenso final."
      },
      {
        trailName: "Laguna Torre",
        issue_summary: "Viento fuerte",
        severity: "Media",
        trail_state: "Precaucion",
        cause: "Viento",
        details: "Rafagas cerca del mirador."
      },
      {
        trailName: "Sendero Macuco",
        issue_summary: "Barro",
        severity: "Media",
        trail_state: "Precaucion",
        cause: "Lluvia",
        details: "Piso resbaladizo en bajadas."
      },
      {
        trailName: "Paseo Superior",
        issue_summary: "Transitable con mucha humedad",
        severity: "Leve",
        trail_state: "Transitable",
        cause: "Lluvia",
        details: "Pasarelas humedas."
      }
    ];
    const findTrail = db.prepare("SELECT id FROM trails WHERE name = ?");
    const insertReport = db.prepare(`
      INSERT INTO trail_reports (
        trail_id,
        issue_summary,
        severity,
        trail_state,
        cause,
        blocks_path,
        details,
        reporter_name,
        created_at
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', ?))
    `);

    seedReports.forEach((report, index) => {
      const trail = findTrail.get(report.trailName);

      if (!trail) return;

      insertReport.run(
        trail.id,
        report.issue_summary,
        report.severity,
        report.trail_state,
        report.cause,
        0,
        report.details,
        "Senderista verificado",
        `-${index + 1} days`
      );
    });
  }
}

module.exports = initDb;

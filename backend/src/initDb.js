const db = require("./db");

function initDb() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'user',
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
  `);

  const userColumns = db
    .prepare("PRAGMA table_info(users)")
    .all()
    .map((column) => column.name);

  if (!userColumns.includes("role")) {
    db.exec("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'");
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
}

module.exports = initDb;

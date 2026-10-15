const definitions = require("./additionalTrailDefinitions");
const routes = require("./additionalTrailRoutes.json");
const photos = require("./additionalTrailPhotos.json");

module.exports = definitions.map((definition) => {
  const route = routes[definition.key];
  const photo = photos[definition.key];
  if (!route?.points?.length || !photo?.url) throw new Error(`Incomplete catalog entry: ${definition.key}`);
  const latitudes = route.points.map(([latitude]) => latitude);
  const longitudes = route.points.map(([, longitude]) => longitude);
  const sources = [{ title: "Ficha del recorrido", url: definition.source_url }];
  if (definition.extra_source_url) sources.push({ title: "Informacion complementaria", url: definition.extra_source_url });
  return {
    name: definition.name, location: definition.location, difficulty: definition.difficulty,
    duration: definition.duration, distance_km: route.distance_km,
    description: definition.description, image_url: photo.url,
    center_lat: (Math.min(...latitudes) + Math.max(...latitudes)) / 2,
    center_lng: (Math.min(...longitudes) + Math.max(...longitudes)) / 2,
    map_zoom: route.distance_km > 15 ? 13 : route.distance_km > 5 ? 14 : route.distance_km > 2 ? 15 : 16,
    route_coordinates: route.points,
    provenance: {
      checked_at: "2026-10-11", route_type: definition.route_type,
      access: definition.access, precautions: definition.precautions,
      duration_basis: definition.duration_basis,
      official_distance_km: definition.official_distance_km ?? null,
      distance_basis: "mapped_geometry", sources,
      mapping: { source: route.source, source_url: route.source_url, license: route.license,
        retrieved_at: route.retrieved_at, ways: route.ways },
      photo: { ...photo, context: definition.photo_context ?? null },
    },
  };
});

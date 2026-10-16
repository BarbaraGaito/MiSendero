import { Trail, SessionRow } from "../types";
export const trail: Trail = { id: 7, name: "Sendero medido", location: "Bariloche", difficulty: "Baja", duration: "1 h", distance_km: 3,
  description: "Recorrido de prueba", image_url: "https://images.example.test/trail.jpg", center_lat: -41, center_lng: -71, map_zoom: 12,
  route_coordinates: "[[-41,-71],[-41.001,-71],[-41.002,-71.001]]", created_at: "2026-10-10T10:00:00Z", national_park: null };
export const completed: SessionRow = { id: 1, user_id: 31, trail_id: 7, started_at: Date.UTC(2026, 9, 10, 10), ended_at: Date.UTC(2026, 9, 10, 11), duration: 3600,
  distance: 3000, avg_fatigue: null, completion_status: "completed", route_progress_meters: 3000, route_total_meters: 3000, ended_latitude: -41.002, ended_longitude: -71.001,
  rating: null, review_text: null, reviewed_at: null };

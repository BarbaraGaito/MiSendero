import { Trail } from "../types";

export type TrailAreaFilter = "all" | "national_parks" | "other_trails";
export type DistanceFilter = "Todas" | "Corta" | "Media" | "Larga" | "Sin dato";

const normalizeText = (value: string) => value.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

export const isNationalParkTrail = (trail: Pick<Trail, "location" | "national_park_slug" | "national_park">) => {
  // Explicit catalog locations also classify older downloads without a profile.
  return Boolean(trail.national_park_slug || trail.national_park) ||
    /^parque nacional\s+/.test(normalizeText((trail.location || "").trim()));
};

const matchesDistanceFilter = (distanceKm: Trail["distance_km"], filter: DistanceFilter) => {
  if (filter === "Todas") return true;
  if (filter === "Sin dato") return distanceKm === null;
  if (typeof distanceKm !== "number") return false;
  if (filter === "Corta") return distanceKm <= 5;
  if (filter === "Media") return distanceKm > 5 && distanceKm <= 10;
  return distanceKm > 10;
};

export const filterTrails = (
  trails: Trail[], favoriteTrailIds: number[], searchQuery: string,
  activeFilter: string, activeDistanceFilter: DistanceFilter, activeAreaFilter: TrailAreaFilter = "all"
) => {
  const normalizedQuery = normalizeText(searchQuery.trim());
  const normalizedDifficulty = normalizeText(activeFilter);
  const favoriteIdSet = new Set(favoriteTrailIds);
  return trails.filter((trail) => {
    const matchesQuery = !normalizedQuery || normalizeText(`${trail.name} ${trail.location}`).includes(normalizedQuery);
    const matchesDifficulty = activeFilter === "Todas" ||
      (activeFilter === "Favoritas" && favoriteIdSet.has(trail.id)) ||
      normalizeText(trail.difficulty).includes(normalizedDifficulty);
    const matchesArea = activeAreaFilter === "all" ||
      isNationalParkTrail(trail) === (activeAreaFilter === "national_parks");
    return matchesQuery && matchesDifficulty && matchesArea && matchesDistanceFilter(trail.distance_km, activeDistanceFilter);
  });
};

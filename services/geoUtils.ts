export type Coordinate = [number, number];

const EARTH_RADIUS_METERS = 6371000;

export const ROUTE_START_WARNING_METERS = 500;
export const ROUTE_DEVIATION_WARNING_METERS = 120;

export const parseRouteCoordinates = (
  value: string | null | undefined
): Coordinate[] => {
  if (!value) return [];

  try {
    const parsed = JSON.parse(value);

    if (!Array.isArray(parsed)) return [];

    return parsed.filter(
      (point): point is Coordinate =>
        Array.isArray(point) &&
        point.length >= 2 &&
        Number.isFinite(point[0]) &&
        Number.isFinite(point[1])
    );
  } catch {
    return [];
  }
};

export const getDistanceMeters = (from: Coordinate, to: Coordinate) => {
  const toRad = (value: number) => (value * Math.PI) / 180;
  const dLat = toRad(to[0] - from[0]);
  const dLng = toRad(to[1] - from[1]);
  const lat1 = toRad(from[0]);
  const lat2 = toRad(to[0]);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return EARTH_RADIUS_METERS * c;
};

const toLocalMeters = (point: Coordinate, origin: Coordinate) => {
  const latRad = (origin[0] * Math.PI) / 180;

  return {
    x:
      ((point[1] - origin[1]) * Math.PI * EARTH_RADIUS_METERS * Math.cos(latRad)) /
      180,
    y: ((point[0] - origin[0]) * Math.PI * EARTH_RADIUS_METERS) / 180,
  };
};

const getDistanceToSegmentMeters = (
  point: Coordinate,
  segmentStart: Coordinate,
  segmentEnd: Coordinate
) => {
  const p = toLocalMeters(point, segmentStart);
  const a = toLocalMeters(segmentStart, segmentStart);
  const b = toLocalMeters(segmentEnd, segmentStart);
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const segmentLengthSquared = dx * dx + dy * dy;

  if (segmentLengthSquared === 0) {
    return getDistanceMeters(point, segmentStart);
  }

  const t = Math.max(
    0,
    Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / segmentLengthSquared)
  );
  const closest = {
    x: a.x + t * dx,
    y: a.y + t * dy,
  };
  const distanceX = p.x - closest.x;
  const distanceY = p.y - closest.y;

  return Math.sqrt(distanceX * distanceX + distanceY * distanceY);
};

const getClosestPointOnSegment = (
  point: Coordinate,
  segmentStart: Coordinate,
  segmentEnd: Coordinate
) => {
  const p = toLocalMeters(point, segmentStart);
  const a = toLocalMeters(segmentStart, segmentStart);
  const b = toLocalMeters(segmentEnd, segmentStart);
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const segmentLengthSquared = dx * dx + dy * dy;

  if (segmentLengthSquared === 0) {
    return {
      coordinate: segmentStart,
      distanceMeters: getDistanceMeters(point, segmentStart),
      progressRatio: 0,
    };
  }

  const progressRatio = Math.max(
    0,
    Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / segmentLengthSquared)
  );
  const closestLocal = {
    x: a.x + progressRatio * dx,
    y: a.y + progressRatio * dy,
  };
  const metersPerLatitudeDegree = (Math.PI * EARTH_RADIUS_METERS) / 180;
  const metersPerLongitudeDegree =
    metersPerLatitudeDegree * Math.cos((segmentStart[0] * Math.PI) / 180);
  const coordinate: Coordinate = [
    segmentStart[0] + closestLocal.y / metersPerLatitudeDegree,
    segmentStart[1] + closestLocal.x / metersPerLongitudeDegree,
  ];

  return {
    coordinate,
    distanceMeters: getDistanceMeters(point, coordinate),
    progressRatio,
  };
};

export const getClosestPointOnRoute = (
  point: Coordinate,
  route: Coordinate[]
) => {
  if (route.length === 0) return null;
  if (route.length === 1) {
    return {
      coordinate: route[0],
      distanceMeters: getDistanceMeters(point, route[0]),
      progressMeters: 0,
    };
  }

  let closest:
    | {
        coordinate: Coordinate;
        distanceMeters: number;
        progressMeters: number;
      }
    | null = null;
  let traveledBeforeSegment = 0;

  route.slice(0, -1).forEach((segmentStart, index) => {
    const segmentEnd = route[index + 1];
    const segmentLength = getDistanceMeters(segmentStart, segmentEnd);
    const candidate = getClosestPointOnSegment(point, segmentStart, segmentEnd);
    const progressMeters = traveledBeforeSegment + segmentLength * candidate.progressRatio;

    if (!closest || candidate.distanceMeters < closest.distanceMeters) {
      closest = {
        coordinate: candidate.coordinate,
        distanceMeters: candidate.distanceMeters,
        progressMeters,
      };
    }

    traveledBeforeSegment += segmentLength;
  });

  return closest;
};

export const getDistanceToRouteMeters = (
  point: Coordinate,
  route: Coordinate[]
) => {
  if (route.length === 0) return null;
  if (route.length === 1) return getDistanceMeters(point, route[0]);

  return route.slice(0, -1).reduce((closestDistance, segmentStart, index) => {
    const distance = getDistanceToSegmentMeters(
      point,
      segmentStart,
      route[index + 1]
    );

    return Math.min(closestDistance, distance);
  }, Number.POSITIVE_INFINITY);
};

export const getRouteLengthMeters = (route: Coordinate[]) => {
  if (route.length < 2) return 0;

  return route.slice(0, -1).reduce(
    (total, point, index) => total + getDistanceMeters(point, route[index + 1]),
    0
  );
};

export const getRouteProgressMeters = (
  point: Coordinate,
  route: Coordinate[]
) => {
  if (route.length === 0) return null;
  if (route.length === 1) return 0;

  let closestDistance = Number.POSITIVE_INFINITY;
  let traveledBeforeSegment = 0;
  let closestProgress = 0;

  route.slice(0, -1).forEach((segmentStart, index) => {
    const segmentEnd = route[index + 1];
    const p = toLocalMeters(point, segmentStart);
    const a = toLocalMeters(segmentStart, segmentStart);
    const b = toLocalMeters(segmentEnd, segmentStart);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const segmentLengthSquared = dx * dx + dy * dy;
    const segmentLength = getDistanceMeters(segmentStart, segmentEnd);

    if (segmentLengthSquared === 0) return;

    const t = Math.max(
      0,
      Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / segmentLengthSquared)
    );
    const closest = {
      x: a.x + t * dx,
      y: a.y + t * dy,
    };
    const distanceX = p.x - closest.x;
    const distanceY = p.y - closest.y;
    const distanceToSegment = Math.sqrt(distanceX * distanceX + distanceY * distanceY);

    if (distanceToSegment < closestDistance) {
      closestDistance = distanceToSegment;
      closestProgress = traveledBeforeSegment + segmentLength * t;
    }

    traveledBeforeSegment += segmentLength;
  });

  return closestProgress;
};

export const getRouteStart = (
  route: Coordinate[],
  fallbackCenter: Coordinate
) => route[0] || fallbackCenter;

export const formatDistance = (meters: number) => {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} km`;
  }

  return `${Math.round(meters)} m`;
};

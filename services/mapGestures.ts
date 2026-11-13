export const MIN_TERRAIN_SCALE = 0.4;
export const MAX_TERRAIN_SCALE = 6;
export const TERRAIN_ZOOM_STEP = 1.28;

export const clampTerrainScale = (scale: number) =>
  Math.max(MIN_TERRAIN_SCALE, Math.min(MAX_TERRAIN_SCALE, scale));

export const getTerrainPerspectiveFov = (scale: number) => {
  const normalizedScale = clampTerrainScale(scale);

  if (normalizedScale <= 1) {
    return 43 + ((1 - normalizedScale) / (1 - MIN_TERRAIN_SCALE)) * 33;
  }

  const halfFov = 43 * Math.PI / 360;
  return Math.atan(Math.tan(halfFov) / normalizedScale) * 360 / Math.PI;
};

export const getPinchZoomDelta = (ratio: number) => {
  if (!Number.isFinite(ratio) || ratio <= 0) return 0;

  const rawZoomDelta = Math.log(ratio) / Math.log(1.32);

  if (ratio >= 1.08) {
    return Math.max(1, Math.round(rawZoomDelta));
  }

  if (ratio <= 0.92) {
    return Math.min(-1, Math.round(rawZoomDelta));
  }

  return 0;
};

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

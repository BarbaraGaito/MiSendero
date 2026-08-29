import {
  MAX_TERRAIN_SCALE,
  MIN_TERRAIN_SCALE,
  clampTerrainScale,
  getPinchZoomDelta,
  getTerrainPerspectiveFov,
} from "../mapGestures";

describe("map gestures", () => {
  test("ignores tiny pinch jitter", () => {
    expect(getPinchZoomDelta(1)).toBe(0);
    expect(getPinchZoomDelta(1.07)).toBe(0);
    expect(getPinchZoomDelta(0.93)).toBe(0);
  });

  test("commits at least one zoom level for a deliberate pinch", () => {
    expect(getPinchZoomDelta(1.08)).toBeGreaterThanOrEqual(1);
    expect(getPinchZoomDelta(0.92)).toBeLessThanOrEqual(-1);
  });

  test("supports larger multi-level pinch gestures", () => {
    expect(getPinchZoomDelta(1.8)).toBeGreaterThan(1);
    expect(getPinchZoomDelta(0.5)).toBeLessThan(-1);
  });

  test("allows the terrain camera to zoom farther out without exceeding its limits", () => {
    expect(clampTerrainScale(0.55)).toBe(0.55);
    expect(clampTerrainScale(0.1)).toBe(MIN_TERRAIN_SCALE);
    expect(clampTerrainScale(3)).toBe(MAX_TERRAIN_SCALE);
  });

  test("maps the complete terrain zoom range to a first-person field of view", () => {
    expect(getTerrainPerspectiveFov(MIN_TERRAIN_SCALE)).toBe(76);
    expect(getTerrainPerspectiveFov(1)).toBe(43);
    expect(getTerrainPerspectiveFov(MAX_TERRAIN_SCALE)).toBe(31);
  });
});

import { getPinchZoomDelta } from "../mapGestures";

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
});

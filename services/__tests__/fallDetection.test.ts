import { createFallDetector, FALL_SETTLE_MS, FALL_STILL_MS, FALL_WAIT_MS } from "../fallDetection";

const STEP = 50;
const feed = (detect: ReturnType<typeof createFallDetector>, from: number, to: number, g: [number, number, number]) => {
  let detected = false;
  for (let t = from; t <= to; t += STEP) detected = detect({ x: g[0], y: g[1], z: g[2], timestamp: t }) || detected;
  return detected;
};
const REST: [number, number, number] = [0, 0, 1];
const WALK: [number, number, number] = [0.6, 0.3, 1.3];
const IMPACT: [number, number, number] = [2, 1.5, 1.5];

test("an impact followed by stillness is reported once as a possible fall", () => {
  const detect = createFallDetector();
  expect(feed(detect, 0, 3000, WALK)).toBe(false);
  expect(detect({ x: IMPACT[0], y: IMPACT[1], z: IMPACT[2], timestamp: 3050 })).toBe(false);
  expect(feed(detect, 3100, 3050 + FALL_SETTLE_MS, WALK)).toBe(false);
  expect(feed(detect, 3100 + FALL_SETTLE_MS, 3100 + FALL_SETTLE_MS + FALL_STILL_MS - STEP, REST)).toBe(false);
  expect(feed(detect, 3100 + FALL_SETTLE_MS + FALL_STILL_MS, 3100 + FALL_SETTLE_MS + FALL_STILL_MS, REST)).toBe(true);
  expect(feed(detect, 3150 + FALL_SETTLE_MS + FALL_STILL_MS, 40000, REST)).toBe(false);
});

test("stillness without a previous impact (a break or the phone on a table) is not a fall", () => {
  expect(feed(createFallDetector(), 0, 60000, REST)).toBe(false);
});

test("walking on after an impact discards it, and movement interrupts the stillness count", () => {
  const detect = createFallDetector();
  detect({ x: IMPACT[0], y: IMPACT[1], z: IMPACT[2], timestamp: 0 });
  expect(feed(detect, STEP, FALL_WAIT_MS + 1000, WALK)).toBe(false);
  expect(feed(detect, FALL_WAIT_MS + 1050, FALL_WAIT_MS + 20000, REST)).toBe(false);

  const interrupted = createFallDetector();
  interrupted({ x: IMPACT[0], y: IMPACT[1], z: IMPACT[2], timestamp: 0 });
  expect(feed(interrupted, FALL_SETTLE_MS, FALL_SETTLE_MS + FALL_STILL_MS / 2, REST)).toBe(false);
  expect(interrupted({ x: WALK[0], y: WALK[1], z: WALK[2], timestamp: FALL_SETTLE_MS + FALL_STILL_MS / 2 + STEP })).toBe(false);
  expect(feed(interrupted, FALL_SETTLE_MS + FALL_STILL_MS / 2 + 2 * STEP, FALL_SETTLE_MS + FALL_STILL_MS, REST)).toBe(false);
});

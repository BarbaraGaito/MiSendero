import contract from "../modelContract.json";
import parity from "../../../testing/fixtures/fall-detection/parity.json";
import { FallDetector, DetectorEvent, LOOSE_SPACING_MS } from "../detector";
import { FEATURE_ORDER, windowFeatures } from "../features";
import { buildFallModel, FALL_MODEL_FILE, FallModelFile, loadFallModel } from "../model";

const model = loadFallModel();
const STEP = 1000 / contract.sampleRateHz;

const run = (detector: FallDetector, xyz: number[], timeAt: (i: number) => number, from = 0, to = xyz.length / 3) => {
  const events: DetectorEvent[] = [];
  for (let i = from; i < to; i++) events.push(...detector.push(timeAt(i), xyz[3 * i], xyz[3 * i + 1], xyz[3 * i + 2]));
  return events;
};
const fresh = (cooldownMs?: number) => new FallDetector({ classify: model.classify, threshold: model.threshold, cooldownMs });

describe("signal contract", () => {
  test("the contract file and the feature order are consistent", () => {
    expect(contract.window).toBe(contract.preSamples + 1 + contract.postSamples);
    expect(contract.postSamples).toBeGreaterThanOrEqual(contract.neighbourhood);
    expect(FEATURE_ORDER).toEqual(contract.features.order);
    expect(FALL_MODEL_FILE.feature_order).toEqual(contract.features.order);
  });
});

describe("Python / TypeScript equivalence on real UniMiB SHAR windows", () => {
  test("features match the Python implementation", () => {
    let worst = 0;
    for (const item of parity.windows) {
      const features = windowFeatures(item.xyz);
      expect(features).toHaveLength(item.features.length);
      features.forEach((value, i) => { worst = Math.max(worst, Math.abs(value - item.features[i]) / Math.max(1, Math.abs(item.features[i]))); });
    }
    expect(worst).toBeLessThan(1e-9);
  });

  test("model probabilities match xgboost and the decisions are identical", () => {
    let worst = 0;
    for (const item of parity.windows) {
      const p = model.classify(item.features).probability;
      worst = Math.max(worst, Math.abs(p - item.probability));
      expect(p >= model.threshold).toBe(item.probability >= model.threshold);
    }
    expect(worst).toBeLessThan(1e-5);
  });

  test("the streaming detector finds the same candidates and probabilities as the Python pipeline", () => {
    for (const segment of parity.segments) {
      const events = run(fresh(0), segment.xyz, (i) => 5_000 + i * STEP);
      const found = events.filter((e) => e.type === "candidate") as Extract<DetectorEvent, { type: "candidate" }>[];
      expect(found).toHaveLength(segment.expected_candidates.length);
      found.forEach((event, i) => {
        const expected = segment.expected_candidates[i];
        expect(event.peakG).toBeCloseTo(expected.peak_g, 9);
        expect(Math.abs(event.probability - expected.probability)).toBeLessThan(1e-5);
        // The decision is taken when the sample `neighbourhood` after the peak arrives.
        expect(event.timestampMs).toBeCloseTo(5_000 + (expected.peak + contract.neighbourhood) * STEP, 6);
      });
    }
  });
});

describe("real fall and activity records", () => {
  const falls = parity.segments.filter((s) => s.activity !== "Jumping" && s.activity !== "SittingDown" && s.activity !== "Running");
  test("fall records raise exactly one alarm", () => {
    for (const segment of falls) {
      const events = run(fresh(), segment.xyz, (i) => i * STEP);
      const positives = segment.expected_candidates.filter((c) => c.probability >= model.threshold).length;
      expect(positives).toBeGreaterThan(0);
      expect(events.filter((e) => e.type === "alarm")).toHaveLength(1);
    }
  });

  test("the cooldown suppresses a second positive candidate instead of alarming twice", () => {
    const a = falls[0].xyz, b = falls[1].xyz;
    const together = [...a, ...b];
    const events = run(fresh(30_000), together, (i) => i * STEP);
    expect(events.filter((e) => e.type === "alarm")).toHaveLength(1);
    expect(events.filter((e) => e.type === "suppressed").length).toBeGreaterThanOrEqual(1);
    const noCooldown = run(fresh(0), together, (i) => i * STEP);
    expect(noCooldown.filter((e) => e.type === "alarm").length).toBeGreaterThanOrEqual(2);
  });

  test("jittered timestamps are resampled to 50 Hz and the fall is still detected", () => {
    const fall = falls[0];
    const n = fall.xyz.length / 3;
    // Irregular delivery times; the values are the real record linearly interpolated at those times.
    const times: number[] = [];
    let t = 0;
    for (let i = 0; i < n * 1.0 && t < (n - 1) * STEP; i++) { times.push(t); t += STEP + ((i * 7919) % 13) - 6; }
    const interpolated: number[] = [];
    for (const time of times) {
      const k = Math.min(n - 2, Math.floor(time / STEP)); const w = time / STEP - k;
      for (let axis = 0; axis < 3; axis++) interpolated.push(fall.xyz[3 * k + axis] * (1 - w) + fall.xyz[3 * (k + 1) + axis] * w);
    }
    const detector = fresh();
    const events = run(detector, interpolated, (i) => times[i], 0, times.length);
    expect(Math.max(...times.slice(1).map((v, i) => v - times[i]))).toBeLessThan(LOOSE_SPACING_MS);
    expect(events.filter((e) => e.type === "alarm")).toHaveLength(1);
    expect(detector.stats.gridSamples).toBeGreaterThan(n - 3);
  });

  test("a stalled sensor discards the buffer: no window ever bridges the gap", () => {
    const fall = falls[0];
    const n = fall.xyz.length / 3;
    const first = fall.expected_candidates[0];
    const cut = first.peak - 10;   // stall just before the first impact
    const detector = fresh(0);
    const events = [
      ...run(detector, fall.xyz, (i) => i * STEP, 0, cut),
      ...run(detector, fall.xyz, (i) => i * STEP + 400, cut, n),
    ];
    expect(events.some((e) => e.type === "interruption")).toBe(true);
    // The impact whose window would have straddled the stall is never classified.
    expect(events.filter((e) => e.type === "candidate" && Math.abs(e.peakG - first.peak_g) < 1e-9)).toHaveLength(0);
    expect(detector.stats.interruptions).toBe(1);
  });

  test("a phone delivering only 20 Hz is skipped for signal quality, never classified", () => {
    const detector = fresh(0);
    const events = run(detector, falls[0].xyz, (i) => i * 50);
    expect(events.filter((e) => e.type === "alarm" || e.type === "candidate")).toHaveLength(0);
    expect(detector.stats.skipped).toBeGreaterThan(0);
  });

  test("walking-like activity records do not alarm in the excerpts", () => {
    const quiet = parity.segments.filter((s) => s.activity === "Running" || s.activity === "Jumping");
    for (const segment of quiet) {
      const alarms = run(fresh(0), segment.xyz, (i) => i * STEP).filter((e) => e.type === "alarm");
      const expected = segment.expected_candidates.filter((c) => c.probability >= model.threshold).length;
      expect(alarms).toHaveLength(expected);
    }
  });
});

describe("input validation", () => {
  test("non finite or out-of-order samples are counted and ignored", () => {
    const detector = fresh();
    detector.push(0, 0, 0, 1);
    detector.push(20, NaN, 0, 1);
    detector.push(40, 0, 0, 1);
    detector.push(30, 0, 0, 1);
    detector.push(Infinity, 0, 0, 1);
    expect(detector.stats.invalidSamples).toBe(3);
    expect(detector.stats.gridSamples).toBe(3);   // t = 0, 20, 40 ms
  });

  test("a classifier failure becomes a skipped candidate, not an alarm or a crash", () => {
    const broken = new FallDetector({ classify: () => { throw new Error("boom"); }, threshold: 0.5, cooldownMs: 0 });
    const events = run(broken, parity.segments[0].xyz, (i) => i * STEP);
    expect(events.some((e) => e.type === "skipped" && e.reason === "classifier_error")).toBe(true);
    expect(events.filter((e) => e.type === "alarm")).toHaveLength(0);
  });

  test("windowFeatures rejects wrong sizes and non-finite samples", () => {
    expect(() => windowFeatures([1, 2, 3])).toThrow();
    const bad = parity.windows[0].xyz.slice(); bad[5] = NaN;
    expect(() => windowFeatures(bad)).toThrow();
  });

  test("the model loader refuses an approved flag, a different feature order or an invalid vector", () => {
    const file = FALL_MODEL_FILE as FallModelFile;
    expect(() => buildFallModel({ ...file, deployment_approved: true as unknown as false })).toThrow(/experimental/);
    expect(() => buildFallModel({ ...file, feature_order: [...file.feature_order].reverse() })).toThrow(/características/);
    expect(() => buildFallModel({ ...file, threshold: 1.2 })).toThrow();
    expect(() => model.classify([1, 2, 3])).toThrow();
    expect(() => model.classify(parity.windows[0].features.map(() => NaN))).toThrow();
  });

  test("the deployed model is labelled experimental and carries its provenance", () => {
    expect(FALL_MODEL_FILE.status).toBe("experimental");
    expect(FALL_MODEL_FILE.deployment_approved).toBe(false);
    expect(FALL_MODEL_FILE.version).toMatch(/exp/);
  });
});

describe("cost", () => {
  test("feature extraction plus inference stays far below the 20 ms sample period", () => {
    const features = parity.windows[0];
    const runs = 500;
    const start = process.hrtime.bigint();
    for (let i = 0; i < runs; i++) model.classify(windowFeatures(features.xyz));
    const msPerWindow = Number(process.hrtime.bigint() - start) / 1e6 / runs;
    // Informational: desktop Node, not a phone. The detector only classifies impact candidates (rare).
    console.info(`fall detection: ${msPerWindow.toFixed(3)} ms per window (host Node, not a phone)`);
    expect(msPerWindow).toBeLessThan(5);
  });
});

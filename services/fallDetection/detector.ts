import contract from "./modelContract.json";
import { windowFeatures } from "./features";

// Streaming counterpart of training/python/fall_detection/candidates.py. Deterministic rules
// (resampling, impact gate, signal quality, cooldown) are kept apart from the model decision.
const RATE = contract.sampleRateHz;
const STEP_MS = 1000 / RATE;
const { gateG, neighbourhood, preSamples, postSamples, window } = contract;
const RING = 128;
/** Raw spacing above this means the sensor stalled: the buffer is discarded, never bridged. */
export const MAX_GAP_MS = 100;
/** Raw spacing above this (2.25 sample periods) marks interpolated samples as low quality; windows containing
 *  them are skipped. Engineering rule, not tuned on hardware: it must be re-checked on real devices. */
export const LOOSE_SPACING_MS = 45;

export interface Classification { probability: number }
export type Classifier = (features: number[]) => Classification;

export type DetectorEvent =
  | { type: "candidate"; timestampMs: number; peakG: number; probability: number; positive: boolean }
  | { type: "alarm"; timestampMs: number; peakG: number; probability: number }
  | { type: "suppressed"; timestampMs: number; probability: number; reason: "cooldown" }
  | { type: "skipped"; timestampMs: number; peakG: number; reason: "signal_quality" | "classifier_error" }
  | { type: "interruption"; timestampMs: number; gapMs: number };

export interface DetectorStats {
  rawSamples: number;
  gridSamples: number;
  invalidSamples: number;
  interruptions: number;
  candidates: number;
  alarms: number;
  suppressed: number;
  skipped: number;
}

export interface DetectorOptions {
  classify: Classifier;
  threshold: number;
  cooldownMs?: number;
}

export class FallDetector {
  private readonly classify: Classifier;
  private readonly threshold: number;
  private readonly cooldownMs: number;
  private readonly xyz = new Float64Array(RING * 3);
  private readonly mag = new Float64Array(RING);
  private readonly loose = new Uint8Array(RING);
  private count = 0;            // grid samples since the last reset
  private prev: { t: number; v: [number, number, number] } | null = null;
  private nextGridMs = 0;
  private lastAlarmMs = -Infinity;
  readonly stats: DetectorStats = { rawSamples: 0, gridSamples: 0, invalidSamples: 0, interruptions: 0,
    candidates: 0, alarms: 0, suppressed: 0, skipped: 0 };

  constructor({ classify, threshold, cooldownMs = contract.cooldownSeconds * 1000 }: DetectorOptions) {
    if (!(threshold > 0 && threshold < 1)) throw new Error("Umbral de decisión inválido.");
    this.classify = classify;
    this.threshold = threshold;
    this.cooldownMs = cooldownMs;
  }

  /** Forget the signal (e.g. after an interruption); alarms already raised keep their cooldown. */
  reset() { this.count = 0; this.prev = null; }

  /** `x`, `y`, `z` in g (gravity included), `timestampMs` monotonic. Returns the events produced. */
  push(timestampMs: number, x: number, y: number, z: number): DetectorEvent[] {
    const events: DetectorEvent[] = [];
    this.stats.rawSamples++;
    if (![timestampMs, x, y, z].every(Number.isFinite) || (this.prev && timestampMs <= this.prev.t)) {
      this.stats.invalidSamples++;
      return events;
    }
    const current = { t: timestampMs, v: [x, y, z] as [number, number, number] };
    if (!this.prev) {
      this.prev = current;
      this.nextGridMs = timestampMs;
      this.append(x, y, z, false, timestampMs, events);
      this.nextGridMs += STEP_MS;
      return events;
    }
    const gap = timestampMs - this.prev.t;
    if (gap > MAX_GAP_MS) {
      this.stats.interruptions++;
      events.push({ type: "interruption", timestampMs, gapMs: gap });
      this.count = 0;
      this.prev = current;
      this.nextGridMs = timestampMs;
      this.append(x, y, z, false, timestampMs, events);
      this.nextGridMs += STEP_MS;
      return events;
    }
    const loose = gap > LOOSE_SPACING_MS;
    while (this.nextGridMs <= timestampMs) {
      const w = (this.nextGridMs - this.prev.t) / gap;
      this.append(
        this.prev.v[0] + (x - this.prev.v[0]) * w,
        this.prev.v[1] + (y - this.prev.v[1]) * w,
        this.prev.v[2] + (z - this.prev.v[2]) * w,
        loose, this.nextGridMs, events);
      this.nextGridMs += STEP_MS;
    }
    this.prev = current;
    return events;
  }

  private append(x: number, y: number, z: number, loose: boolean, timestampMs: number, events: DetectorEvent[]) {
    const slot = this.count % RING;
    this.xyz[3 * slot] = x; this.xyz[3 * slot + 1] = y; this.xyz[3 * slot + 2] = z;
    this.mag[slot] = Math.sqrt(x * x + y * y + z * z);
    this.loose[slot] = loose ? 1 : 0;
    this.count++;
    this.stats.gridSamples++;
    this.inspect(timestampMs, events);
  }

  // The newest sample is p + neighbourhood: p is decided now, its window ends at p + postSamples.
  private inspect(timestampMs: number, events: DetectorEvent[]) {
    const newest = this.count - 1;
    const p = newest - neighbourhood;
    if (p < 0) return;
    const m = (index: number) => this.mag[index % RING];
    const peak = m(p);
    if (peak <= gateG) return;
    for (let i = Math.max(0, p - neighbourhood); i < p; i++) if (!(m(i) < peak)) return;
    for (let i = p + 1; i <= newest; i++) if (!(m(i) <= peak)) return;
    // A candidate without a full real window is not classified (same rule as the training data).
    if (p < preSamples || p + postSamples > newest) return;
    this.stats.candidates++;
    const start = p - preSamples;
    const flat = new Float64Array(window * 3);
    for (let i = 0; i < window; i++) {
      const slot = (start + i) % RING;
      if (this.loose[slot]) {
        this.stats.skipped++;
        events.push({ type: "skipped", timestampMs, peakG: peak, reason: "signal_quality" });
        return;
      }
      flat[3 * i] = this.xyz[3 * slot]; flat[3 * i + 1] = this.xyz[3 * slot + 1]; flat[3 * i + 2] = this.xyz[3 * slot + 2];
    }
    let probability: number;
    try {
      probability = this.classify(windowFeatures(flat)).probability;
      if (!Number.isFinite(probability)) throw new Error("Probabilidad no finita");
    } catch {
      this.stats.skipped++;
      events.push({ type: "skipped", timestampMs, peakG: peak, reason: "classifier_error" });
      return;
    }
    const positive = probability >= this.threshold;
    events.push({ type: "candidate", timestampMs, peakG: peak, probability, positive });
    if (!positive) return;
    if (timestampMs - this.lastAlarmMs < this.cooldownMs) {
      this.stats.suppressed++;
      events.push({ type: "suppressed", timestampMs, probability, reason: "cooldown" });
      return;
    }
    this.lastAlarmMs = timestampMs;
    this.stats.alarms++;
    events.push({ type: "alarm", timestampMs, peakG: peak, probability });
  }
}

import contract from "./modelContract.json";

// Mirror of training/python/fall_detection/features.py. Orientation-invariant: only the acceleration
// magnitude and the angle between mean gravity vectors are used. Inputs are in g, gravity included.
const { window: WINDOW, peakIndex: PEAK_INDEX, sampleRateHz: SAMPLE_RATE_HZ } = contract;
const F = contract.features;

export const FEATURE_ORDER: readonly string[] = F.order;

const mean = (values: ArrayLike<number>, from = 0, to = values.length) => {
  let sum = 0;
  for (let i = from; i < to; i++) sum += values[i];
  return sum / (to - from);
};
// Population standard deviation, two passes like numpy.
const std = (values: ArrayLike<number>, from = 0, to = values.length) => {
  const mu = mean(values, from, to);
  let sum = 0;
  for (let i = from; i < to; i++) sum += (values[i] - mu) ** 2;
  return Math.sqrt(sum / (to - from));
};
const min = (values: ArrayLike<number>, from = 0, to = values.length) => {
  let out = Infinity;
  for (let i = from; i < to; i++) if (values[i] < out) out = values[i];
  return out;
};
const max = (values: ArrayLike<number>, from = 0, to = values.length) => {
  let out = -Infinity;
  for (let i = from; i < to; i++) if (values[i] > out) out = values[i];
  return out;
};

const localMaxima = (m: ArrayLike<number>, start: number, stop: number, threshold: number) => {
  let count = 0;
  for (let i = Math.max(start, 1); i < Math.min(stop, m.length - 1); i++) {
    if (m[i] > threshold && m[i] > m[i - 1] && m[i] >= m[i + 1]) count++;
  }
  return count;
};

/** `xyz` is a flat [x0, y0, z0, x1, ...] array of `contract.window` samples at exactly 50 Hz, in g. */
export const windowFeatures = (xyz: ArrayLike<number>): number[] => {
  if (xyz.length !== WINDOW * 3) throw new Error(`La ventana debe tener ${WINDOW} muestras.`);
  const m = new Float64Array(WINDOW);
  for (let i = 0; i < WINDOW; i++) {
    const x = xyz[3 * i], y = xyz[3 * i + 1], z = xyz[3 * i + 2];
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) throw new Error("Muestra no finita.");
    m[i] = Math.sqrt(x * x + y * y + z * z);
  }
  const f: Record<string, number> = {
    m_mean: mean(m), m_std: std(m), m_min: min(m), m_max: max(m), m_range: max(m) - min(m),
  };
  for (const [name, [a, b]] of Object.entries(F.segments)) {
    f[`${name}_mean`] = mean(m, a, b); f[`${name}_std`] = std(m, a, b);
    f[`${name}_min`] = min(m, a, b); f[`${name}_max`] = max(m, a, b);
  }
  const dev = new Float64Array(WINDOW);
  for (let i = 0; i < WINDOW; i++) dev[i] = (m[i] - 1) ** 2;
  const preEnd = F.segments.impact[0];
  const [postA, postB] = F.segments.post;
  const energyPre = mean(dev, 0, preEnd);
  f.energy_all = mean(dev);
  f.energy_pre = energyPre;
  f.energy_post = mean(dev, postA, WINDOW);
  f.peak_over_pre_rms = m[PEAK_INDEX] / (Math.sqrt(energyPre) + 0.05);
  const [ffA, ffB] = F.freeFall;
  f.freefall_min = min(m, ffA, ffB);
  let freeSamples = 0;
  for (let i = ffA; i < ffB; i++) if (m[i] < F.freeFallThresholdG) freeSamples++;
  f.freefall_samples = freeSamples;
  const diff = new Float64Array(WINDOW - 1);
  for (let i = 0; i < WINDOW - 1; i++) diff[i] = Math.abs(m[i + 1] - m[i]) * SAMPLE_RATE_HZ;
  f.jerk_max = max(diff);
  f.jerk_mean = mean(diff);
  f.jerk_impact = max(diff, F.segments.impact[0] - 4, F.segments.impact[1] - 1);
  f.peaks_all = localMaxima(m, 0, WINDOW, F.peakCountThresholdG);
  f.peaks_pre = localMaxima(m, 0, preEnd, F.peakCountThresholdG);
  const meanVector = (a: number, b: number) => [0, 1, 2].map((axis) => {
    let sum = 0;
    for (let i = a; i < b; i++) sum += xyz[3 * i + axis];
    return sum / (b - a);
  });
  const before = meanVector(...(F.segments.pre_far as [number, number]));
  const after = meanVector(postA, postB);
  const nb = Math.sqrt(before[0] * before[0] + before[1] * before[1] + before[2] * before[2]);
  const na = Math.sqrt(after[0] * after[0] + after[1] * after[1] + after[2] * after[2]);
  const cosine = nb > 0 && na > 0 ? (before[0] * after[0] + before[1] * after[1] + before[2] * after[2]) / (nb * na) : 1;
  f.angle_deg = Math.acos(Math.min(1, Math.max(-1, cosine))) * (180 / Math.PI);
  f.gravity_pre = nb;
  f.gravity_post = na;
  let postDevSum = 0, still = 0;
  for (let i = postA; i < postB; i++) {
    const d = Math.abs(m[i] - 1);
    postDevSum += d;
    if (d < F.stillToleranceG) still++;
  }
  f.post_dev_mean = postDevSum / (postB - postA);
  f.post_still_fraction = still / (postB - postA);
  return FEATURE_ORDER.map((name) => {
    const value = f[name];
    if (value === undefined) throw new Error(`Falta la característica ${name}.`);
    return value;
  });
};

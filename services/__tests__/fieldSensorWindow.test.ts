import { completedHeartRateWindow, freshMorningPair, type NativeFieldSamples } from "../fieldSensorWindow";
const now = 600000;
const samples = (): NativeFieldSamples => ({ provider: "apple_healthkit", heartRate: [0,15000,30000,45000,60000].map(offset => ({ value: 100+offset/15000, recordedAt: now-60000+offset })), oxygen: [{ value: 97, recordedAt: now }] });
test("a completed measured minute ignores later readings and never interpolates missing samples", () => {
  const source = samples();
  source.heartRate.push({ value: 220, recordedAt: now+1 });
  expect(completedHeartRateWindow(source, now+15000)).toMatchObject({ meanBpm: 102, sampleCount: 5, startAt: now-60000, endAt: now });
  expect(completedHeartRateWindow(null, now)).toBeNull();
  expect(completedHeartRateWindow({ ...source, provider: "development_simulator" }, now)).toBeNull();
  expect(completedHeartRateWindow({ ...source, heartRate: source.heartRate.slice(0,2) }, now)).toBeNull();
  expect(completedHeartRateWindow({ ...source, heartRate: source.heartRate.slice(1,5).map(row => ({ ...row, recordedAt: row.recordedAt+16000 })) }, now)).toBeNull();
  expect(completedHeartRateWindow({ ...source, heartRate: [...source.heartRate,{ value: 200, recordedAt: now }] }, now)).toBeNull();
  expect(completedHeartRateWindow({ ...source, heartRate: source.heartRate.map(row => ({ ...row, value: NaN })) }, now)).toBeNull();
});
test("resting pulse and oxygen must be real, fresh and sufficiently simultaneous", () => {
  expect(freshMorningPair(samples(), now)).toMatchObject({ hr: 104, spo2: 97 });
  expect(freshMorningPair(null, now)).toBeNull();
  expect(freshMorningPair({ ...samples(), provider: "development_simulator" }, now)).toBeNull();
  expect(freshMorningPair({ ...samples(), oxygen: [{ value: 97, recordedAt: now-61000 }] }, now)).toBeNull();
  expect(freshMorningPair(samples(), now+360000)).toBeNull();
  expect(freshMorningPair({ ...samples(), oxygen: [{ value: 97, recordedAt: now+1 }] }, now)).toBeNull();
  expect(freshMorningPair(samples(), NaN)).toBeNull();
});

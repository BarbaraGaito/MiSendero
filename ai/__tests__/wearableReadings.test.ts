import { assessWearableReadings } from "../wearableReadings";

// Technical screening-rule cases only; never used as empirical observations or training labels.
test.each([
  [90, 98, "normal", "baja"],
  [144, 98, "normal", "baja"],
  [145, 98, "caution", "media"],
  [164, 98, "caution", "media"],
  [165, 98, "caution", "alta"],
  [179, 98, "caution", "alta"],
  [180, 98, "high", "alta"],
  [90, 94, "normal", "baja"],
  [90, 93.9, "caution", "baja"],
  [90, 90, "caution", "baja"],
  [90, 89.9, "high", "baja"],
] as const)("pulse %s and oxygen %s activate the declared screening level", (heartRateBpm, oxygenSaturation, level, cardiacLoad) => {
  expect(assessWearableReadings({ heartRateBpm, oxygenSaturation })).toMatchObject({ level, cardiacLoad, coverage: "pulse_and_oxygen" });
});

test.each([null, NaN, Infinity, -1, 0, 29, 241])("oxygen can be used independently of invalid pulse %s", heartRateBpm => {
  expect(assessWearableReadings({ heartRateBpm, oxygenSaturation: 88 })).toMatchObject({ level: "high", cardiacLoad: null, heartRateBpm: null, coverage: "oxygen_only" });
});

test.each([null, NaN, Infinity, -1, 0, 49, 101])("pulse can be used independently of invalid oxygen %s", oxygenSaturation => {
  expect(assessWearableReadings({ heartRateBpm: 150, oxygenSaturation })).toMatchObject({ level: "caution", cardiacLoad: "media", oxygenSaturation: null, coverage: "pulse_only" });
});

test("neither sensor means no invented assessment; no confidence or disease prediction is returned", () => {
  expect(assessWearableReadings({ heartRateBpm: null, oxygenSaturation: null })).toBeNull();
  const result = assessWearableReadings({ heartRateBpm: 90, oxygenSaturation: 98 });
  expect(result).not.toHaveProperty("confidence");
  expect(result).not.toHaveProperty("fatigue");
  expect(result).not.toHaveProperty("riskLabel");
});

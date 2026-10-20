import { getEstimatedReturnHours } from "../trailDuration";

test.each([
  ["4 a 5 h", 5],
  ["6 a 8 h", 8],
  ["1 h 30 min a 2 h", 2],
  ["30 a 45 min", 0.75],
  ["1 h 30 min", 1.5],
  ["8 a 10 h", 10],
  ["3 h", 3],
  ["1 a 2 h", 2],
  ["10 a 12 h", 12],
  ["1,5 h", 1.5],
  ["45 minutos", 0.75],
  ["2 horas 30 minutos", 2.5],
  ["1 h\t a\n 2 h", 2],
  ["30 min  —\t 1 h", 1],
])("prefills %s as %s hours, using the upper end of a range", (duration, hours) => {
  expect(getEstimatedReturnHours(duration)).toBe(hours);
});

test.each([null, undefined, "", "a confirmar", "0 h", "-2 h", "100 h", "3 dias", "1 h extra"])(
  "does not invent a default for missing or invalid estimates (%s)", (duration) => {
    expect(getEstimatedReturnHours(duration)).toBeNull();
  }
);

test("long whitespace followed by an invalid separator is rejected", () => {
  expect(getEstimatedReturnHours(`1 h${" ".repeat(100000)}x`)).toBeNull();
});

import "../../../testing/mobileSetup";
jest.mock("../../../services/environmental", () => ({ getTrailEnvironmental: jest.fn() }));
jest.mock("expo-network", () => ({ addNetworkStateListener: jest.fn() }));
import * as Network from "expo-network";
import { getTrailEnvironmental } from "../../../services/environmental";
import EnvironmentalConditions from "../EnvironmentalConditions";
import { act, mount, text } from "../../../testing/mobileHarness";
const { fixtureTrail, makeBatch, now } = require("../../../testing/fixtures/environmental.cjs");

beforeEach(() => {
  jest.useFakeTimers().setSystemTime(now);
  (Network.addNetworkStateListener as jest.Mock).mockReturnValue({ remove: jest.fn() });
  (getTrailEnvironmental as jest.Mock).mockResolvedValue({ batch: makeBatch(), mode: "offline", error: false });
});
afterEach(() => jest.useRealTimers());

test("an offline forecast displays provenance and turns historical at its deadline", async () => {
  const tree = await mount(EnvironmentalConditions, { trail: fixtureTrail, offlineOnly: true });
  expect(text(tree)).toContain("Predicción experimental");
  expect(text(tree)).toContain("Fixture station");
  expect(text(tree)).toContain("No es un límite garantizado del error");
  expect(text(tree)).toContain("sin conexión");
  await act(async () => { jest.advanceTimersByTime(3 * 3600000); });
  expect(text(tree)).toContain("Información vencida");
  expect(text(tree)).toContain("valor histórico");
  expect(text(tree)).not.toContain("Predicción vigente");
});

test("missing data remains distinct from a numerical estimate; reconnection updates the card", async () => {
  (getTrailEnvironmental as jest.Mock).mockResolvedValueOnce({ batch: null, mode: "offline", error: true });
  const tree = await mount(EnvironmentalConditions, { trail: fixtureTrail });
  expect(text(tree)).toContain("No guardaste información ambiental");
  expect(text(tree)).not.toContain("1.23");
  const listener = (Network.addNetworkStateListener as jest.Mock).mock.calls.at(-1)[0];
  await act(async () => { listener({ isConnected: true, isInternetReachable: true }); });
  expect(text(tree)).toContain("Predicción experimental");
  expect(text(tree)).toContain("Fixture station");
});

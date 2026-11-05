import "../../../testing/mobileSetup";
jest.mock("expo-sensors", () => ({ Accelerometer: { isAvailableAsync: jest.fn(), getPermissionsAsync: jest.fn(), requestPermissionsAsync: jest.fn(), setUpdateInterval: jest.fn(), addListener: jest.fn() } }));
jest.mock("../../../services/fallDetection/fallEvents", () => ({ getFallSettings: jest.fn(), saveFallSettings: jest.fn().mockResolvedValue(undefined) }));
import { Alert, Switch } from "react-native";
import { Accelerometer } from "expo-sensors";
import { getFallSettings, saveFallSettings } from "../../../services/fallDetection/fallEvents";
import { act, flush, mount, text } from "../../../testing/mobileHarness";
import { FALL_FEATURE_NAME, FallDetectionCard, FallDetectionStatusLine, monitorStatusText } from "../FallDetectionCard";

const toggle = async (tree: any, value: boolean) => act(async () => { tree.root.findByType(Switch).props.onValueChange(value); await flush(); });
const confirmAlert = async (label: string) => {
  const buttons = (Alert.alert as jest.Mock).mock.calls.at(-1)[2] as Array<{ text: string; onPress?: () => void }>;
  await act(async () => { buttons.find((b) => b.text === label)?.onPress?.(); await flush(); });
};
beforeEach(() => {
  (getFallSettings as jest.Mock).mockResolvedValue({ enabled: false, limitationsAcknowledgedAt: null });
  (Accelerometer.isAvailableAsync as jest.Mock).mockResolvedValue(true);
  (Accelerometer.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "granted", canAskAgain: true });
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
});

test("shows the name, offline operation, phone position, platform limits and the experimental status", async () => {
  const tree = await mount(FallDetectionCard);
  const content = text(tree);
  expect(content).toContain(FALL_FEATURE_NAME);
  expect(FALL_FEATURE_NAME).toBe("Detección de caídas — IA experimental");
  expect(content).toContain("Desactivada");
  expect(content).toContain("Funciona sin Internet");
  expect(content).toContain("bolsillo del pantalón");
  expect(content).toMatch(/Android|iPhone/);
  expect(content).toContain("caídas simuladas por voluntarios");
});

test("turning it on requires reading the limits and an explicit confirmation, then checks the sensor", async () => {
  const tree = await mount(FallDetectionCard);
  await toggle(tree, true);
  expect(Alert.alert).toHaveBeenCalledTimes(1);
  expect((Alert.alert as jest.Mock).mock.calls[0][1]).toContain("nunca llama ni envía SMS por su cuenta");
  await confirmAlert("Cancelar");
  expect(saveFallSettings).not.toHaveBeenCalled();
  await toggle(tree, true);
  await confirmAlert("Entiendo, activar");
  expect(saveFallSettings).toHaveBeenCalledWith({ enabled: true, limitationsAcknowledgedAt: expect.any(Number) });
  expect(tree.root.findByType(Switch).props.value).toBe(true);
});

test("a missing sensor or a denied permission leaves it off and explains why", async () => {
  const tree = await mount(FallDetectionCard);
  (Accelerometer.isAvailableAsync as jest.Mock).mockResolvedValue(false);
  await toggle(tree, true); await confirmAlert("Entiendo, activar");
  expect(text(tree)).toContain("no informa un acelerómetro disponible");
  (Accelerometer.isAvailableAsync as jest.Mock).mockResolvedValue(true);
  (Accelerometer.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: "denied", canAskAgain: false });
  await toggle(tree, true); await confirmAlert("Entiendo, activar");
  expect(text(tree)).toContain("Falta el permiso de movimiento");
  expect(saveFallSettings).not.toHaveBeenCalled();
  expect(tree.root.findByType(Switch).props.value).toBe(false);
});

test("turning it off needs no confirmation and clears the acknowledgement", async () => {
  (getFallSettings as jest.Mock).mockResolvedValue({ enabled: true, limitationsAcknowledgedAt: 5 });
  const tree = await mount(FallDetectionCard);
  expect(tree.root.findByType(Switch).props.value).toBe(true);
  await toggle(tree, false);
  expect(Alert.alert).not.toHaveBeenCalled();
  expect(saveFallSettings).toHaveBeenCalledWith({ enabled: false, limitationsAcknowledgedAt: null });
});

test("status wording never promises protection that the samples do not support", () => {
  const base = { state: "off", reason: null, appState: "active", sensorAvailable: true, measuredRateHz: null, lastSampleAt: null,
    startedAt: null, monitoredMs: 0, interruptedMs: 0, model: null, counters: null, pendingEventId: null } as const;
  expect(monitorStatusText({ ...base, state: "monitoring", measuredRateHz: 49.6 }, true, true)).toBe("Monitoreo activo (50 Hz).");
  expect(monitorStatusText({ ...base, state: "interrupted", reason: "sin protección" }, true, true)).toContain("sin protección");
  expect(monitorStatusText(base, true, false)).toContain("comenzará cuando inicies un recorrido");
  expect(monitorStatusText(base, false, false)).toContain("no se lee el acelerómetro");
});

test("the route line is hidden when the feature is off", async () => {
  const tree = await mount(FallDetectionStatusLine);
  expect(text(tree)).toBe("");
});

jest.mock("../../hooks/useScreenFocused", () => ({ useScreenFocused: () => true }));
jest.mock("../MiSenderoUI", () => ({ colors: { white: "white", ink: "black", green: "green", line: "gray", soft: "white", muted: "gray", mint: "green", danger: "red" } }));
jest.mock("../../../services/fieldAssessments", () => ({ getFieldSnapshot: jest.fn(), saveBorgCheckin: jest.fn(), evaluateMorningAms: jest.fn() }));
jest.mock("../../../services/deviceLocation", () => ({ getCurrentDeviceLocation: jest.fn() }));
import React from "react";
import { AppState, Modal, type AppStateStatus } from "react-native";
import { FieldAssessmentPanel } from "../FieldAssessmentPanel";
import { getFieldSnapshot, saveBorgCheckin, evaluateMorningAms } from "../../../services/fieldAssessments";
import { getCurrentDeviceLocation } from "../../../services/deviceLocation";
import { invalidateSessionContext } from "../../../services/sessionEpoch";
import { act, mount, press, text, flush } from "../../../testing/mobileHarness";
const snapshot = () => ({ enabled: true, reason: null, checkins: [{ borg: 4, recordedAt: Date.now()-300000 }], reminderDue: true,
  fatigue: { status: "available", value: 5, reason: "orientativa" } });
beforeEach(() => {
  (getFieldSnapshot as jest.Mock).mockResolvedValue(snapshot());
  (saveBorgCheckin as jest.Mock).mockResolvedValue({ borg: 6, recordedAt: Date.now() });
  (evaluateMorningAms as jest.Mock).mockResolvedValue({ status: "available", label: null, score: .16, reason: "Sin clasificación binaria." });
  (getCurrentDeviceLocation as jest.Mock).mockResolvedValue({ altitudeM: 3000 });
});
test("optional effort prompt separates declared and estimated Borg and submits only explicit answers", async () => {
  const tree = await mount(FieldAssessmentPanel, { trailId: 7, startedAt: 100000 });
  expect(text(tree)).toContain("Declarado: 4/10"); expect(text(tree)).toContain("Estimado: 5/10");
  expect(tree.root.findByType(Modal).props.visible).toBe(false);
  await press(tree,"Más tarde"); expect(text(tree)).not.toContain("Si querés");
  await press(tree,"Registrar esfuerzo"); await press(tree,"Borg 6"); await press(tree,"Guardar esfuerzo");
  expect(saveBorgCheckin).toHaveBeenCalledWith(7,100000,6);
  expect(tree.root.findByType(Modal).props.visible).toBe(false);
  await press(tree,"Registrar esfuerzo"); await press(tree,"Cancelar");
});
test("save failures keep the answer reviewable and simulator/consent-disabled sessions show no controls", async () => {
  (saveBorgCheckin as jest.Mock).mockRejectedValue(new Error("Permiso revocado"));
  const tree = await mount(FieldAssessmentPanel, { trailId: 7, startedAt: 100000, compact: true });
  await press(tree,"Registrar esfuerzo"); await press(tree,"Borg 0"); await press(tree,"Guardar esfuerzo");
  expect(text(tree)).toContain("Permiso revocado");
  await act(async () => tree.root.findByType(Modal).props.onRequestClose());
  const simulated = await mount(FieldAssessmentPanel, { trailId: 7, simulated: true });
  expect(simulated.toJSON()).toBeNull();
  (getFieldSnapshot as jest.Mock).mockResolvedValue({ enabled: false });
  const disabled = await mount(FieldAssessmentPanel, { trailId: 7 });
  expect(disabled.toJSON()).toBeNull();
});
test("height control needs three confirmations, requests GPS explicitly and displays a score without an all-clear", async () => {
  const tree = await mount(FieldAssessmentPanel, { trailId: 7, morning: true });
  expect(getCurrentDeviceLocation).not.toHaveBeenCalled();
  for (const label of ["Descansé durante la noche", "Estoy en reposo ahora", "Todavía no inicié el próximo ascenso"]) await press(tree,label);
  await press(tree,"Realizar control");
  expect(evaluateMorningAms).toHaveBeenCalledWith(expect.objectContaining({ trailId: 7, startedAt: 0, restedOvernight: true, restingNow: true, beforeAscent: true }));
  expect(text(tree)).toContain("0.16"); expect(text(tree)).toContain("Sin clasificación binaria");
  (evaluateMorningAms as jest.Mock).mockResolvedValue({ status: "missing_inputs", reason: "Falta SpO₂" });
  await press(tree,"Realizar control"); expect(text(tree)).toContain("Falta SpO₂");
});
test("backgrounding, account switches and late async responses clear sensitive screen state", async () => {
  let changed: (state: AppStateStatus) => void = () => {};
  jest.spyOn(AppState,"addEventListener").mockImplementation((_event, listener) => { changed = listener; return { remove: jest.fn() }; });
  const tree = await mount(FieldAssessmentPanel, { trailId: 7, startedAt: 100000 });
  await act(async () => changed("background")); expect(tree.toJSON()).toBeNull();
  await act(async () => { changed("active"); await flush(); }); expect(text(tree)).toContain("Declarado");
  let resolve: (value: unknown) => void = () => {};
  (getFieldSnapshot as jest.Mock).mockReturnValue(new Promise(done => { resolve = done; }));
  await act(async () => changed("active"));
  await act(async () => invalidateSessionContext());
  await act(async () => { resolve(snapshot()); await flush(); });
  expect(tree.toJSON()).toBeNull();
});
test("read failures and missing fatigue inputs do not block the route", async () => {
  (getFieldSnapshot as jest.Mock).mockRejectedValue(new Error("closed"));
  const tree = await mount(FieldAssessmentPanel, { trailId: 7 }); expect(tree.toJSON()).toBeNull();
  (getFieldSnapshot as jest.Mock).mockResolvedValue({ ...snapshot(), checkins: [], fatigue: { status: "missing_inputs", reason: "Falta pulso completo" } });
  const waiting = await mount(FieldAssessmentPanel, { trailId: 7, startedAt: 100000 });
  expect(text(waiting)).toContain("Todavía no registraste"); expect(text(waiting)).toContain("Falta pulso completo");
});

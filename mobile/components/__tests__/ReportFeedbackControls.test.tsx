import "../../../testing/mobileSetup";
jest.mock("../../../services/syncQueue", () => ({ enqueue: jest.fn(), runSync: jest.fn().mockResolvedValue({ processed: 1, failed: 0 }) }));
import { mount, press, text } from "../../../testing/mobileHarness";
import { enqueue, runSync } from "../../../services/syncQueue";
import { ReportFeedbackControls } from "../ReportFeedbackControls";
import type { TrailReport } from "../../../types";
const report: TrailReport = { id: 13, trail_id: 7, issue_summary: "Barro", severity: "Media", trail_state: "Precaucion", blocks_path: false,
  cause: null, details: null, latitude: -41, longitude: -71, route_progress_meters: 100, created_at: new Date().toISOString() };
test("a community response is saved through the existing queue and repeated taps cannot create additional votes", async () => {
  (enqueue as jest.Mock).mockResolvedValue(1);
  const changed = jest.fn().mockResolvedValue(undefined);
  const tree = await mount(ReportFeedbackControls, { report, onChanged: changed, observedAt: "2026-11-05T12:00:00.000Z" });
  await press(tree, "Sigue igual");
  expect(enqueue).toHaveBeenCalledWith("report_feedback", { reportId: 13, trailId: 7, feedback: "still_there", observed_at: "2026-11-05T12:00:00.000Z" });
  await expect(press(tree, "Sigue igual")).rejects.toThrow("disabled");
  expect(runSync).toHaveBeenCalledTimes(1);
  await press(tree, "No pude verificar");
  expect(enqueue).toHaveBeenLastCalledWith("report_feedback", expect.objectContaining({ feedback: "unsure" }));
});
test("a local save failure remains actionable and does not display the answer as recorded", async () => {
  (enqueue as jest.Mock).mockRejectedValueOnce(new Error("No hay espacio para guardar"));
  const recorded = jest.fn(); const tree = await mount(ReportFeedbackControls, { report, onRecorded: recorded });
  await press(tree, "Ya no está"); expect(text(tree)).toContain("No hay espacio"); expect(recorded).not.toHaveBeenCalled();
  (enqueue as jest.Mock).mockResolvedValueOnce(2);
  await press(tree, "Ya no está"); expect(recorded).toHaveBeenCalledTimes(1);
});

test("a previous response can be confirmed again on a new visit without adding a second vote", async () => {
  (enqueue as jest.Mock).mockResolvedValue(3);
  const tree = await mount(ReportFeedbackControls, { report: { ...report, my_feedback: "still_there" } });
  await press(tree, "Sigue igual");
  expect(enqueue).toHaveBeenCalledWith("report_feedback", expect.objectContaining({ reportId: 13, feedback: "still_there" }));
  await expect(press(tree, "Sigue igual")).rejects.toThrow("disabled");
});

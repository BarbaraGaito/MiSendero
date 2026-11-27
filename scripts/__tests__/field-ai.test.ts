jest.mock("node:child_process", () => ({ spawnSync: jest.fn() }));
jest.mock("node:fs", () => ({ existsSync: jest.fn() }));
const { spawnSync } = require("node:child_process");
const { existsSync } = require("node:fs");
const { run } = require("../field-ai.cjs");
test("CLI forwards frozen run identifiers and reports missing runtime or subprocess failures", () => {
  existsSync.mockReturnValue(false); expect(() => run(["prepare"])).toThrow(".venv-ai");
  existsSync.mockReturnValue(true); expect(() => run(["other"])).toThrow("Uso");
  spawnSync.mockReturnValue({ status: 0 }); expect(run(["validate","--run","v1"])).toBe(0);
  expect(spawnSync).toHaveBeenCalledWith(expect.any(String), [expect.stringContaining("field_ai.py"),"validate","--run","v1"], expect.objectContaining({ stdio: "inherit" }));
  spawnSync.mockReturnValue({ status: null }); expect(run(["evaluate"])).toBe(1);
  spawnSync.mockReturnValue({ error: new Error("failed") }); expect(() => run(["select"])).toThrow("failed");
});

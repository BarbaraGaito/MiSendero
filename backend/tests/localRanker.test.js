jest.mock("node:child_process", () => ({ spawn: jest.fn() }));
const { spawn } = require("node:child_process");
const { EventEmitter } = require("events");
const { PassThrough } = require("stream");
const { LocalRanker } = require("../dist/ai/model");
const { featureSpec } = require("../dist/ai/features");
let child, ranker;
const vector = [1, 1, 0.5, 120, 5, 0, 0, null, null, null, null, null, null, null];
beforeEach(() => {
  child = Object.assign(new EventEmitter(), { stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), killed: false });
  child.kill = jest.fn(() => { child.killed = true; });
  spawn.mockReturnValue(child);
  ranker = new LocalRanker("C:/private/models/version1", "python-test");
});
afterEach(() => { ranker.stop(); spawn.mockClear(); jest.useRealTimers(); });
async function ready() {
  const startup = ranker.start();
  child.stdout.write(JSON.stringify({ type: "ready", modelVersion: "rf-test", featureSchemaVersion: featureSpec.version }) + "\n");
  expect(await startup).toBe(true);
}

test("an optional absent model and an unready worker do not delay API recommendations", async () => {
  const absent = new LocalRanker("", "python-test");
  expect(await absent.predict([vector])).toBeNull();
  expect(spawn).not.toHaveBeenCalled();
  expect(await ranker.predict([vector])).toBeNull();
  expect(spawn).toHaveBeenCalledTimes(1);
});

test("one private process loads once; protocol correlates finite scores and never forwards secrets", async () => {
  await ready(); await ranker.start();
  expect(spawn).toHaveBeenCalledTimes(1);
  const [executable, args, options] = spawn.mock.calls[0];
  expect(executable).toBe("python-test");
  expect(args).toContain("--model-dir");
  expect(options).toMatchObject({ shell: false, windowsHide: true, stdio: "pipe" });
  for (const name of ["DATABASE_URL", "JWT_SECRET", "OPENAI_API_KEY", "PYTHONPATH"]) expect(options.env).not.toHaveProperty(name);
  const result = ranker.predict([vector]);
  const frame = JSON.parse(child.stdin.read().toString());
  expect(frame.features).toEqual([vector]);
  child.stdout.write(JSON.stringify({ id: frame.id, scores: [2.4] }) + "\n");
  expect(await result).toEqual({ scores: [2.4], modelVersion: "rf-test" });
});

test.each(["not json\n", JSON.stringify({ id: 99, scores: [1] }) + "\n", JSON.stringify({ id: 1, scores: [1, 2] }) + "\n", JSON.stringify({ id: 1, scores: [null] }) + "\n"])("malformed inference stops the worker and falls back: %s", async (message) => {
  await ready();
  const pending = ranker.predict([vector]);
  child.stdout.write(message);
  expect(await pending).toBeNull();
  expect(child.kill).toHaveBeenCalled();
  expect(await ranker.predict([vector])).toBeNull();
  expect(spawn).toHaveBeenCalledTimes(1);
});

test("worker crash resolves all pending requests to the baseline", async () => {
  await ready();
  const a = ranker.predict([vector]), b = ranker.predict([vector]);
  child.emit("exit", 1);
  expect(await a).toBeNull(); expect(await b).toBeNull();
});

test("broken stdout/stderr pipes do not become unhandled backend errors", async () => {
  await ready();
  const pending = ranker.predict([vector]);
  child.stderr.emit("error", new Error("broken pipe"));
  expect(await pending).toBeNull();
});

test("an inference deadline kills the blocked child and releases pending work", async () => {
  jest.useFakeTimers();
  await ready();
  const pending = ranker.predict([vector]);
  jest.advanceTimersByTime(5001);
  expect(await pending).toBeNull();
  expect(child.kill).toHaveBeenCalled();
});

test("startup failure is isolated; wrong feature schemas and oversized frames are refused", async () => {
  const startup = ranker.start();
  child.stdout.write(JSON.stringify({ type: "ready", modelVersion: "invalid", featureSchemaVersion: -1 }) + "\n");
  expect(await startup).toBe(false);
  expect(await ranker.predict([vector])).toBeNull();
});

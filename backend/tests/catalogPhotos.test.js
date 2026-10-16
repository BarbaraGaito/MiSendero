jest.mock("node:fs/promises", () => ({ readFile: jest.fn(), writeFile: jest.fn() }));
jest.mock("../src/data/additionalTrailDefinitions", () => [{ key: "verified", photo_file: "Trail.jpg", photo_author: "Photographer" }, { key: "other", photo_file: "Other.jpg", photo_author: "Another" }]);
const fs = require("node:fs/promises");
const argv = process.argv;
const tick = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
const photo = (name) => ({ title: `File:${name}`, imageinfo: [{ url: "https://commons.example.test/photo?temporary=1", descriptionurl: "https://commons.example.test/page", extmetadata: { LicenseUrl: { value: "https://creativecommons.org/licenses/by/4.0/" }, LicenseShortName: { value: "CC BY 4.0" } } }] });
beforeEach(() => { jest.clearAllMocks(); jest.useFakeTimers({ now: Date.UTC(2026, 9, 16) }); process.argv = ["node", "catalogPhotos.js"]; fs.readFile.mockResolvedValue(JSON.stringify({ preserved: { file: "old.jpg" } })); fs.writeFile.mockResolvedValue(undefined); jest.spyOn(console, "log").mockImplementation(() => {}); jest.spyOn(console, "error").mockImplementation(() => {}); });
afterEach(() => { process.argv = argv; process.exitCode = 0; jest.restoreAllMocks(); jest.useRealTimers(); });
const run = async () => { jest.isolateModules(() => require("../scripts/catalogPhotos")); await tick(); };
test("selected catalogue refresh preserves other records, verifies licence metadata and removes transient URL parameters", async () => {
  process.argv.push("--keys=verified"); const fetchMock = jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => ({ query: { pages: { 1: photo("Trail.jpg") } } }) }); await run();
  expect(fetchMock).toHaveBeenCalledTimes(1); const written = JSON.parse(fs.writeFile.mock.calls[0][1]); expect(written.preserved.file).toBe("old.jpg"); expect(written.verified).toMatchObject({ author: "Photographer", license: "CC BY 4.0", url: "https://commons.example.test/photo", retrieved_at: new Date().toISOString() });
});
test("an unverified photo or failed provider aborts without replacing the catalogue", async () => {
  const fetchMock = jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => ({ query: { pages: {} } }) }); await run(); expect(console.error).toHaveBeenCalledWith(expect.stringContaining("verified photo")); expect(fs.writeFile).not.toHaveBeenCalled(); expect(process.exitCode).toBe(1);
  fetchMock.mockResolvedValue({ ok: false, status: 503 }); await run(); expect(console.error).toHaveBeenLastCalledWith("Commons HTTP 503"); expect(fs.writeFile).not.toHaveBeenCalled();
});
test("discovery reports candidates without writing a production catalogue and rejects an ambiguous selection option", async () => {
  process.argv.push("--key=verified"); await run(); expect(console.error).toHaveBeenCalledWith("--key is only supported for discovery"); expect(fs.writeFile).not.toHaveBeenCalled();
  process.argv.push("--discover"); jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => ({ query: { pages: { 1: photo("Trail.jpg") } } }) }); await run(); await jest.advanceTimersByTimeAsync(2000); expect(console.log).toHaveBeenCalledWith(expect.stringContaining('"key":"verified"')); expect(fs.writeFile).not.toHaveBeenCalled();
});

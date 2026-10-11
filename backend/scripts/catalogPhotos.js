const fs = require("node:fs/promises");
const path = require("node:path");
const definitions = require("../src/data/additionalTrailDefinitions");

const main = async () => {
  const output = {};
  const outputPath = path.resolve(__dirname, "../src/data/additionalTrailPhotos.json");
  const keys = process.argv.find((arg) => arg.startsWith("--keys="))?.slice(7).split(",");
  let batch;
  const discover = process.argv.includes("--discover");
  if (keys && !discover) Object.assign(output, JSON.parse(await fs.readFile(outputPath, "utf8")));
  if (!discover && process.argv.some((arg) => arg.startsWith("--key="))) throw new Error("--key is only supported for discovery");
  for (const trail of definitions) {
    if (keys && !keys.includes(trail.key)) continue;
    const onlyKey = process.argv.find((arg) => arg.startsWith("--key="))?.slice(6);
    if (onlyKey && onlyKey !== trail.key) continue;
    const url = new URL("https://commons.wikimedia.org/w/api.php");
    url.search = new URLSearchParams({ action: "query",
      ...(!discover ? { titles: [...new Set(definitions.map((item) => `File:${item.photo_file}`))].join("|") } : trail.photo_file ? { titles: `File:${trail.photo_file}` } : {
        generator: "search", gsrsearch: trail.photo_search, gsrnamespace: "6", gsrlimit: "10",
      }), prop: "imageinfo", iiprop: "url|extmetadata", iiurlwidth: "1280", format: "json" }).toString();
    if (!batch) {
      const response = await fetch(url, { headers: { "User-Agent": "MiSendero/1.0 (university hiking catalog; photo attribution)" },
        signal: AbortSignal.timeout(30000) });
      if (!response.ok) throw new Error(`Commons HTTP ${response.status}`);
      batch = await response.json();
    }
    const data = batch;
    const pages = Object.values(data.query?.pages || {}).sort((a, b) => a.index - b.index);
    if (discover) {
      batch = null;
      await new Promise((resolve) => setTimeout(resolve, 2000));
      console.log(JSON.stringify({ key: trail.key, candidates: pages.map((page) => ({
        file: page.title, description: page.imageinfo?.[0]?.extmetadata?.ImageDescription?.value,
        author: page.imageinfo?.[0]?.extmetadata?.Artist?.value,
        license: page.imageinfo?.[0]?.extmetadata?.LicenseShortName?.value,
      })) }));
      continue;
    }
    const photo = pages.find((page) => page.title === `File:${trail.photo_file}`)?.imageinfo?.[0];
    if (!photo?.url || !trail.photo_author || !photo.extmetadata?.LicenseUrl?.value) {
      throw new Error(`Select and attribute a verified photo for ${trail.key}`);
    }
    output[trail.key] = { file: trail.photo_file, author: trail.photo_author,
      url: (photo.thumburl || photo.url).split("?")[0], page_url: photo.descriptionurl,
      license: photo.extmetadata.LicenseShortName.value, license_url: photo.extmetadata.LicenseUrl.value,
      retrieved_at: new Date().toISOString() };
    console.log(`${trail.key}: ${output[trail.key].file}`);
  }
  if (!discover) {
    await fs.writeFile(outputPath, JSON.stringify(output, null, 2) + "\n");
  }
};

main().catch((error) => { console.error(error.message); process.exitCode = 1; });

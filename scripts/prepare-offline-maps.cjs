// Run manually when the catalog changes; the app never queries public OSM APIs.
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const routes = [
  ...Object.values(require('../backend/src/data/realTrailRoutes')),
  ...Object.values(require('../backend/src/data/additionalTrailRoutes.json')).map(r => r.points),
  ...Object.values(require('../backend/src/data/catalogExpansionRoutes20261017.json')).map(r => r.points),
].filter(p => p?.length > 1);
const bounds = points => ({ south: Math.min(...points.map(p => p[0])) - .015,
  north: Math.max(...points.map(p => p[0])) + .015,
  west: Math.min(...points.map(p => p[1])) - .02, east: Math.max(...points.map(p => p[1])) + .02 });
const union = (a,b) => ({ south: Math.min(a.south,b.south), north: Math.max(a.north,b.north), west: Math.min(a.west,b.west), east: Math.max(a.east,b.east) });
const regions = [];
for (const points of routes) {
  const b = bounds(points);
  const match = regions.find(r => r.south < b.north && r.north > b.south && r.west < b.east && r.east > b.west &&
    (union(r,b).north-union(r,b).south)*(union(r,b).east-union(r,b).west) < .08);
  if (match) Object.assign(match,union(match,b)); else regions.push(b);
}
const inside = (p,b) => p.lat >= b.south && p.lat <= b.north && p.lon >= b.west && p.lon <= b.east;
const coordinate = p => [Number(p.lat.toFixed(6)),Number(p.lon.toFixed(6))];
function features(data,b) {
  const output = [];
  for (const e of data.elements) {
    const t = e.tags || {};
    const kind = t.highway ? (['path','footway','steps','track','pedestrian','bridleway'].includes(t.highway) ? 'path' : 'road')
      : t.waterway ? 'river' : t.natural === 'water' ? 'water'
      : t.natural === 'wood' || t.landuse === 'forest' ? 'forest'
      : e.type === 'node' && t.name ? 'place' : null;
    if (!kind) continue;
    if (e.type === 'node') {
      if (inside(e,b)) output.push({ id: `n${e.id}`, kind, name: t.name.slice(0,80), points: [coordinate(e)] });
      continue;
    }
    if (e.type !== 'way' || !e.geometry?.length) continue;
    const closed = ['water','forest'].includes(kind) && e.nodes?.[0] === e.nodes?.at(-1);
    // Do not fabricate polygon closures when the provider clips a geometry.
    if (closed && e.geometry.every(p => p && Number.isFinite(p.lat))) {
      output.push({ id: `w${e.id}`, kind, name: t.name?.slice(0,80), closed: true, points: e.geometry.map(coordinate) });
    } else {
      let segment = [];
      const flush = () => { if (segment.length > 1) output.push({ id: `w${e.id}-${output.length}`, kind, name: t.name?.slice(0,80), points: segment }); segment = []; };
      for (const p of e.geometry) { if (p && Number.isFinite(p.lat)) segment.push(coordinate(p)); else flush(); }
      flush();
    }
  }
  return output.sort((a,b) => ['forest','water','river','road','path','place'].indexOf(a.kind)-['forest','water','river','road','path','place'].indexOf(b.kind));
}
async function main() {
  if (process.argv.includes('--verify')) {
    const data = JSON.parse(await fs.readFile('assets/offline-maps/catalog.json','utf8'));
    if (data.version !== 1 || data.license !== 'ODbL-1.0' || !data.attribution || !data.licenseUrl || !data.sourceUrl)
      throw Error('Missing source metadata');
    for (const points of routes) {
      if (!data.maps.some(m => m.features?.length && m.sourceDate && points.every(([lat,lon]) => inside({lat,lon},m.bounds))))
        throw Error(`Missing coverage for route starting at ${points[0]}`);
    }
    if (data.maps.some(m => m.features.some(f => !f.points.length || f.points.some(p => !p.every(Number.isFinite)))))
      throw Error('Invalid feature geometry');
    console.log(`Verified ${data.maps.length} regions covering ${routes.length} routes; ${(JSON.stringify(data).length/1024/1024).toFixed(2)} MiB of JSON.`);
    return;
  }
  const cache = path.resolve('tmp/offline-map-sources');
  await fs.mkdir(cache,{recursive:true});
  const maps = [];
  for (const b of regions) {
    const bbox = [b.south,b.west,b.north,b.east].map(n => n.toFixed(6)).join(',');
    const id = crypto.createHash('sha256').update(bbox).digest('hex').slice(0,12);
    const file = path.join(cache,`${id}.json`);
    let data;
    try { data = JSON.parse(await fs.readFile(file,'utf8')); }
    catch {
      const query = `[out:json][timeout:45][maxsize:33554432];(way[highway](${bbox});way[waterway](${bbox});way[natural~"^(water|wood)$"](${bbox});way[landuse=forest](${bbox});node[place][name](${bbox});node[natural=peak][name](${bbox});node[tourism~"^(viewpoint|alpine_hut|wilderness_hut|camp_site)$"][name](${bbox}););out geom(${bbox});`;
      const response = await fetch('https://overpass-api.de/api/interpreter',{ method:'POST',
        headers:{'Content-Type':'application/x-www-form-urlencoded','User-Agent':'MiSendero university offline cartography preparation'},
        body:`data=${encodeURIComponent(query)}`,signal:AbortSignal.timeout(60000) });
      if (!response.ok) throw Error(`HTTP ${response.status} preparing ${id}; rerun to resume from cache`);
      data = await response.json();
      if (data.remark || !Array.isArray(data.elements)) throw Error(`Incomplete region ${id}: ${data.remark}`);
      await fs.writeFile(file,JSON.stringify(data));
    }
    const items = features(data,b);
    if (!items.length) throw Error(`Empty map ${id}`);
    maps.push({id,bounds:b,features:items,sourceDate:data.osm3s?.timestamp_osm_base || new Date().toISOString()});
    console.log(`${maps.length}/${regions.length} ${id}: ${items.length} features`);
  }
  await fs.mkdir('assets/offline-maps',{recursive:true});
  const result = {version:1,attribution:'© OpenStreetMap contributors',license:'ODbL-1.0',
    licenseUrl:'https://opendatacommons.org/licenses/odbl/1-0/',sourceUrl:'https://www.openstreetmap.org/copyright',maps};
  await fs.writeFile('assets/offline-maps/catalog.json',JSON.stringify(result));
  console.log(`Prepared ${maps.length} basic 2D regions for ${routes.length} catalog routes.`);
}
if(require.main === module) main().catch(e => { console.error(e.message); process.exitCode=1; });
module.exports = {features,regions,routes};

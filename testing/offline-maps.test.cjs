const {test} = require('node:test');
const assert = require('node:assert/strict');
const {features,routes} = require('../scripts/prepare-offline-maps.cjs');
test('all catalog geometries have a prepared region with real mapped features and source metadata', () => {
  const catalog = require('../assets/offline-maps/catalog.json');
  assert.equal(catalog.license,'ODbL-1.0');
  assert.match(catalog.sourceUrl,/openstreetmap.org/);
  for (const route of routes) {
    const region = catalog.maps.find(m => route.every(([lat,lon]) => lat >= m.bounds.south && lat <= m.bounds.north && lon >= m.bounds.west && lon <= m.bounds.east));
    assert.ok(region,`Missing region at ${route[0]}`);
    assert.ok(region.features.length > 0);
    assert.ok(Number.isFinite(Date.parse(region.sourceDate)));
    assert.ok(region.features.every(f => f.points.length && f.points.every(p => p.length === 2 && p.every(Number.isFinite))));
  }
});
test('clipped source geometries preserve gaps and never invent polygon closures', () => {
  const geometry = [{lat:0,lon:0},{lat:0,lon:1},null,{lat:1,lon:1},{lat:1,lon:0}];
  const result = features({elements:[{type:'way',id:1,nodes:[1,2,3,4,1],tags:{natural:'water'},geometry}]},{});
  assert.equal(result.length,2);
  assert.deepEqual(result[0].points,[[0,0],[0,1]]);
  assert.deepEqual(result[1].points,[[1,1],[1,0]]);
  assert.ok(result.every(f => !f.closed));
});

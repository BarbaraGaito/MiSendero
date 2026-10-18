// Research build: only source polylines and shared-node OSM walking paths; no interpolation.
const fs=require('node:fs'),path=require('node:path');
const {assemble}=require('./catalogGeometry');
const {sampleRoute}=require('../src/trailElevation');
const evidence=require('../src/data/catalogExpansionEvidence20261017.json');
const read=f=>{if(!evidence.files[f])throw Error('Missing reviewed source '+f);return evidence.files[f];};
const hash=f=>{if(!evidence.source_hashes[f])throw Error('Missing source digest '+f);return evidence.source_hashes[f];};
const km=p=>sampleRoute(p).samples.at(-1).distance_m/1000;
const eq=(a,b)=>a[0]===b[0]&&a[1]===b[1];
const join=(...lines)=>lines.reduce((a,b)=>{if(!a.length)return b;if(!eq(a.at(-1),b[0]))throw Error('Disconnected source segments');return a.concat(b.slice(1));},[]);
const back=p=>p.concat(p.slice(0,-1).reverse());
const mid={mburucuya:'1sggSbbuusRIxFOAprWsrL96YMRgaku7M',rey:'1ULnLCqJekBzDwSVMPGQ5cWG7pXYylMCX',alerces:'1qzpIFZpovu1alDAuCrCl2d8jTvePoLZz',aconquija:'1ShP1Khs_w91wYnvSDxS7HjgnwkR1tJ7l',quijadas:'1QcnHRODe4FHzqqCDvH_zYu4E1iaVUwbQ',leoncito:'10DICzZmEMiPZoWiNaG1su3d-QMD66IjT',fuego:'1IHBZbX667Zt1wGgnv8-14CSV0MBfb8f2',lanin:'1VDRg9Fsx25ISaYK__xlylYHm-0zeL-Ox',condorito:'1FX1jmSalj2oF2leRIpYnSSZBxN1yRBDS'};
const routes={};
function add(key,points,meta){
 for(const p of points)if(!p.every(Number.isFinite))throw Error('Invalid coordinates');
 routes[key]={points,distance_km:Number(km(points).toFixed(3)),retrieved_at:'2026-10-17',navigation_ready:true,...meta};
}
function official(key,park,pattern,{returnTrip=true,partial=false,note='',line=0}={}){
 const file=park+'-official.kml',matches=read(file+'.json').filter(p=>new RegExp(pattern,'i').test(p.name)&&p.lines.length);
 if(!matches.length)throw Error('Missing '+key);const feature=matches[0];const points=feature.lines[line];
 add(key,returnTrip?back(points):points,{source:'Administración de Parques Nacionales',source_url:`https://www.google.com/maps/d/viewer?mid=${mid[park]}`,download_url:`https://www.google.com/maps/d/kml?mid=${mid[park]}&forcekml=1`,license:'CC BY 4.0',license_url:'https://creativecommons.org/licenses/by/4.0/',source_sha256:hash(file),source_feature:feature.name,navigation_ready:!partial,scope:partial?'partial_reference':'published_itinerary',note:note||'Cartografía publicada por APN. No es un relevamiento GPS propio ni certifica apertura o condiciones actuales.'});
}
function osm(key,file,specs,{returnTrip=true,...meta}={}){const r=assemble(specs,read(file).elements);add(key,returnTrip?back(r.points):r.points,{source:'OpenStreetMap contributors',source_url:'https://www.openstreetmap.org/way/'+specs[0].id,license:'ODbL-1.0',license_url:'https://opendatacommons.org/licenses/odbl/1-0/',source_sha256:hash(file),ways:r.ways,scope:'mapped_itinerary',note:'Recorrido cartográfico sobre senderos conectados de OpenStreetMap; no certifica apertura ni condiciones actuales.',...meta});}
// Che Roga: access + stem + outer loop + return at the same shared nodes.
osm('mburucuya-che-roga','mburucuya-osm.json',[
 {id:507806572},{id:328651992},{id:507806566},{id:507806568,to:3354695765},
 {id:328651989,reverse:true},{id:507806568,reverse:true,from:3354695673},
 {id:507806566,reverse:true},{id:328651992,reverse:true},{id:507806572,reverse:true}],{returnTrip:false});
official('mburucuya-tape-pora','mburucuya','Histórico Tapé',{partial:true,note:'APN publica un tramo de 336 m entre las casas históricas; no cubre la totalidad del paseo de 1 km. Mapa de referencia; no habilitado para iniciar navegación.'});
official('el-rey-la-chuna','rey','La Chuña');
// Patitos: use the actually connected official access roads, clipping only at exact source vertices.
{const file='rey-official.kml',features=read(file+'.json');const spur=features.find(p=>p.name==='Camino a Laguna Los Patitos').lines[0];const approach=features.find(p=>p.name==='Camino a Río Popayán').lines[0];
 const cut=approach.findIndex(p=>eq(p,spur[0]));const points=join(approach.slice(0,cut+1),spur);
 add('el-rey-laguna-patitos',back(points),{source:'Administración de Parques Nacionales',source_url:`https://www.google.com/maps/d/viewer?mid=${mid.rey}`,license:'CC BY 4.0',source_sha256:hash(file),source_feature:'Camino a Río Popayán + Camino a Laguna Los Patitos',scope:'partial_reference',navigation_ready:false,note:'Tramo publicado desde el desvío al Río Popayán hasta el acceso a la laguna. Falta verificar la conexión desde el Centro Operativo y el acceso final al borde del agua; mapa parcial.'});}
official('quijadas-farallones','quijadas','Farallones',{partial:true,note:'Senda publicada por APN de 3,2 km por sentido; no incluye todos los accesos del itinerario oficial de 9 km. Guía obligatorio. Referencia cartográfica parcial.'});
official('leoncito-cerro','leoncito','Cerro El Leoncito',{returnTrip:false,partial:true,note:'Circuito publicado por APN de 6,3 km, con cabeceras distintas. Falta verificar el cierre por el camino de acceso del itinerario de 8 km; no se dibuja una unión recta.'});
official('fuego-pampa-alta','fuego','Pampa Alta',{returnTrip:false});
official('alerces-alto-petiso','alerces','Alto El Petizo',{partial:true,note:'Senda publicada por APN de 6,4 km por sentido; la ficha refiere 8 km de ida. El archivo no permite certificar la totalidad del ascenso. Guía y registro obligatorios.'});
osm('alerces-laguna-escondida','alerces-osm.json',[{id:412055906},{id:412055910,reverse:true},{id:1222371562},{id:461265464}]);
official('alerces-arroyo-hacha','alerces','Arroyo del Hacha',{partial:true,note:'APN publica un tramo de 433 m por sentido; la ficha describe 1 km de ida. No se completa el tramo faltante con una línea aproximada.'});
official('alerces-cerro-cocinero','alerces','Cerro Cocinero',{partial:true,note:'Traza parcial publicada por APN de 4,4 km por sentido frente a 8 km de ida en la ficha. APN informa un cierre por incendio en la página de actividades consultada el 17/10/2026; consultar al parque. No habilitado para iniciar navegación.'});
// Exact shared-node walking graph, used to identify the Tacul branch (never a straight shortcut).
function walkingPath(file,start,end){const {elements}=read(file);const nodes=new Map(elements.filter(e=>e.type==='node').map(n=>[n.id,n]));const graph=new Map();
 const ways=elements.filter(w=>w.type==='way'&&['path','footway','steps','track','pedestrian'].includes(w.tags?.highway)&&w.tags.access!=='no'&&w.tags.foot!=='no');
 for(const w of ways)for(let i=1;i<w.nodes.length;i++){const a=w.nodes[i-1],b=w.nodes[i];if(!nodes.has(a)||!nodes.has(b))continue;const cost=km([[nodes.get(a).lat,nodes.get(a).lon],[nodes.get(b).lat,nodes.get(b).lon]]);for(const [f,t]of[[a,b],[b,a]]){if(!graph.has(f))graph.set(f,[]);graph.get(f).push({to:t,cost,way:w.id});}}
 const dist=new Map([[start,0]]),prev=new Map(),done=new Set();while(true){let u;let best=Infinity;for(const [id,d]of dist)if(!done.has(id)&&d<best){u=id;best=d;}if(u===undefined)throw Error('No connected path');if(u===end)break;done.add(u);for(const edge of graph.get(u)||[])if(best+edge.cost<(dist.get(edge.to)??Infinity)){dist.set(edge.to,best+edge.cost);prev.set(edge.to,{from:u,way:edge.way});}}
 const edges=[];let at=end;while(at!==start){const e=prev.get(at);edges.unshift({id:e.way,from:e.from,to:at});at=e.from;}
 const specs=[];for(const e of edges){const w=ways.find(w=>w.id===e.id);e.reverse=w.nodes.indexOf(e.from)>w.nodes.indexOf(e.to);const p=specs.at(-1);if(p&&p.id===e.id&&p.reverse===e.reverse)p.to=e.to;else specs.push(e);}return specs;
}
osm('llao-llao-villa-tacul','llao-osm.json',walkingPath('llao-osm.json',2105971936,2107792644),{note:'Variante desde el estacionamiento de Villa Tacul al mirador del Cerro Llao Llao y regreso por la misma senda. No se usa el track de Puerto Pañuelo.'});
{const f=read('condorito-official.kml.json').find(p=>/Secretos/i.test(p.name));const stem=f.lines[0];const p=join(stem,f.lines[1],stem.slice().reverse());add('condorito-secretos-pies',p,{source:'Administración de Parques Nacionales',source_url:`https://www.google.com/maps/d/viewer?mid=${mid.condorito}`,license:'CC BY 4.0',source_sha256:hash('condorito-official.kml'),scope:'published_itinerary',note:'Acceso y circuito interpretativo publicados por APN, unidos exclusivamente en su vértice compartido.'});}
{const f=read('aconquija-official.kml.json').find(p=>/Puesto Los Chorizos/i.test(p.name));const points=join(...f.lines);add('aconquija-puesto-chorizos',back(points),{source:'Administración de Parques Nacionales',source_url:`https://www.google.com/maps/d/viewer?mid=${mid.aconquija}`,license:'CC BY 4.0',source_sha256:hash('aconquija-official.kml'),scope:'published_itinerary',note:'Dos segmentos publicados que comparten vértice; regreso por la misma senda.'});}
official('aconquija-el-pozon','aconquija','El Pozón');
for(const [size,num]of[['chico','06'],['grande','08']]){const file=`moreno-${size}.gpx`;const p=read(file+'.json')[0].lines[0];add('moreno-belgrano-'+size,p,{source:'Circuito de senderos del Parque Nacional Perito Moreno',source_url:'https://trekkingperitomoreno.com/sendero-peninsulabelgrano/',download_url:`https://trekkingperitomoreno.com/maps/tracks/track-${num}.gpx`,license:'Consultar condiciones de la fuente oficial',source_sha256:hash(file),scope:'published_itinerary',note:'GPX publicado para el circuito '+size+'. Se conserva tal cual: las cabeceras del archivo son distintas en el sector de acceso. No se agrega un cierre recto ni se reemplaza la distancia oficial por la longitud del archivo.'});}
official('lanin-cara-sur-puerto-canoa','lanin','Base Vº Lanin Cara Sur');
// Rosales stage: omit the disconnected first member; preserve the connected part without bridging it.
{const file='rosales-osm.json',data=read(file);const rel=data.elements.find(e=>e.type==='relation'&&e.id===9379221);const ways=new Map(data.elements.filter(e=>e.type==='way').map(w=>[w.id,w]));const nodes=new Map(data.elements.filter(e=>e.type==='node').map(n=>[n.id,n]));let chain=[],metadata=[];
 for(const member of rel.members.filter(m=>m.type==='way').slice(1)){const w=ways.get(member.ref);let ids=w.nodes.slice();if(chain.length&&chain.at(-1)===ids.at(-1))ids.reverse();if(chain.length&&chain.at(-1)!==ids[0])throw Error('Rosales disconnected '+w.id);if(w.tags?.access==='no'||w.tags?.foot==='no')throw Error('Closed way');chain.push(...(chain.length?ids.slice(1):ids));metadata.push({id:w.id,version:w.version,timestamp:w.timestamp});}
 add('lanin-rosales-san-martin',chain.map(id=>[nodes.get(id).lat,nodes.get(id).lon]),{source:'OpenStreetMap contributors',source_url:'https://www.openstreetmap.org/relation/9379221',license:'ODbL-1.0',source_sha256:hash(file),ways:metadata,scope:'partial_reference',navigation_ready:false,note:'Parte continua de la etapa Huella Andina Rosales–San Martín. Se excluye el primer miembro desconectado y no incluye toda la extensión urbana de la ficha de 14 km. Incluye cruces y tramos de RP48: referencia parcial.'});}
const output=path.join(__dirname,'../src/data/catalogExpansionRoutes20261017.json');
if(process.argv.includes('--verify')){
 if(JSON.stringify(routes)!==JSON.stringify(JSON.parse(fs.readFileSync(output,'utf8'))))throw Error('Reviewed routes differ from the reproducible build');
 console.log('Verified: 19 routes reproduced from the committed source geometry snapshot.');
}else{
 fs.writeFileSync(output,JSON.stringify(routes,null,2)+'\n');
 console.log(Object.entries(routes).map(([key,r])=>({key,km:r.distance_km,points:r.points.length,navigationReady:r.navigation_ready})));
}

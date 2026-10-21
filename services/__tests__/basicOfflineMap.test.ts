import type { Trail } from "../../types";
const mockFiles = new Map<string,string>();
jest.mock("expo-file-system/legacy", () => ({
  documentDirectory:"file:///documents/",
  getInfoAsync:jest.fn(async (uri:string) => ({exists:mockFiles.has(uri),size:mockFiles.get(uri)?.length || 0})),
  makeDirectoryAsync:jest.fn(),
  writeAsStringAsync:jest.fn(async (uri:string,text:string) => { mockFiles.set(uri,text); }),
  readAsStringAsync:jest.fn(async (uri:string) => { if (!mockFiles.has(uri)) throw Error("missing"); return mockFiles.get(uri); }),
  moveAsync:jest.fn(async ({from,to}:{from:string;to:string}) => { mockFiles.set(to,mockFiles.get(from)!); mockFiles.delete(from); }),
  deleteAsync:jest.fn(async (uri:string) => { mockFiles.delete(uri); }),
}));
jest.mock("../../assets/offline-maps/catalog.json", () => ({
  attribution:"© OpenStreetMap contributors",license:"ODbL-1.0",licenseUrl:"https://opendatacommons.org/licenses/odbl/1-0/",
  maps:[{id:"region",bounds:{south:-42,north:-40,west:-72,east:-70},sourceDate:"2026-10-20",
    features:[{id:"w1",kind:"path",name:"Sendero real",points:[[-41,-71],[-41.01,-71.01]]}]}],
}));
import * as fs from "expo-file-system/legacy";
import { readBasicOfflineMap, saveBasicOfflineMap, deleteBasicOfflineMap } from "../basicOfflineMap";
const trail = {id:7,route_coordinates:JSON.stringify([[-41,-71],[-41.01,-71.01]]),center_lat:-41,center_lng:-71} as Trail;
beforeEach(() => { mockFiles.clear(); jest.clearAllMocks(); global.fetch = jest.fn().mockRejectedValue(Error("offline")); });
test("saves and verifies the selected 2D region, then reopens entirely from persistent storage", async () => {
  const progress = jest.fn();
  const result = await saveBasicOfflineMap(trail,progress);
  expect(result).toMatchObject({downloadedTiles:1,totalTiles:1});
  expect(result.sizeMb).toBeGreaterThan(0);
  expect(progress).toHaveBeenLastCalledWith(3,3);
  expect((await readBasicOfflineMap(trail))?.features[0].name).toBe("Sendero real");
  expect((await readBasicOfflineMap(trail))?.license).toBe("ODbL-1.0");
  expect(global.fetch).not.toHaveBeenCalled();
  expect([...mockFiles.keys()]).toEqual(["file:///documents/misendero-basic-maps/7.json"]);
});
test("corrupt packages and changed routes cannot be treated as downloaded", async () => {
  await saveBasicOfflineMap(trail);
  expect(await readBasicOfflineMap({...trail,route_coordinates:"[[-41,-71],[-41.1,-71.1]]"})).toBeNull();
  mockFiles.set("file:///documents/misendero-basic-maps/7.json","not json");
  expect(await readBasicOfflineMap(trail)).toBeNull();
});
test("a route outside the packaged zones fails without inventing a basemap", async () => {
  await expect(saveBasicOfflineMap({...trail,route_coordinates:"[[-32,-69],[-32.1,-69.1]]"}))
    .rejects.toMatchObject({code:"basic-map-unavailable"});
  expect(fs.writeAsStringAsync).not.toHaveBeenCalled();
});
test("cancelling after the file is written removes temporary data and cannot produce a complete package", async () => {
  let cancel = false;
  await expect(saveBasicOfflineMap(trail,done => { if(done===2) cancel = true; },{shouldCancel:() => cancel}))
    .rejects.toMatchObject({code:"download-cancelled"});
  expect(await readBasicOfflineMap(trail)).toBeNull();
  expect([...mockFiles.keys()]).toHaveLength(0);
});
test("delete removes only the requested route package", async () => {
  await saveBasicOfflineMap(trail);
  await saveBasicOfflineMap({...trail,id:8});
  await deleteBasicOfflineMap(trail);
  expect(await readBasicOfflineMap(trail)).toBeNull();
  expect(await readBasicOfflineMap({...trail,id:8})).not.toBeNull();
});

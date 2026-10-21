import "../../../testing/mobileSetup";
jest.mock("../../../database/database", () => ({initDB:jest.fn()}));
jest.mock("../../../services/authSession", () => ({getAuthSession:jest.fn()}));
jest.mock("../LoginScreen", () => ({__esModule:true,default:"LoginScreen"}));
import {router} from "expo-router";
import {initDB} from "../../../database/database";
import {getAuthSession} from "../../../services/authSession";
import App from "../../../app/index";
import {act,mount,text,press,flush} from "../../../testing/mobileHarness";
beforeEach(() => {
  jest.useFakeTimers();
  (initDB as jest.Mock).mockResolvedValue(undefined);
  (getAuthSession as jest.Mock).mockResolvedValue(null);
});
afterEach(() => {jest.useRealTimers();});
const advance = async (ms:number) => act(async () => {jest.advanceTimersByTime(ms);await flush();});
test("a successful native initialization leaves the splash and opens login", async () => {
  const tree = await mount(App);
  expect(text(tree)).toContain("Cargando rutas cercanas");
  await advance(1800);
  expect(tree.root.findAllByType("LoginScreen")).toHaveLength(1);
});
test("storage errors expose retry, preserve the login gate, and can recover", async () => {
  (initDB as jest.Mock).mockRejectedValueOnce(Error("URI is not absolute"));
  const tree = await mount(App);
  expect(text(tree)).toContain("No pudimos abrir los datos guardados");
  expect(tree.root.findAllByType("LoginScreen")).toHaveLength(0);
  expect(getAuthSession).not.toHaveBeenCalled();
  await press(tree,"Reintentar inicio");
  await advance(1800);
  expect(initDB).toHaveBeenCalledTimes(2);
  expect(tree.root.findAllByType("LoginScreen")).toHaveLength(1);
});
test("a stalled initialization has a bounded wait and does not expose account data", async () => {
  (initDB as jest.Mock).mockReturnValue(new Promise(() => {}));
  const tree = await mount(App);
  await advance(20000);
  expect(text(tree)).toContain("Reintentar inicio");
  expect(text(tree)).not.toContain("Cargando rutas cercanas");
  expect(getAuthSession).not.toHaveBeenCalled();
});
test("a valid saved session opens the home screen after initialization", async () => {
  (getAuthSession as jest.Mock).mockResolvedValue({user:{id:7},token:"fixture"});
  await mount(App); await advance(1800);
  expect(router.replace).toHaveBeenCalledWith("/inicio");
});

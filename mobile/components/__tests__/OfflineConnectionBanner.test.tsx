import "../../../testing/mobileSetup";
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn(), addNetworkStateListener: jest.fn() }));
import { AppState, Text } from "react-native";
import * as Network from "expo-network";
import { router } from "expo-router";
import { ConnectivityProvider } from "../../../services/ConnectivityProvider";
import { AppScreen } from "../MiSenderoUI";
import { act, flush, mount, press, text } from "../../../testing/mobileHarness";

let networkChange: (state: Network.NetworkState) => void;
let appChange: (state: string) => void;
const removeNetwork = jest.fn(), removeApp = jest.fn();
const Screen = () => <ConnectivityProvider><AppScreen activeTab="inicio"><Text>Inicio de prueba</Text></AppScreen></ConnectivityProvider>;
beforeEach(() => {
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true, isInternetReachable: true });
  (Network.addNetworkStateListener as jest.Mock).mockImplementation(callback => { networkChange = callback; return { remove: removeNetwork }; });
  jest.spyOn(AppState, "addEventListener").mockImplementation((_event, callback) => {
    appChange = callback as typeof appChange;
    return { remove: removeApp };
  });
});

test.each([{ isConnected: false }, { isConnected: true, isInternetReachable: false }])("offline state %j shows the top shortcut to downloaded maps", async state => {
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue(state);
  const tree = await mount(Screen);
  expect(text(tree)).toContain("No hay conexión");
  await press(tree, "No hay conexión. Ver mapas descargados");
  expect(router.navigate).toHaveBeenCalledWith("/offline-mapas-descargados");
});

test("live network changes show and remove the notice without redirecting an active screen", async () => {
  const tree = await mount(Screen);
  expect(text(tree)).not.toContain("No hay conexión");
  await act(async () => networkChange({ isConnected: false }));
  expect(text(tree)).toContain("No hay conexión");
  expect(router.navigate).not.toHaveBeenCalled();
  await act(async () => networkChange({ isConnected: true, isInternetReachable: true }));
  expect(text(tree)).not.toContain("No hay conexión");
  await act(async () => tree.unmount());
  expect(removeNetwork).toHaveBeenCalledTimes(1);
  expect(removeApp).toHaveBeenCalledTimes(1);
});

test("foreground refresh updates connectivity and a slow initial snapshot cannot undo a newer event", async () => {
  let resolveInitial!: (state: Network.NetworkState) => void;
  (Network.getNetworkStateAsync as jest.Mock).mockImplementationOnce(() => new Promise(resolve => { resolveInitial = resolve; }));
  const tree = await mount(Screen);
  await act(async () => {
    networkChange({ isConnected: false });
    resolveInitial({ isConnected: true, isInternetReachable: true });
    await flush();
  });
  expect(text(tree)).toContain("No hay conexión");
  await act(async () => { appChange("active"); await flush(); });
  expect(text(tree)).not.toContain("No hay conexión");
});

test("an unknown or failed network check does not claim there is no connection", async () => {
  (Network.getNetworkStateAsync as jest.Mock).mockRejectedValue(new Error("unavailable"));
  const tree = await mount(Screen);
  expect(text(tree)).not.toContain("No hay conexión");
  await act(async () => networkChange({}));
  expect(text(tree)).not.toContain("No hay conexión");
});

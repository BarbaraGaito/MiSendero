import { createContext, PropsWithChildren, useContext, useEffect, useState } from "react";
import { AppState } from "react-native";
import * as Network from "expo-network";

const OfflineContext = createContext(false);
export const useIsOffline = () => useContext(OfflineContext);

export function ConnectivityProvider({ children }: PropsWithChildren) {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let mounted = true;
    let generation = 0;
    const update = (state: Network.NetworkState) => {
      if (mounted) setOffline(state.isConnected === false || state.isInternetReachable === false);
    };
    const refresh = () => {
      const request = ++generation;
      void Network.getNetworkStateAsync().then(state => {
        if (request === generation) update(state);
      }).catch(() => undefined);
    };
    const network = Network.addNetworkStateListener(state => {
      generation += 1;
      update(state);
    });
    const app = AppState.addEventListener("change", state => {
      if (state === "active") refresh();
    });
    refresh();
    return () => { mounted = false; network.remove(); app.remove(); };
  }, []);
  return <OfflineContext.Provider value={offline}>{children}</OfflineContext.Provider>;
}

import { useEffect } from "react";
import { AppState } from "react-native";
import * as Network from "expo-network";
import { runSync } from "./syncQueue";

export function SyncCoordinator() {
  useEffect(() => {
    const sync = () => { void runSync().catch(() => undefined); };
    sync();
    const network = Network.addNetworkStateListener((state) => {
      if (state.isConnected && state.isInternetReachable !== false) sync();
    });
    const app = AppState.addEventListener("change", (state) => { if (state === "active") sync(); });
    const timer = setInterval(() => { if (AppState.currentState === "active") sync(); }, 15000);
    return () => { clearInterval(timer); network.remove(); app.remove(); };
  }, []);
  return null;
}

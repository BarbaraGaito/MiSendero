import { useEffect } from "react";
import { AppState } from "react-native";
import * as Network from "expo-network";
import { runSync } from "./syncQueue";
import { getAuthSession } from "./authSession";
import { getProfile } from "./api";

export function SyncCoordinator() {
  useEffect(() => {
    let validating = false;
    const sync = () => {
      if (validating) return;
      validating = true;
      void (async () => {
        // Validate even an empty queue so a remotely deleted account is cleared
        // when another installation returns online.
        const session = await getAuthSession();
        if (session) await getProfile(session.token);
        await runSync();
      })().catch(() => undefined).finally(() => { validating = false; });
    };
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

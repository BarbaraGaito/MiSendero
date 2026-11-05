import { useSyncExternalStore } from "react";
import { fallMonitor } from "../../services/fallDetection/monitor";

export const useFallMonitor = () => useSyncExternalStore(fallMonitor.subscribe, fallMonitor.getSnapshot, fallMonitor.getSnapshot);

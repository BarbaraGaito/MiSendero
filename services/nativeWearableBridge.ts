import { Platform } from "react-native";
import { WearableMetricSample, WearableProvider } from "../types";

export interface NativeWearableBridge {
  provider: WearableProvider;
  isAvailable(): Promise<boolean>;
  requestPermissions(): Promise<boolean>;
  readLatestSample(): Promise<
    Omit<WearableMetricSample, "id" | "user_id" | "createdAt"> | null
  >;
}

const unavailableBridge: NativeWearableBridge = {
  provider:
    Platform.OS === "ios"
      ? "apple_healthkit"
      : Platform.OS === "android"
        ? "android_health_connect"
        : "development_simulator",
  async isAvailable() {
    return false;
  },
  async requestPermissions() {
    return false;
  },
  async readLatestSample() {
    return null;
  },
};

export const getNativeWearableBridge = () => unavailableBridge;

import { WearableMetricSample, WearableProvider } from "../types";

export interface NativeWearableReadOptions {
  since?: number;
}

export interface NativeWearableBridge {
  provider: WearableProvider;
  isAvailable: () => Promise<boolean>;
  requestPermissions: () => Promise<boolean>;
  readLatestSample: (
    options?: NativeWearableReadOptions
  ) => Promise<Omit<WearableMetricSample, "id" | "user_id" | "createdAt"> | null>;
}

const unavailableBridge: NativeWearableBridge = {
  provider: "development_simulator",
  isAvailable: async () => false,
  requestPermissions: async () => false,
  readLatestSample: async () => null,
};

export const getNativeWearableBridge = () => unavailableBridge;

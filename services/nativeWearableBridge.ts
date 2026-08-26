import { Platform } from "react-native";
import { WearableMetricSample, WearableProvider } from "../types";

type HealthKitModule = typeof import("@kingstinct/react-native-healthkit");
type HealthConnectModule = typeof import("react-native-health-connect");
type HealthConnectRecordType = Parameters<HealthConnectModule["readRecords"]>[0];

export interface NativeWearableReadOptions {
  startAt?: number;
  endAt?: number;
  requireHeartRate?: boolean;
}

const healthKitReadTypes = [
  "HKQuantityTypeIdentifierHeartRate",
  "HKQuantityTypeIdentifierStepCount",
  "HKQuantityTypeIdentifierActiveEnergyBurned",
  "HKQuantityTypeIdentifierWalkingSpeed",
  "HKQuantityTypeIdentifierOxygenSaturation",
] as const;

const healthConnectReadPermissions = [
  { accessType: "read", recordType: "HeartRate" },
  { accessType: "read", recordType: "Steps" },
  { accessType: "read", recordType: "ActiveCaloriesBurned" },
  { accessType: "read", recordType: "Speed" },
  { accessType: "read", recordType: "OxygenSaturation" },
] as const;

const getHealthKit = (): HealthKitModule | null => {
  if (Platform.OS !== "ios") return null;

  try {
    // Expo Go does not include this native module. Loading lazily keeps the rest
    // of the app usable there while development builds load the iOS bridge.
    return require("@kingstinct/react-native-healthkit") as HealthKitModule;
  } catch {
    return null;
  }
};

const getHealthConnect = (): HealthConnectModule | null => {
  if (Platform.OS !== "android") return null;

  try {
    return require("react-native-health-connect") as HealthConnectModule;
  } catch {
    return null;
  }
};

const readQuantitySafely = async <T>(read: () => Promise<T>) => {
  try {
    return await read();
  } catch {
    return undefined;
  }
};

const toTimestamp = (value: Date | undefined) =>
  value && !Number.isNaN(value.getTime()) ? value.getTime() : 0;

const toTimestampFromIso = (value: string | undefined) => {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
};

const getHealthConnectRecordTimestamp = (record: {
  endTime?: string;
  time?: string;
}) => toTimestampFromIso(record.endTime ?? record.time);

const getLatestByTimestamp = <T extends { endTime?: string; time?: string }>(
  records: T[]
) =>
  records.reduce<T | null>((latest, record) => {
    if (!latest) return record;
    return getHealthConnectRecordTimestamp(record) >
      getHealthConnectRecordTimestamp(latest)
      ? record
      : latest;
  }, null);

const hasHealthConnectPermission = (
  permissions: Array<{ accessType?: string; recordType?: string }>,
  recordType: string
) =>
  permissions.some(
    (permission) =>
      permission.accessType === "read" && permission.recordType === recordType
  );

const readHealthConnectRecordsSafely = async (
  healthConnect: HealthConnectModule,
  recordType: HealthConnectRecordType,
  startTime: string,
  endTime: string
) => {
  try {
    const { records } = await healthConnect.readRecords(recordType, {
      timeRangeFilter: {
        operator: "between",
        startTime,
        endTime,
      },
      ascendingOrder: false,
      pageSize: 50,
    });

    return records as any[];
  } catch {
    return [];
  }
};

const appleHealthKitBridge: NativeWearableBridge = {
  provider: "apple_healthkit",
  async isAvailable() {
    const healthKit = getHealthKit();
    if (!healthKit) return false;

    try {
      return await healthKit.isHealthDataAvailableAsync();
    } catch {
      return false;
    }
  },
  async requestPermissions() {
    const healthKit = getHealthKit();
    if (!healthKit) return false;

    try {
      const granted = await healthKit.requestAuthorization({
        toRead: healthKitReadTypes,
      });

      if (granted) {
        await healthKit.configureBackgroundTypes(
          [
            "HKQuantityTypeIdentifierHeartRate",
            "HKQuantityTypeIdentifierStepCount",
            "HKQuantityTypeIdentifierActiveEnergyBurned",
          ],
          healthKit.UpdateFrequency.hourly
        );
      }

      return granted;
    } catch {
      return false;
    }
  },
  async readLatestSample() {
    const healthKit = getHealthKit();
    if (!healthKit) return null;

    const [heartRate, steps, activeEnergy, walkingSpeed, oxygenSaturation] =
      await Promise.all([
        readQuantitySafely(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierHeartRate",
            "count/min"
          )
        ),
        readQuantitySafely(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierStepCount",
            "count"
          )
        ),
        readQuantitySafely(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierActiveEnergyBurned",
            "kcal"
          )
        ),
        readQuantitySafely(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierWalkingSpeed",
            "m/s"
          )
        ),
        readQuantitySafely(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierOxygenSaturation",
            "%"
          )
        ),
      ]);

    if (!heartRate && !steps && !activeEnergy && !walkingSpeed && !oxygenSaturation) {
      return null;
    }

    const recordedAt = Math.max(
      toTimestamp(heartRate?.endDate),
      toTimestamp(steps?.endDate),
      toTimestamp(activeEnergy?.endDate),
      toTimestamp(walkingSpeed?.endDate),
      toTimestamp(oxygenSaturation?.endDate)
    );

    return {
      provider: "apple_healthkit" as const,
      heartRateBpm: heartRate?.quantity ?? null,
      steps: steps ? Math.round(steps.quantity) : null,
      activeEnergyKcal: activeEnergy?.quantity ?? null,
      speedKmh:
        walkingSpeed?.quantity !== undefined
          ? Number((walkingSpeed.quantity * 3.6).toFixed(1))
          : null,
      oxygenSaturation: oxygenSaturation?.quantity ?? null,
      recordedAt,
    };
  },
};

const androidHealthConnectBridge: NativeWearableBridge = {
  provider: "android_health_connect",
  async isAvailable() {
    const healthConnect = getHealthConnect();
    if (!healthConnect) return false;

    try {
      const sdkStatus = await healthConnect.getSdkStatus();
      if (sdkStatus !== healthConnect.SdkAvailabilityStatus.SDK_AVAILABLE) {
        return false;
      }

      return await healthConnect.initialize();
    } catch {
      return false;
    }
  },
  async requestPermissions() {
    const healthConnect = getHealthConnect();
    if (!healthConnect) return false;

    try {
      const initialized = await healthConnect.initialize();
      if (!initialized) return false;

      const granted = await healthConnect.requestPermission([
        ...healthConnectReadPermissions,
      ]);

      return hasHealthConnectPermission(granted, "HeartRate");
    } catch {
      return false;
    }
  },
  async readLatestSample(options) {
    const healthConnect = getHealthConnect();
    if (!healthConnect) return null;

    try {
      const initialized = await healthConnect.initialize();
      if (!initialized) return null;
    } catch {
      return null;
    }

    const endTime = new Date(options?.endAt ?? Date.now());
    const startTime = new Date(
      options?.startAt ?? endTime.getTime() - 6 * 60 * 60 * 1000
    );
    const [heartRate, steps, activeEnergy, speed, oxygenSaturation] =
      await Promise.all([
        readHealthConnectRecordsSafely(
          healthConnect,
          "HeartRate",
          startTime.toISOString(),
          endTime.toISOString()
        ),
        readHealthConnectRecordsSafely(
          healthConnect,
          "Steps",
          startTime.toISOString(),
          endTime.toISOString()
        ),
        readHealthConnectRecordsSafely(
          healthConnect,
          "ActiveCaloriesBurned",
          startTime.toISOString(),
          endTime.toISOString()
        ),
        readHealthConnectRecordsSafely(
          healthConnect,
          "Speed",
          startTime.toISOString(),
          endTime.toISOString()
        ),
        readHealthConnectRecordsSafely(
          healthConnect,
          "OxygenSaturation",
          startTime.toISOString(),
          endTime.toISOString()
        ),
      ]);

    const latestHeartRate = heartRate
      .flatMap((record) => record.samples ?? [])
      .reduce<any | null>((latest, sample) => {
        if (!latest) return sample;
        return toTimestampFromIso(sample.time) > toTimestampFromIso(latest.time)
          ? sample
          : latest;
      }, null);
    const latestSpeed = speed
      .flatMap((record) => record.samples ?? [])
      .reduce<any | null>((latest, sample) => {
        if (!latest) return sample;
        return toTimestampFromIso(sample.time) > toTimestampFromIso(latest.time)
          ? sample
          : latest;
      }, null);
    const latestOxygen = getLatestByTimestamp(oxygenSaturation);
    const latestRecordedAt = Math.max(
      toTimestampFromIso(latestHeartRate?.time),
      toTimestampFromIso(latestSpeed?.time),
      getHealthConnectRecordTimestamp(latestOxygen ?? {}),
      ...steps.map(getHealthConnectRecordTimestamp),
      ...activeEnergy.map(getHealthConnectRecordTimestamp)
    );

    const totalSteps = steps.reduce(
      (total, record) => total + Math.round(record.count ?? 0),
      0
    );
    const totalActiveEnergy = activeEnergy.reduce(
      (total, record) => total + (record.energy?.inKilocalories ?? 0),
      0
    );

    if (options?.requireHeartRate && !latestHeartRate) {
      return null;
    }

    if (
      !latestHeartRate &&
      totalSteps === 0 &&
      totalActiveEnergy === 0 &&
      !latestSpeed &&
      !latestOxygen
    ) {
      return null;
    }

    return {
      provider: "android_health_connect" as const,
      heartRateBpm: latestHeartRate?.beatsPerMinute ?? null,
      steps: totalSteps > 0 ? totalSteps : null,
      activeEnergyKcal:
        totalActiveEnergy > 0 ? Number(totalActiveEnergy.toFixed(1)) : null,
      speedKmh:
        latestSpeed?.speed?.inKilometersPerHour !== undefined
          ? Number(latestSpeed.speed.inKilometersPerHour.toFixed(1))
          : null,
      oxygenSaturation:
        latestOxygen?.percentage !== undefined
          ? Number(latestOxygen.percentage.toFixed(1))
          : null,
      recordedAt: latestRecordedAt || Date.now(),
    };
  },
};

export interface NativeWearableBridge {
  provider: WearableProvider;
  isAvailable(): Promise<boolean>;
  requestPermissions(): Promise<boolean>;
  readLatestSample(options?: NativeWearableReadOptions): Promise<
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

export const getNativeWearableBridge = () =>
  Platform.OS === "ios"
    ? appleHealthKitBridge
    : Platform.OS === "android"
      ? androidHealthConnectBridge
      : unavailableBridge;

import { Platform } from "react-native";
import { WearableMetricSample, WearableProvider } from "../types";

type HealthKitModule = typeof import("@kingstinct/react-native-healthkit");
type HealthConnectModule = typeof import("react-native-health-connect");
type HealthConnectRecordType = Parameters<HealthConnectModule["readRecords"]>[0];

type HealthKitQuantitySample = {
  quantity?: number;
  endDate?: Date;
};

type HealthConnectSample = {
  beatsPerMinute?: number;
  speed?: {
    inKilometersPerHour?: number;
  };
  time?: string;
};

type HealthConnectRecord = {
  count?: number;
  endTime?: string;
  energy?: {
    inKilocalories?: number;
  };
  percentage?: number;
  samples?: HealthConnectSample[];
  time?: string;
};

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

    return records as HealthConnectRecord[];
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

      // Reads are foreground/on demand. Background delivery is not requested.

      return granted;
    } catch {
      return false;
    }
  },
  async readLatestSample(options) {
    const healthKit = getHealthKit();
    if (!healthKit) return null;

    let [heartRate, steps, activeEnergy, walkingSpeed, oxygenSaturation] =
      await Promise.all([
        readQuantitySafely<HealthKitQuantitySample>(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierHeartRate",
            "count/min"
          ) as Promise<HealthKitQuantitySample>
        ),
        readQuantitySafely<HealthKitQuantitySample>(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierStepCount",
            "count"
          ) as Promise<HealthKitQuantitySample>
        ),
        readQuantitySafely<HealthKitQuantitySample>(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierActiveEnergyBurned",
            "kcal"
          ) as Promise<HealthKitQuantitySample>
        ),
        readQuantitySafely<HealthKitQuantitySample>(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierWalkingSpeed",
            "m/s"
          ) as Promise<HealthKitQuantitySample>
        ),
        readQuantitySafely<HealthKitQuantitySample>(() =>
          healthKit.getMostRecentQuantitySample(
            "HKQuantityTypeIdentifierOxygenSaturation",
            "%"
          ) as Promise<HealthKitQuantitySample>
        ),
      ]);

    const inWindow = (sample: HealthKitQuantitySample | undefined) => {
      const timestamp = toTimestamp(sample?.endDate);
      return timestamp > 0 && timestamp >= (options?.startAt ?? Date.now() - 300000) && timestamp <= (options?.endAt ?? Date.now() + 30000);
    };
    heartRate = inWindow(heartRate) ? heartRate : undefined;
    steps = inWindow(steps) ? steps : undefined;
    activeEnergy = inWindow(activeEnergy) ? activeEnergy : undefined;
    walkingSpeed = inWindow(walkingSpeed) ? walkingSpeed : undefined;
    oxygenSaturation = inWindow(oxygenSaturation) ? oxygenSaturation : undefined;
    if (options?.requireHeartRate && !heartRate) return null;
    // Do not combine a new pulse with older oxygen or speed measurements.
    const pulseTime = toTimestamp(heartRate?.endDate);
    if (pulseTime) {
      if (Math.abs(toTimestamp(walkingSpeed?.endDate) - pulseTime) > 60000) walkingSpeed = undefined;
      if (Math.abs(toTimestamp(oxygenSaturation?.endDate) - pulseTime) > 60000) oxygenSaturation = undefined;
    }

    if (!heartRate && !steps && !activeEnergy && !walkingSpeed && !oxygenSaturation) {
      return null;
    }

    const recordedAt = pulseTime || Math.max(
      toTimestamp(heartRate?.endDate),
      toTimestamp(steps?.endDate),
      toTimestamp(activeEnergy?.endDate),
      toTimestamp(walkingSpeed?.endDate),
      toTimestamp(oxygenSaturation?.endDate)
    );

    return {
      provider: "apple_healthkit" as const,
      heartRateBpm: heartRate?.quantity ?? null,
      steps: steps?.quantity !== undefined ? Math.round(steps.quantity) : null,
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
      .reduce<HealthConnectSample | null>((latest, sample) => {
        if (!latest) return sample;
        return toTimestampFromIso(sample.time) > toTimestampFromIso(latest.time)
          ? sample
          : latest;
      }, null);
    let latestSpeed = speed
      .flatMap((record) => record.samples ?? [])
      .reduce<HealthConnectSample | null>((latest, sample) => {
        if (!latest) return sample;
        return toTimestampFromIso(sample.time) > toTimestampFromIso(latest.time)
          ? sample
          : latest;
      }, null);
    let latestOxygen = getLatestByTimestamp(oxygenSaturation);
    const pulseTime = toTimestampFromIso(latestHeartRate?.time);
    if (pulseTime) {
      if (Math.abs(toTimestampFromIso(latestSpeed?.time) - pulseTime) > 60000) latestSpeed = null;
      if (Math.abs(getHealthConnectRecordTimestamp(latestOxygen ?? {}) - pulseTime) > 60000) latestOxygen = null;
    }
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
      recordedAt: pulseTime || latestRecordedAt,
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

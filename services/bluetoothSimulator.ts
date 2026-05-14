import { PhoneToWatchPayload, SensorSample, WatchCommand } from '../types';
import { SENSOR_INTERVAL_MS, getSimulationProfile } from './simulationProfile';

type Listener<T> = (payload: T) => void;

class BluetoothSimulator {
  private commandListeners = new Set<Listener<WatchCommand>>();
  private phoneListeners = new Set<Listener<PhoneToWatchPayload>>();
  private sensorInterval: ReturnType<typeof setInterval> | null = null;
  private sensorListeners = new Set<Listener<SensorSample>>();
  private step = 0;

  subscribeToCommands(listener: Listener<WatchCommand>) {
    this.commandListeners.add(listener);

    return () => {
      this.commandListeners.delete(listener);
    };
  }

  subscribeToPhoneUpdates(listener: Listener<PhoneToWatchPayload>) {
    this.phoneListeners.add(listener);

    return () => {
      this.phoneListeners.delete(listener);
    };
  }

  subscribeToWatchData(listener: Listener<SensorSample>) {
    this.sensorListeners.add(listener);

    return () => {
      this.sensorListeners.delete(listener);
    };
  }

  sendPhoneUpdate(payload: PhoneToWatchPayload) {
    this.phoneListeners.forEach((listener) => listener(payload));
  }

  sendWatchCommand(command: WatchCommand) {
    this.commandListeners.forEach((listener) => listener(command));
  }

  startSensorStream() {
    if (this.sensorInterval) {
      return;
    }

    this.step = 0;
    this.sensorInterval = setInterval(() => {
      const sample = getSimulationProfile(this.step);
      this.step += 1;

      this.sensorListeners.forEach((listener) =>
        listener({
          heartRate: sample.heartRate,
          timestamp: Date.now(),
        })
      );
    }, SENSOR_INTERVAL_MS);
  }

  stopSensorStream() {
    if (!this.sensorInterval) {
      return;
    }

    clearInterval(this.sensorInterval);
    this.sensorInterval = null;
    this.step = 0;
  }
}

export const bluetoothSimulator = new BluetoothSimulator();


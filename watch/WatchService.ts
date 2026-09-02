import { bluetoothSimulator } from "../services/bluetoothSimulator";

let interval: ReturnType<typeof setInterval> | undefined;
let simulationSeed = Date.now() % 2_147_483_647;

const nextSimulationRatio = () => {
  simulationSeed = (simulationSeed * 48_271) % 2_147_483_647;
  return simulationSeed / 2_147_483_647;
};

export const startWatch = () => {
  stopWatch();

  emitHeartRate();
  interval = setInterval(() => {
    emitHeartRate();
  }, 5000);
};

export const stopWatch = () => {
  if (interval) {
    clearInterval(interval);
    interval = undefined;
  }
};

const emitHeartRate = () => {
  const fakeHR = Math.floor(nextSimulationRatio() * 75) + 88;

  bluetoothSimulator.send({
    hr: fakeHR,
    timestamp: Date.now(),
  });
};

import { bluetoothSimulator } from "../services/bluetoothSimulator";

let interval: any;

export const startWatch = () => {
  stopWatch();

  emitHeartRate();
  interval = setInterval(() => {
    emitHeartRate();
  }, 5000);
};

export const stopWatch = () => {
  clearInterval(interval);
};

const emitHeartRate = () => {
  const fakeHR = Math.floor(Math.random() * 75) + 88;

  bluetoothSimulator.send({
    hr: fakeHR,
    timestamp: Date.now(),
  });
};

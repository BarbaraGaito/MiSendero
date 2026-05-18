import { WatchData } from "../types";

type Listener = (data: WatchData) => void;

let listeners: Listener[] = [];

export const bluetoothSimulator = {
  send(data: WatchData) {
    listeners.forEach((cb) => cb(data));
  },

  subscribe(cb: Listener) {
    listeners.push(cb);

    return () => {
      listeners = listeners.filter((listener) => listener !== cb);
    };
  },
};

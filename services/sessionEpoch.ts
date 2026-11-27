let epoch = 0;
const listeners = new Set<() => void>();
export const getSessionEpoch = () => epoch;
export const invalidateSessionContext = () => { epoch += 1; listeners.forEach(listener => listener()); };
export const subscribeSessionEpoch = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};

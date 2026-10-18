let epoch = 0;
export const getSessionEpoch = () => epoch;
export const invalidateSessionContext = () => { epoch += 1; };

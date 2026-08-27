import { runSync } from "./syncQueue";

export const syncSessions = async () => {
  await runSync();
};

import { getAuthSession } from "./authSession";
import { getSessionEpoch } from "./sessionEpoch";

export type AccountContext = Readonly<{ userId: number | null; token: string | null; epoch: number }>;
export class AccountContextChanged extends Error {
  constructor() { super("La sesión cambió. Volvé a intentar la operación con tu cuenta actual."); }
}
export const assertAccountContext = (context: AccountContext) => {
  if (context.epoch !== getSessionEpoch()) throw new AccountContextChanged();
};
export const captureAccountContext = async (): Promise<AccountContext> => {
  const epoch = getSessionEpoch();
  const session = await getAuthSession();
  const context = Object.freeze({ userId: session?.user.id ?? null, token: session?.token ?? null, epoch });
  assertAccountContext(context);
  return context;
};

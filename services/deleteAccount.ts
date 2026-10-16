import { deleteAccount, ApiError } from "./api";
import { clearAuthSession, getAuthSession } from "./authSession";
import { eraseLocalAccountData, markAccountDeletion, cancelLocalAccountDeletion } from "./accountLifecycle";

export async function deleteCurrentAccount(password: string) {
  const session = await getAuthSession();
  if (!session) throw new Error("Iniciá sesión para eliminar tu cuenta.");
  // Persist before the request: a lost response or an app restart must not restart uploads.
  await markAccountDeletion(session.user.id);
  try { await deleteAccount(session.token, password); }
  catch (error) {
    if (error instanceof ApiError && error.code === "INVALID_PASSWORD") await cancelLocalAccountDeletion(session.user.id);
    throw error;
  }
  await eraseLocalAccountData(session.user.id);
  const current = await getAuthSession();
  if (current?.token === session.token) await clearAuthSession();
}

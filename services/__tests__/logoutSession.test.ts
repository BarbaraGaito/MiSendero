jest.mock('../api',()=>({...jest.requireActual('../api'),revokeSession:jest.fn()}));
import * as SecureStore from 'expo-secure-store';
import { saveAuthSession,getAuthSession } from '../authSession';
import { logoutSession,flushPendingRevocations } from '../logoutSession';
import { revokeSession,ApiError } from '../api';
const pending='misendero.pending-revocations.v1';
beforeEach(async()=>{
  jest.restoreAllMocks();jest.clearAllMocks();
  await SecureStore.deleteItemAsync(pending);
  await saveAuthSession({token:'synthetic-logout-token',user:{id:9701,name:'Fixture',email:'logout@example.test'}});
});
test('online logout confirms revocation and removes local access',async()=>{
  (revokeSession as jest.Mock).mockResolvedValue({revoked:true});
  expect(await logoutSession()).toEqual({remoteRevoked:true});
  expect(revokeSession).toHaveBeenCalledWith('synthetic-logout-token');
  expect(await getAuthSession()).toBeNull();expect(await SecureStore.getItemAsync(pending)).toBeNull();
});
test('offline logout retains retry credentials only in SecureStore and flushes after reconnect',async()=>{
  (revokeSession as jest.Mock).mockRejectedValue(new Error('fixture offline'));
  expect(await logoutSession()).toEqual({remoteRevoked:false});expect(await getAuthSession()).toBeNull();
  expect(await SecureStore.getItemAsync(pending)).toBeTruthy();
  (revokeSession as jest.Mock).mockResolvedValue({revoked:true});await flushPendingRevocations();
  expect(await SecureStore.getItemAsync(pending)).toBeNull();
});
test('a token already rejected by the server does not need another pending revocation',async()=>{
  (revokeSession as jest.Mock).mockRejectedValue(new ApiError('fixture revoked',401));
  expect(await logoutSession()).toEqual({remoteRevoked:true});
  expect(await SecureStore.getItemAsync(pending)).toBeNull();
});
test('failed secure persistence of an offline revocation remains visible after local logout',async()=>{
  (revokeSession as jest.Mock).mockRejectedValue(new Error('fixture offline'));
  jest.spyOn(SecureStore,'setItemAsync').mockRejectedValueOnce(new Error('fixture unavailable'));
  await expect(logoutSession()).rejects.toThrow('No se pudo confirmar');
  expect(await getAuthSession()).toBeNull();
});

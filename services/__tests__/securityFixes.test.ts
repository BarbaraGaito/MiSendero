// Observations against production services, with native boundaries replaced.
import { db, initDB } from '../../database/database';
import { saveAuthSession, getAuthSession, clearAuthSession } from '../../services/authSession';
import { savePrivacyPreferences } from '../../services/privacyConsent';
import { saveWearableConnection, syncNativeWearableSampleWithStatus } from '../../services/wearableMetrics';
import { enqueue, getPendingOperations, runSync } from '../../services/syncQueue';
import { resolveApiUrl } from '../../services/apiConfig';
import * as SecureStore from 'expo-secure-store';
import * as lifecycle from '../../services/accountLifecycle';
import * as Network from 'expo-network';
import * as api from '../../services/api';
const fs = require('node:fs');
const observations: unknown[]=[];
const record=(id:string, classification:string, result:unknown)=>observations.push({id,classification,result});
const login=(id:number)=>saveAuthSession({token:`synthetic-audit-${id}`,user:{id,name:'Fixture',email:`audit-${id}@example.test`}});
const mockRead=jest.fn();
jest.mock('expo-secure-store',()=>{
  const values=new Map<string,string>();
  return {__esModule:true,isAvailableAsync:jest.fn().mockResolvedValue(true),
    WHEN_UNLOCKED_THIS_DEVICE_ONLY:1,
    setItemAsync:jest.fn(async(k:string,v:string)=>{values.set(k,v);}),
    getItemAsync:jest.fn(async(k:string)=>values.get(k)??null),
    deleteItemAsync:jest.fn(async(k:string)=>{values.delete(k);})};
});
jest.mock('../../services/nativeWearableBridge',()=>({getNativeWearableBridge:()=>({provider:'android_health_connect',isAvailable:async()=>true,requestPermissions:async()=>true,readLatestSample:(...args:unknown[])=>mockRead(...args)})}));
jest.mock('expo-network',()=>({getNetworkStateAsync:jest.fn().mockResolvedValue({isConnected:false,isInternetReachable:false})}));
jest.mock('../../services/api',()=>({createTrailReport:jest.fn().mockResolvedValue({id:1}),getTrailReports:jest.fn().mockResolvedValue([])}));
beforeAll(async()=>{await initDB();});
afterEach(()=>{jest.restoreAllMocks();});
const sample=()=>({provider:'android_health_connect',heartRateBpm:91,steps:null,activeEnergyKcal:null,speedKmh:null,oxygenSaturation:null,recordedAt:Date.now(),simulated:false});

test('C01 CONTROL: token is absent from ordinary SQLite; logout clears local session',async()=>{
  await login(9101);
  const row=await db.getFirstAsync<{token:string}>('SELECT token FROM auth_session');
  expect(row?.token).toBe('__secure_store__');
  await clearAuthSession(); expect(await getAuthSession()).toBeNull();
  record('C01','control_observado',{tokenSentinelOnly:true,localSessionCleared:true,nativeKeystoreIsDouble:true});
});
test('C02 CONTROL: release endpoint validation rejects HTTP and embedded credentials',()=>{
  expect(()=>resolveApiUrl('http://example.test/api',false)).toThrow();
  expect(()=>resolveApiUrl('https://user:password@example.test/api',false)).toThrow();
  expect(resolveApiUrl('https://example.test/api',false)).toBe('https://example.test/api');
  record('C02','control_observado',{httpRejectedByConfiguration:true,credentialsInUrlRejected:true,liveCertificateTested:false});
});
test('C03 CONTROL: stale health reads are cancelled after a switch',async()=>{
  for(const id of [9102,9103]) {await login(id);await savePrivacyPreferences({sensitiveDataConsent:true,analyticsTrainingConsent:false});await saveWearableConnection('android_health_connect',true,true);}
  await login(9102);
  let release:(value:unknown)=>void=()=>{};
  let started:()=>void=()=>{};
  const readStarted=new Promise<void>(resolve=>{started=resolve;});
  mockRead.mockImplementationOnce(()=>{started();return new Promise(resolve=>{release=resolve;});});
  const inFlight=syncNativeWearableSampleWithStatus();
  await readStarted; await login(9103); release(sample());
  expect(await inFlight).toBe('permission_denied');
  const rows=await db.getAllAsync<{user_id:number}>('SELECT user_id FROM wearable_metric_samples WHERE user_id IN (9102,9103)');
  expect(rows).toHaveLength(0);
  record('C03','control_observado',{staleReadCancelled:true,crossAccountSamples:0});
});
test('C04 CONTROL: revoking the same account consent during native read prevents storing its result',async()=>{
  await login(9104);await savePrivacyPreferences({sensitiveDataConsent:true,analyticsTrainingConsent:false});await saveWearableConnection('android_health_connect',true,true);
  let release:(value:unknown)=>void=()=>{};let started:()=>void=()=>{};
  const readStarted=new Promise<void>(resolve=>{started=resolve;});
  mockRead.mockImplementationOnce(()=>{started();return new Promise(resolve=>{release=resolve;});});
  const operation=syncNativeWearableSampleWithStatus();await readStarted;
  await savePrivacyPreferences({sensitiveDataConsent:false,analyticsTrainingConsent:false});release(sample());
  expect(await operation).toBe('permission_denied');
  expect(await db.getAllAsync('SELECT * FROM wearable_metric_samples WHERE user_id=9104')).toHaveLength(0);
  record('C04','control_observado',{withdrawalEnforcedAfterRead:true});
});
test('C05 CONTROL: report enqueue rejects a changed account context',async()=>{
  await login(9105);
  const original=lifecycle.isAccountDeletionPending;
  let release:(value:boolean)=>void=()=>{};let reached:()=>void=()=>{};
  const checkpoint=new Promise<void>(resolve=>{reached=resolve;});
  jest.spyOn(lifecycle,'isAccountDeletionPending').mockImplementationOnce(()=>{reached();return new Promise(resolve=>{release=resolve;});}).mockImplementation(original);
  const event=require('node:crypto').randomUUID();
  const queued=enqueue('trail_report',{trailId:1,client_event_id:event,issue_summary:'Fixture A'});
  const rejected=expect(queued).rejects.toThrow('sesión cambió');
  await checkpoint;await login(9106);release(false);await rejected;
  const row=await db.getFirstAsync<{user_id:number}>('SELECT user_id FROM pending_operations WHERE payload_json LIKE ?',[`%${event}%`]);
  expect(row).toBeNull();
  record('C05','control_observado',{staleEnqueueRejected:true,crossAccountOperations:0});
});
test('C06 CONTROL: existing queued records are not dispatched as another account',async()=>{
  await login(9107);await enqueue('trail_report',{trailId:1,issue_summary:'Fixture de propietario'});
  await login(9108);
  expect(await getPendingOperations()).toHaveLength(0);
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({isConnected:true,isInternetReachable:true});
  expect(await runSync()).toEqual({processed:0,failed:0});expect(api.createTrailReport).not.toHaveBeenCalled();
  record('C06','control_observado',{persistedQueueOwnerIsolation:true});
});
test('C07 CONTROL: transient keystore deletion failure is retried',async()=>{
  await login(9109);jest.spyOn(SecureStore,'deleteItemAsync').mockRejectedValueOnce(new Error('Fixture unavailable'));
  await clearAuthSession();expect(await getAuthSession()).toBeNull();
  expect(await SecureStore.getItemAsync('misendero.auth.token')).toBeNull();
  record('C07','control_observado',{transientDeleteRetried:true,secureTokenRemoved:true,nativeKeystoreIsDouble:true});
});
test('C08 CONTROL: persistent keystore failure is reported after local access is removed',async()=>{
  await login(9110);jest.spyOn(SecureStore,'deleteItemAsync').mockRejectedValue(new Error('Fixture unavailable'));
  await expect(clearAuthSession()).rejects.toThrow('no pudimos borrar');
  expect(await getAuthSession()).toBeNull();
  record('C08','control_observado',{localAccessRemoved:true,cleanupFailureReported:true});
});
test('C09 CONTROL: A to B to A does not revive an old health operation',async()=>{
  await login(9111);await savePrivacyPreferences({sensitiveDataConsent:true,analyticsTrainingConsent:false});await saveWearableConnection('android_health_connect',true,true);
  let release:(value:unknown)=>void=()=>{};let started:()=>void=()=>{};
  const ready=new Promise<void>(resolve=>{started=resolve;});
  mockRead.mockImplementationOnce(()=>{started();return new Promise(resolve=>{release=resolve;});});
  const reading=syncNativeWearableSampleWithStatus();await ready;
  await login(9112);await login(9111);release(sample());
  expect(await reading).toBe('permission_denied');
  expect(await db.getAllAsync('SELECT * FROM wearable_metric_samples WHERE user_id=9111')).toHaveLength(0);
  record('C09','control_observado',{sameOwnerNewGenerationRejected:true});
});

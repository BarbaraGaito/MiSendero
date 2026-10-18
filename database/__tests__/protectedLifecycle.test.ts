const mockRun=jest.fn();
const mockRelease=jest.fn().mockResolvedValue(undefined);
jest.mock('../protectedStorage',()=>({openProtectedDatabase:async()=>({runAsync:mockRun}),releaseProtectedDatabase:()=>mockRelease()}));
import { db, suspendProtectedStorage, resumeProtectedStorage } from '../connection';

beforeEach(async()=>{await resumeProtectedStorage();jest.clearAllMocks();mockRelease.mockResolvedValue(undefined);});
test('background waits for dispatched SQL, closes storage and rejects new work until resume',async()=>{
  let complete:(value:unknown)=>void=()=>{};
  mockRun.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;}));
  const operation=db.runAsync('fixture');
  await Promise.resolve();await Promise.resolve();
  const closing=suspendProtectedStorage();
  expect(mockRelease).not.toHaveBeenCalled();
  await expect(db.runAsync('must-not-open')).rejects.toThrow('suspendido');
  complete({changes:1});await operation;await closing;
  expect(mockRelease).toHaveBeenCalledTimes(1);
  await resumeProtectedStorage();mockRun.mockResolvedValue({changes:1});
  await expect(db.runAsync('after-resume')).resolves.toMatchObject({changes:1});
});
test('a later background event wins over a resume still waiting for closure',async()=>{
  let release:()=>void=()=>{};
  mockRelease.mockImplementationOnce(()=>new Promise<void>(resolve=>{release=resolve;}));
  const closing=suspendProtectedStorage();
  await Promise.resolve();await Promise.resolve();
  const opening=resumeProtectedStorage();
  const closingAgain=suspendProtectedStorage();release();
  await Promise.all([closing,closingAgain,opening]);
  await expect(db.runAsync('still-background')).rejects.toThrow('suspendido');
});

test('a failed native close keeps access suspended and resume retries cleanup',async()=>{
  mockRelease.mockRejectedValueOnce(new Error('fixture close failure'));
  await expect(suspendProtectedStorage()).rejects.toThrow('fixture close failure');
  await expect(db.runAsync('while-close-failed')).rejects.toThrow('suspendido');
  await resumeProtectedStorage();
  expect(mockRelease).toHaveBeenCalledTimes(2);
  mockRun.mockResolvedValue({changes:1});await expect(db.runAsync('recovered')).resolves.toMatchObject({changes:1});
});

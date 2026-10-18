import { db, initDB } from '../database';
import { applyLocalRetention, installRetentionPolicy } from '../dataRetention';
const DAY=86400000, now=Date.UTC(2026,9,18), old=now-100*DAY;
beforeAll(async()=>{await initDB();});
beforeEach(async()=>{await db.execAsync('DELETE FROM wearable_metric_samples; DELETE FROM route_tracking_points; DELETE FROM sessions; DELETE FROM pending_operations;');});
test('only eligible health rows expire; historical and fresh samples survive repeated maintenance',async()=>{
 for(const date of [old,old,now]) await db.runAsync("INSERT INTO wearable_metric_samples(user_id,provider,recorded_at,created_at) VALUES(1,'fixture',?,?)",[date,date]);
 await db.runAsync('UPDATE wearable_metric_samples SET retention_eligible_at=NULL WHERE id=(SELECT MIN(id) FROM wearable_metric_samples)');
 await installRetentionPolicy();
 expect((await applyLocalRetention(now)).health).toBe(1);
 expect((await applyLocalRetention(now)).health).toBe(0);
 expect(await db.getAllAsync('SELECT id FROM wearable_metric_samples')).toHaveLength(2);
});
test('GPS retention preserves active, paused, historical and orphaned routes and retains completed summaries',async()=>{
 for(let trail=1;trail<=5;trail++){
  await db.runAsync('INSERT INTO route_tracking_points(user_id,trail_id,started_at,latitude,longitude,recorded_at,created_at) VALUES(1,?,1,0,0,?,?)',[trail,old,old]);
  if(trail!==5) await db.runAsync('INSERT INTO sessions(user_id,trail_id,started_at,ended_at,completion_status) VALUES(1,?,1,?,?)',[trail,trail===2?null:old,trail===3?'paused':'completed']);
 }
 await db.runAsync('UPDATE route_tracking_points SET retention_eligible_at=NULL WHERE trail_id=4');
 expect((await applyLocalRetention(now)).points).toBe(1);
 expect(await db.getAllAsync('SELECT id FROM sessions')).toHaveLength(4);
 expect((await db.getAllAsync<{trail_id:number}>('SELECT trail_id FROM route_tracking_points')).map(x=>x.trail_id)).toEqual([2,3,4,5]);
});
test('terminal queue payloads are removed without losing identity; unresolved and recent records survive',async()=>{
 for(const [i,status] of ['synced','abandoned','pending','failed','syncing','synced'].entries())
  await db.runAsync("INSERT INTO pending_operations(entity_type,payload_json,dedupe_key,status,created_at,updated_at) VALUES('emergency_alert','{\"private\":true}',?,?,?,?)",[`retention-${i}`,status,old,i===5?now:old]);
 expect((await applyLocalRetention(now)).payloads).toBe(2);
 const rows=await db.getAllAsync<{payload_json:string;dedupe_key:string}>('SELECT payload_json,dedupe_key FROM pending_operations ORDER BY id');
 expect(rows).toHaveLength(6);expect(rows[0]).toEqual({payload_json:'{}',dedupe_key:'retention-0'});
 expect(rows.slice(2).every(x=>x.payload_json.includes('private'))).toBe(true);
 expect((await applyLocalRetention(now)).payloads).toBe(0);
});

test('closed-plan cache expires only eligible terminal data and preserves unresolved notifications',async()=>{
 await db.execAsync('CREATE TABLE IF NOT EXISTS saved_trip_plans(id INTEGER PRIMARY KEY,user_id INTEGER,trail_id INTEGER,plan_json TEXT); DELETE FROM saved_trip_plans;');
 for(const [index,plan] of [
  {status:'checked_in',retention_eligible_at:new Date(old).toISOString(),closed_at:new Date(old).toISOString(),notification_status:'accepted'},
  {status:'cancelled',closed_at:new Date(old).toISOString()},
  {status:'active',retention_eligible_at:new Date(old).toISOString(),closed_at:new Date(old).toISOString()},
  {status:'cancelled',retention_eligible_at:new Date(old).toISOString(),closed_at:new Date(old).toISOString(),notification_status:'processing'},
 ].entries()) await db.runAsync('INSERT INTO saved_trip_plans VALUES(?,1,1,?)',[index,JSON.stringify(plan)]);
 await applyLocalRetention(now);
 expect((await db.getAllAsync<{id:number}>('SELECT id FROM saved_trip_plans ORDER BY id')).map(x=>x.id)).toEqual([1,2,3]);
});

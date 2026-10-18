const migrate=require('../src/migrate');
const {query}=require('../src/db');
const {applyRemoteRetention}=require('../src/dataRetention');
const now=new Date('2026-10-18T12:00:00Z'), old='2026-01-01T00:00:00Z';
let user;
beforeAll(async()=>{await migrate();user=(await query("INSERT INTO users(name,email,password_hash) VALUES('Fixture','retention@example.test','fixture') RETURNING id")).rows[0].id;});
test('remote retention leaves historical and active records; redacts eligible data and preserves dedupe identities',async()=>{
 for(const [key,eligible] of [['new',old],['historical',null]])
  await query("INSERT INTO emergency_alerts(user_id,client_event_id,latitude,longitude,contact_phone,status,created_at,retention_eligible_at) VALUES($1,$2,1,2,'private','registered',$3,$4)",[user,key,old,eligible]);
 for(const [key,status,eligible,job] of [['closed','checked_in',old,'accepted'],['active','active',old,'pending'],['processing','cancelled',old,'processing'],['legacy','cancelled',null,'cancelled']]){
  const p=(await query("INSERT INTO trip_plans(user_id,client_plan_id,expected_return_at,grace_minutes,contact_name,contact_phone,status,closed_at,created_at,retention_eligible_at) VALUES($1,$2,$3,30,'private','private',$4,$3,$3,$5) RETURNING id",[user,key,old,status,eligible])).rows[0];
  await query('INSERT INTO trip_notifications(plan_id,due_at,next_attempt_at,status) VALUES($1,$2,$2,$3)',[p.id,old,job]);
 }
 expect(await applyRemoteRetention({now})).toEqual({sos:1,plans:1});
 expect(await applyRemoteRetention({now})).toEqual({sos:0,plans:0});
 const sos=(await query('SELECT * FROM emergency_alerts WHERE user_id=$1 ORDER BY id',[user])).rows;
 expect(sos[0]).toMatchObject({client_event_id:'new',latitude:null,longitude:null,contact_phone:null});expect(sos[1].contact_phone).toBe('private');
 const plans=(await query('SELECT * FROM trip_plans WHERE user_id=$1 ORDER BY id',[user])).rows;
 expect(plans[0]).toMatchObject({client_plan_id:'closed',contact_phone:''});expect(plans.slice(1).every(p=>p.contact_phone==='private')).toBe(true);
});

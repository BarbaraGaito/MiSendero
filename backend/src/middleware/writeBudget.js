const { query } = require("../db");
const { requireAuth } = require("./requireAuth");
const definitions = [
  [/^\/trails\/\d+\/reports$/, 'reports', 10, 'trail_reports', 'client_event_id', 'reporter_user_id'],
  [/^\/activities$/, 'activities', 30, 'activities', 'client_session_id', 'user_id'],
  [/^\/trip-plans$/, 'trip-plans', 12, 'trip_plans', 'client_plan_id', 'user_id'],
  [/^\/emergency-alerts$/, 'emergency-alerts', 60, 'emergency_alerts', 'client_event_id', 'user_id'],
  [/^\/auth\/me\/privacy-decisions$/, 'privacy-decisions', 60, 'privacy_decisions', 'client_event_id', 'user_id'],
  [/^\/reports\/\d+(?:\/(?:flag|block-author|moderate))?$/, 'report-actions', 60, null, null, null],
];
const writeBudget = (req, res, next) => {
  const definition = ['POST','PATCH'].includes(req.method) && definitions.find(([pattern]) => pattern.test(req.path));
  if (!definition) return next();
  requireAuth(req,res,async error => {
    if (error) return next(error);
    try {
      const [,resource,limit,table,idColumn,ownerColumn] = definition;
      const identity=req.body?.[idColumn];
      if (table && idColumn && typeof identity === 'string' && identity.length <= 100 && (idColumn !== 'client_event_id' || /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(identity))) {
        // Retrying the same logical event must not consume a new-write budget.
        if ((await query(`SELECT id FROM ${table} WHERE ${ownerColumn} = $1 AND ${idColumn} = $2`,[req.userId,identity])).rows[0]) return next();
      }
      const start = new Date(Math.floor(Date.now()/900000)*900000).toISOString();
      const result=await query(`INSERT INTO api_write_budgets (user_id,resource,window_start,used) VALUES ($1,$2,$3,1)
        ON CONFLICT (user_id,resource,window_start) DO UPDATE SET used = api_write_budgets.used + 1 RETURNING used`,[req.userId,resource,start]);
      if (result.rows[0].used > limit) {
        res.set('Retry-After',String(Math.max(1,Math.ceil((Date.parse(start)+900000-Date.now())/1000))));
        return res.status(429).json({ message: 'Alcanzaste el límite temporal de esta operación. Conservá el envío pendiente y reintentá más tarde.', code:'WRITE_BUDGET_EXCEEDED' });
      }
      next();
    } catch (cause) { next(cause); }
  });
};
module.exports = { writeBudget };

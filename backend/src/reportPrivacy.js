const MAX_DISTANCE_METERS = 130;
const EARTH = 6371000;
const radians = n => n * Math.PI / 180;
const validateReportPosition = (trail, report) => {
  if ((report.latitude == null) !== (report.longitude == null)) return false;
  if (report.latitude == null) return true; // Explicitly unlocated legacy report.
  let points = trail.route_coordinates;
  if (typeof points === "string") { try { points = JSON.parse(points); } catch { return false; } }
  if (!Array.isArray(points) || points.length < 2) return false;
  const cos = Math.cos(radians(report.latitude));
  const project = p => [(radians(p[1] - report.longitude)) * EARTH * cos, radians(p[0] - report.latitude) * EARTH];
  let nearest = Infinity;
  for (let i=1; i<points.length; i++) {
    if (![points[i-1],points[i]].every(p => Array.isArray(p) && p.length===2 && p.every(Number.isFinite))) return false;
    const a=project(points[i-1]), b=project(points[i]);
    const dx=b[0]-a[0], dy=b[1]-a[1], length=dx*dx+dy*dy;
    const t=length ? Math.max(0,Math.min(1,-(a[0]*dx+a[1]*dy)/length)) : 0;
    nearest=Math.min(nearest,Math.hypot(a[0]+t*dx,a[1]+t*dy));
  }
  // A client-supplied accuracy must never expand this server bound.
  return nearest <= MAX_DISTANCE_METERS;
};
const safeOptions = require("./reportPublicPolicy.json");
const normalize = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const safeField = (field,value) => {
  const text=normalize(value);
  const allowed=safeOptions[field].filter(option => field==='issue_summary' ? text.split(/[,;·|]/).map(s=>s.trim()).includes(normalize(option)) : text===normalize(option));
  return allowed.join(', ') || (field==='issue_summary' ? 'Incidente de terreno' : 'Sin clasificar');
};
const hour = value => value == null ? value : new Date(Math.floor(new Date(value).getTime()/3600000)*3600000).toISOString();
const minimizePublicReport = report => ({
  ...report,
  issue_summary: safeField('issue_summary',report.issue_summary),
  severity: safeField('severity',report.severity),
  trail_state: safeField('trail_state',report.trail_state),
  cause: safeField('cause',report.cause),
  details: null,
  latitude: report.latitude == null ? null : Number(Number(report.latitude).toFixed(3)),
  longitude: report.longitude == null ? null : Number(Number(report.longitude).toFixed(3)),
  route_progress_meters: report.route_progress_meters == null ? null : Math.round(report.route_progress_meters/100)*100,
  created_at: hour(report.created_at), observed_at: hour(report.observed_at),
  updated_at: hour(report.updated_at), received_at: hour(report.received_at), expires_at: hour(report.expires_at),
  position_precision_meters: 150,
});
module.exports = { validateReportPosition, minimizePublicReport };

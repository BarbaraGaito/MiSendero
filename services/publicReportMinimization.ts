import type { TrailReport } from "../types";
import options from "../backend/src/reportPublicPolicy.json";
const normalize = (v: unknown) => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const safe = (field: keyof typeof options, value: unknown) => options[field].filter(o => field==='issue_summary' ? normalize(value).split(/[,;·|]/).map(v=>v.trim()).includes(normalize(o)) : normalize(value)===normalize(o)).join(', ') || (field==='issue_summary' ? 'Incidente de terreno' : 'Sin clasificar');
const hour = (v: string | undefined) => v && Number.isFinite(Date.parse(v)) ? new Date(Math.floor(Date.parse(v)/3600000)*3600000).toISOString() : v;
// Existing downloaded copies receive the same public view as the current API.
// Own report editing data and unsent source events retain their owner-only scope.
export const minimizeCachedPublicReport = (r: TrailReport): TrailReport => r.is_mine ? r : {
  ...r, issue_summary:safe('issue_summary',r.issue_summary), severity:safe('severity',r.severity),
  trail_state:safe('trail_state',r.trail_state), cause:safe('cause',r.cause), details:null,
  latitude:r.latitude==null ? null : Number(Number(r.latitude).toFixed(3)),
  longitude:r.longitude==null ? null : Number(Number(r.longitude).toFixed(3)),
  route_progress_meters:r.route_progress_meters==null ? null : Math.round(r.route_progress_meters/100)*100,
  end_latitude:r.end_latitude==null ? null : Number(Number(r.end_latitude).toFixed(3)),
  end_longitude:r.end_longitude==null ? null : Number(Number(r.end_longitude).toFixed(3)),
  route_end_progress_meters:r.route_end_progress_meters==null ? null : Math.round(r.route_end_progress_meters/100)*100,
  created_at:hour(r.created_at)!, observed_at:hour(r.observed_at), updated_at:hour(r.updated_at),
  received_at:hour(r.received_at), expires_at:hour(r.expires_at), position_precision_meters:150,
  last_confirmed_at:hour(r.last_confirmed_at ?? undefined), last_checked_at:hour(r.last_checked_at ?? undefined),
};

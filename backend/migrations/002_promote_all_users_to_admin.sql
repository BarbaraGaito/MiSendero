-- All registered users are now treated as admin (see auth.routes.js).
-- Idempotent: promotes any pre-existing non-admin accounts on every boot.

UPDATE users SET role = 'admin' WHERE role <> 'admin';

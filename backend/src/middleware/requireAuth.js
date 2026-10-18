const jwt = require("jsonwebtoken");
const JWT_ALGORITHM = "HS256";
const { query } = require("../db");
const { isRevoked } = require("../sessionRevocation");

const requireAuth = async (req, res, next) => {
  const authHeader = req.headers.authorization || "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : null;

  if (!token) {
    return res.status(401).json({ message: "Sesion requerida" });
  }

  let payload;
  let expired = false;
  try {
    payload = jwt.verify(token, process.env.JWT_SECRET, {
      algorithms: [JWT_ALGORITHM],
    });
  } catch (error) {
    if (error.name !== "TokenExpiredError") return res.status(401).json({ message: "Sesion invalida" });
    // An authentic expired token can learn that its account was deleted, but
    // never gains access. This lets dormant installations erase stale copies.
    try {
      payload = jwt.verify(token, process.env.JWT_SECRET, { algorithms: [JWT_ALGORITHM], ignoreExpiration: true });
      expired = true;
    } catch { return res.status(401).json({ message: "Sesion invalida" }); }
  }
  try {
    if (!Number.isInteger(payload.userId)) return res.status(401).json({ message: "Sesion invalida" });
    const { rows } = await query("SELECT id, role FROM users WHERE id = $1", [payload.userId]);
    if (!rows[0]) return res.status(401).json({ message: "Cuenta eliminada", code: "ACCOUNT_DELETED" });
    if (expired) return res.status(401).json({ message: "Sesion vencida" });
    if (await isRevoked(token)) return res.status(401).json({ message: "Sesión revocada", code: "SESSION_REVOKED" });
    req.userId = rows[0].id;
    req.userRole = rows[0].role;
    req.authToken = token;
    req.authExpiresAt = payload.exp;
    next();
  } catch (error) { next(error); }
};

const requireAdmin = (req, res, next) => {
  if (req.userRole !== "admin") {
    return res.status(403).json({ message: "Requiere permisos de administrador" });
  }

  next();
};

module.exports = { requireAuth, requireAdmin };

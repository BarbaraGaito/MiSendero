jest.mock("pino", () => jest.fn((options) => ({ options })));
const { options } = require("../src/logger");
const pino = jest.requireActual("pino");

test("redacts credentials, contact and location fields and suppresses database error contents", () => {
  let output = "";
  const logger = pino({ ...options, level: "info" }, { write: (line) => { output += line; } });
  const secret = "private-value-for-test";
  logger.info({ password: secret, token: secret, email: secret, contact_phone: secret,
    req: { headers: { authorization: secret, cookie: secret }, body: { name: secret } },
    user: { email: secret, password_hash: secret, latitude: secret, longitude: secret } }, "metadata");
  logger.error({ err: Object.assign(new Error(secret), { detail: secret, query: secret }) }, "Solicitud fallida");
  expect(output).not.toContain(secret);
  expect(output).toContain("[REDACTED]");
  expect(output).toContain("Solicitud fallida");
});

jest.mock("../src/db", () => ({ query: jest.fn() }));
jest.mock("../src/middleware/requireAuth", () => ({ requireAuth: jest.fn() }));
const { requireAuth } = require("../src/middleware/requireAuth");
const { writeBudget } = require("../src/middleware/writeBudget");

test("write budget forwards a rejected authentication promise to Express", async () => {
  const error = new Error("Authentication unavailable");
  requireAuth.mockRejectedValueOnce(error);
  const next = jest.fn();
  await writeBudget({ method: "POST", path: "/activities" }, {}, next);
  expect(next).toHaveBeenCalledTimes(1);
  expect(next).toHaveBeenCalledWith(error);
});

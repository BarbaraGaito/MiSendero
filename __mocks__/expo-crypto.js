const crypto = require("node:crypto");
module.exports = {
  randomUUID: () => crypto.randomUUID(),
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
  digestStringAsync: async (_algorithm, value) => crypto.createHash("sha256").update(value).digest("hex"),
};

import { CryptoDigestAlgorithm, digestStringAsync } from "expo-crypto";
import { batchBody, canonicalJSON, geometryCanonical, validateBatch, EnvironmentalBatch } from "../backend/src/contracts/environmental";
import type { Trail } from "../types";

export const environmentalGeometryHash = (trail: Trail) =>
  digestStringAsync(CryptoDigestAlgorithm.SHA256, geometryCanonical(trail));

export const verifiedEnvironmentalBatch = async (raw: unknown, trail: Trail): Promise<EnvironmentalBatch> => {
  const hash = await environmentalGeometryHash(trail);
  const batch = validateBatch(raw, trail.id, hash);
  const checksum = await digestStringAsync(CryptoDigestAlgorithm.SHA256, canonicalJSON(batchBody(batch)));
  if (checksum !== batch.payload_sha256) throw new Error("environmental-checksum-mismatch");
  return batch;
};

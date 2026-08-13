const personalFieldPatterns = [
  /name/i,
  /nombre/i,
  /email/i,
  /mail/i,
  /phone/i,
  /telefono/i,
  /dni/i,
  /document/i,
  /user.?id/i,
  /session.?id/i,
  /exact.?lat/i,
  /exact.?lng/i,
  /exact.?lon/i,
  /location/i,
  /ubicacion/i,
  /address/i,
  /direccion/i,
];

export const isPersonalTrainingField = (field: string) => {
  return personalFieldPatterns.some((pattern) => pattern.test(field));
};

export const assertNoPersonalTrainingFields = (fields: string[]) => {
  const rejectedFields = fields.filter(isPersonalTrainingField);

  if (rejectedFields.length > 0) {
    throw new Error(
      `Dataset contains personal or exact-location fields: ${rejectedFields.join(", ")}`
    );
  }
};

export const anonymizeTrainingRow = <T extends Record<string, unknown>>(row: T) => {
  return Object.fromEntries(
    Object.entries(row).filter(([field]) => !isPersonalTrainingField(field))
  );
};

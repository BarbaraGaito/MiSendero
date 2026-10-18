const fs = require('node:fs');
const { randomBytes } = require('node:crypto');
const { validateServerSecrets, databaseOptions } = require('../src/securityConfig');
const { validateReportPosition } = require('../src/reportPrivacy');

test('production rejects weak/missing signing configuration without echoing values',()=>{
  expect(()=>validateServerSecrets({NODE_ENV:'production',JWT_SECRET:'fixture-weak'})).toThrow('política');
  expect(()=>validateServerSecrets({NODE_ENV:'production',JWT_SECRET:randomBytes(48).toString('hex')})).toThrow('privacidad');
  expect(()=>validateServerSecrets({NODE_ENV:'production',JWT_SECRET:randomBytes(48).toString('hex'),PRIVACY_CONTACT_URL:'mailto:privacy@example.test'})).not.toThrow();
});
test('PostgreSQL production config fails closed and DSN cannot replace CA verification',()=>{
  expect(()=>databaseOptions({NODE_ENV:'production'})).toThrow('PGSSLROOTCERT');
  const read=jest.spyOn(fs,'readFileSync').mockReturnValue('SYNTHETIC-CA');
  try {
    expect(()=>databaseOptions({NODE_ENV:'production',PGSSLROOTCERT:'fixture',DATABASE_URL:'postgres://example.test/db?sslmode=require'})).toThrow('permisivo');
    const options=databaseOptions({NODE_ENV:'production',PGSSLROOTCERT:'fixture',DATABASE_URL:'postgres://example.test/db?sslmode=verify-full&sslrootcert=ignored&uselibpqcompat=true'});
    expect(options.ssl).toEqual({ca:'SYNTHETIC-CA',rejectUnauthorized:true});
    expect(options.connectionString).not.toMatch(/sslmode|sslrootcert|uselibpqcompat/);
  } finally {read.mockRestore();}
});
test('report validation uses the real latitude-longitude order and ignores inflated client accuracy',()=>{
  const trail={route_coordinates:[[-41,-71],[-41.01,-71]]};
  expect(validateReportPosition(trail,{latitude:-41.005,longitude:-71.0001})).toBe(true);
  expect(validateReportPosition(trail,{latitude:-41.005,longitude:-70,accuracy_meters:10000000})).toBe(false);
  expect(validateReportPosition(trail,{latitude:-41})).toBe(false);
  expect(validateReportPosition({route_coordinates:null},{latitude:-41,longitude:-71})).toBe(false);
});

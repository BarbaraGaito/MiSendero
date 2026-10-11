CREATE TABLE IF NOT EXISTS national_parks (
  slug TEXT PRIMARY KEY,
  profile JSONB NOT NULL
);
ALTER TABLE trails ADD COLUMN IF NOT EXISTS national_park_slug TEXT REFERENCES national_parks(slug);

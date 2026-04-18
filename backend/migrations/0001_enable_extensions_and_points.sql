CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.points (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key text NOT NULL UNIQUE,
    satellite text NOT NULL,
    version_tag text NULL,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    acquisition_time timestamptz NOT NULL,
    ingest_time timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    geom geometry(Point, 4326) NOT NULL,
    confidence text NULL,
    frp double precision NULL,
    bright_ti4 double precision NULL,
    bright_ti5 double precision NULL,
    scan double precision NULL,
    track double precision NULL,
    daynight text NULL
);

CREATE INDEX IF NOT EXISTS points_acquisition_time_idx
    ON public.points (acquisition_time);

CREATE INDEX IF NOT EXISTS points_geom_gix
    ON public.points
    USING GIST (geom);

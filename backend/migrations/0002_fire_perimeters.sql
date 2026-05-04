CREATE TABLE IF NOT EXISTS public.fire_perimeters (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    first_detection_time timestamptz NOT NULL,
    latest_detection_time timestamptz NOT NULL,
    detection_count integer NOT NULL,
    merged boolean NOT NULL DEFAULT FALSE,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    centroid geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.fire_perimeter_points (
    fire_perimeter_id uuid NOT NULL,
    point_source_key text NOT NULL,
    linked_at timestamptz NOT NULL,
    PRIMARY KEY (fire_perimeter_id, point_source_key),
    CONSTRAINT fire_perimeter_points_fire_perimeter_id_fkey
        FOREIGN KEY (fire_perimeter_id)
        REFERENCES public.fire_perimeters (id),
    CONSTRAINT fire_perimeter_points_point_source_key_fkey
        FOREIGN KEY (point_source_key)
        REFERENCES public.points (source_key)
);

-- Spatial lookups drive merge-candidate selection and map queries.
CREATE INDEX IF NOT EXISTS fire_perimeters_geom_gix
    ON public.fire_perimeters
    USING GIST (geom);

CREATE INDEX IF NOT EXISTS fire_perimeters_centroid_gix
    ON public.fire_perimeters
    USING GIST (centroid);

CREATE INDEX IF NOT EXISTS fire_perimeters_updated_at_idx
    ON public.fire_perimeters (updated_at);

CREATE INDEX IF NOT EXISTS fire_perimeter_points_point_source_key_idx
    ON public.fire_perimeter_points (point_source_key);

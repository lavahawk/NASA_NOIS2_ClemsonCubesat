from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta, datetime
import logging
import math
from typing import Protocol

from .config import WorkerConfig
from .models import NormalizedPoint, PerimeterCluster, PerimeterCycleSummary
from .storage import ConnectionFactory, _managed_connection

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
CONNECTED_HULL_TARGET_PERCENT = 0.99


class FirePerimeterStore(Protocol):
    def filter_unlinked_point_keys(self, point_source_keys: Sequence[str]) -> set[str]:
        raise NotImplementedError

    def find_merge_candidates(
        self,
        point_source_keys: Sequence[str],
        *,
        cycle_time: datetime,
        active_fire_window_days: int,
        merge_threshold_km: float,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> list[str]:
        raise NotImplementedError

    def create_perimeter_from_points(
        self,
        point_source_keys: Sequence[str],
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        raise NotImplementedError

    def merge_points_into_perimeter(
        self,
        perimeter_id: str,
        point_source_keys: Sequence[str],
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        raise NotImplementedError

    def consolidate_perimeters(
        self,
        perimeter_ids: Sequence[str],
        point_source_keys: Sequence[str],
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        raise NotImplementedError


class FirePerimeterGenerator:
    def __init__(self, config: WorkerConfig, store: FirePerimeterStore) -> None:
        self._config = config
        self._store = store

    def process_cycle(
        self,
        points: Sequence[NormalizedPoint],
        *,
        cycle_time: datetime,
    ) -> dict[str, int]:
        eligible_points = _filter_eligible_points(points)
        if not eligible_points:
            return _summary_to_dict(PerimeterCycleSummary())

        # Only brand-new perimeter points should affect active fire geometry.
        unlinked_keys = self._store.filter_unlinked_point_keys(
            [point.source_key for point in eligible_points]
        )
        if not unlinked_keys:
            return _summary_to_dict(
                PerimeterCycleSummary(eligible_points=0, clusters=0)
            )

        cycle_points = [
            point for point in eligible_points if point.source_key in unlinked_keys
        ]
        clusters = build_clusters(
            cycle_points,
            cluster_threshold_km=self._config.perimeter_cluster_threshold_km,
        )

        summary = PerimeterCycleSummary(
            eligible_points=len(cycle_points),
            clusters=len(clusters),
        )
        for cluster in clusters:
            try:
                candidate_ids = self._store.find_merge_candidates(
                    cluster.point_source_keys,
                    cycle_time=cycle_time,
                    active_fire_window_days=self._config.active_fire_window_days,
                    merge_threshold_km=self._config.perimeter_merge_threshold_km,
                    point_buffer_meters=self._config.perimeter_point_buffer_meters,
                    perimeter_smoothing_meters=self._config.perimeter_smoothing_meters,
                )
                if not candidate_ids:
                    self._store.create_perimeter_from_points(
                        cluster.point_source_keys,
                        cycle_time=cycle_time,
                        point_buffer_meters=self._config.perimeter_point_buffer_meters,
                        perimeter_smoothing_meters=self._config.perimeter_smoothing_meters,
                    )
                    summary = replace(summary, created=summary.created + 1)
                elif len(candidate_ids) == 1:
                    self._store.merge_points_into_perimeter(
                        candidate_ids[0],
                        cluster.point_source_keys,
                        cycle_time=cycle_time,
                        point_buffer_meters=self._config.perimeter_point_buffer_meters,
                        perimeter_smoothing_meters=self._config.perimeter_smoothing_meters,
                    )
                    summary = replace(summary, updated=summary.updated + 1)
                else:
                    self._store.consolidate_perimeters(
                        candidate_ids,
                        cluster.point_source_keys,
                        cycle_time=cycle_time,
                        point_buffer_meters=self._config.perimeter_point_buffer_meters,
                        perimeter_smoothing_meters=self._config.perimeter_smoothing_meters,
                    )
                    summary = replace(summary, consolidated=summary.consolidated + 1)
            except Exception:
                # Cluster failures should not break the underlying point-ingestion cycle.
                logger.exception(
                    "Failed to process perimeter cluster for points %s",
                    cluster.point_source_keys,
                )
                summary = replace(summary, skipped=summary.skipped + 1)

        return _summary_to_dict(summary)


class PostgresFirePerimeterStore(FirePerimeterStore):
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def filter_unlinked_point_keys(self, point_source_keys: Sequence[str]) -> set[str]:
        normalized_keys = _unique_point_keys(point_source_keys)
        if not normalized_keys:
            return set()

        sql = """
        SELECT p.source_key
        FROM public.points AS p
        LEFT JOIN public.fire_perimeter_points AS fpp
            ON fpp.point_source_key = p.source_key
        WHERE p.source_key = ANY(%s)
          AND fpp.point_source_key IS NULL
        """
        with _managed_connection(self._connection_factory()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, (normalized_keys,))
                rows = cursor.fetchall()
        return {str(row[0]) for row in rows}

    def find_merge_candidates(
        self,
        point_source_keys: Sequence[str],
        *,
        cycle_time: datetime,
        active_fire_window_days: int,
        merge_threshold_km: float,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> list[str]:
        normalized_keys = _unique_point_keys(point_source_keys)
        if not normalized_keys:
            return []

        active_cutoff = cycle_time - timedelta(days=active_fire_window_days)
        sql = """
        WITH selected_points AS (
            SELECT geom
            FROM public.points
            WHERE source_key = ANY(%s)
        ),
        buffered_points AS (
            SELECT ST_Buffer(geom::geography, %s)::geometry AS geom
            FROM selected_points
        ),
        cluster_geom AS (
            SELECT ST_Multi(
                ST_CollectionExtract(
                    ST_Buffer(
                        ST_Buffer(
                            ST_CollectionExtract(
                                ST_ConcaveHull(
                                    ST_UnaryUnion(ST_Collect(geom)),
                                    %s,
                                    FALSE
                                ),
                                3
                            )::geography,
                            %s
                        )::geometry::geography,
                        -%s
                    )::geometry,
                    3
                )
            ) AS geom
            FROM buffered_points
        )
        SELECT fp.id::text
        FROM public.fire_perimeters AS fp
        CROSS JOIN cluster_geom AS cg
        WHERE fp.merged = FALSE
          AND fp.latest_detection_time >= %s
          AND ST_DWithin(
              fp.geom::geography,
              cg.geom::geography,
              %s
          )
        ORDER BY ST_Distance(fp.geom::geography, cg.geom::geography), fp.id
        """
        with _managed_connection(self._connection_factory()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        normalized_keys,
                        point_buffer_meters,
                        CONNECTED_HULL_TARGET_PERCENT,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        active_cutoff,
                        merge_threshold_km * 1000.0,
                    ),
                )
                rows = cursor.fetchall()
        return [str(row[0]) for row in rows]

    def create_perimeter_from_points(
        self,
        point_source_keys: Sequence[str],
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        normalized_keys = _unique_point_keys(point_source_keys)
        if not normalized_keys:
            return

        insert_sql = """
        WITH selected_points AS (
            SELECT source_key, acquisition_time, geom
            FROM public.points
            WHERE source_key = ANY(%s)
        ),
        buffered_points AS (
            SELECT ST_Buffer(geom::geography, %s)::geometry AS geom
            FROM selected_points
        ),
        cluster_stats AS (
            SELECT
                MIN(acquisition_time) AS first_detection_time,
                MAX(acquisition_time) AS latest_detection_time,
                COUNT(*)::integer AS detection_count,
                (
                    SELECT ST_Multi(
                        ST_CollectionExtract(
                            ST_Buffer(
                                ST_Buffer(
                                    ST_CollectionExtract(
                                        ST_ConcaveHull(
                                            ST_UnaryUnion(ST_Collect(geom)),
                                            %s,
                                            FALSE
                                        ),
                                        3
                                    )::geography,
                                    %s
                                )::geometry::geography,
                                -%s
                            )::geometry,
                            3
                        )
                    )
                    FROM buffered_points
                ) AS geom
            FROM selected_points
        )
        INSERT INTO public.fire_perimeters (
            created_at,
            updated_at,
            first_detection_time,
            latest_detection_time,
            detection_count,
            merged,
            geom,
            centroid
        )
        SELECT
            %s,
            %s,
            first_detection_time,
            latest_detection_time,
            detection_count,
            FALSE,
            geom,
            ST_Centroid(geom)
        FROM cluster_stats
        RETURNING id::text
        """
        link_sql = """
        INSERT INTO public.fire_perimeter_points (
            fire_perimeter_id,
            point_source_key,
            linked_at
        )
        SELECT %s, p.source_key, %s
        FROM public.points AS p
        WHERE p.source_key = ANY(%s)
        ON CONFLICT (fire_perimeter_id, point_source_key) DO NOTHING
        """
        with _managed_connection(self._connection_factory()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    insert_sql,
                    (
                        normalized_keys,
                        point_buffer_meters,
                        CONNECTED_HULL_TARGET_PERCENT,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        cycle_time,
                        cycle_time,
                    ),
                )
                perimeter_id = str(cursor.fetchone()[0])
                cursor.execute(link_sql, (perimeter_id, cycle_time, normalized_keys))
            connection.commit()

    def merge_points_into_perimeter(
        self,
        perimeter_id: str,
        point_source_keys: Sequence[str],
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        normalized_keys = _unique_point_keys(point_source_keys)
        if not normalized_keys:
            return

        update_sql = """
        WITH selected_points AS (
            SELECT source_key, acquisition_time, geom
            FROM public.points
            WHERE source_key = ANY(%s)
        ),
        buffered_points AS (
            SELECT ST_Buffer(geom::geography, %s)::geometry AS geom
            FROM selected_points
        ),
        cluster_stats AS (
            SELECT
                MAX(acquisition_time) AS latest_detection_time,
                COUNT(*)::integer AS detection_count,
                (
                    SELECT ST_Multi(
                        ST_CollectionExtract(
                            ST_Buffer(
                                ST_Buffer(
                                    ST_CollectionExtract(
                                        ST_ConcaveHull(
                                            ST_UnaryUnion(ST_Collect(geom)),
                                            %s,
                                            FALSE
                                        ),
                                        3
                                    )::geography,
                                    %s
                                )::geometry::geography,
                                -%s
                            )::geometry,
                            3
                        )
                    )
                    FROM buffered_points
                ) AS geom
            FROM selected_points
        )
        UPDATE public.fire_perimeters AS fp
        SET geom = ST_Multi(
                ST_CollectionExtract(
                    ST_Buffer(
                        ST_Buffer(
                            ST_CollectionExtract(
                                ST_ConcaveHull(
                                    ST_UnaryUnion(ST_Collect(fp.geom, cs.geom)),
                                    %s,
                                    FALSE
                                ),
                                3
                            )::geography,
                            %s
                        )::geometry::geography,
                        -%s
                    )::geometry,
                    3
                )
            ),
            centroid = ST_Centroid(
                ST_Multi(
                    ST_CollectionExtract(
                        ST_Buffer(
                            ST_Buffer(
                                ST_CollectionExtract(
                                    ST_ConcaveHull(
                                        ST_UnaryUnion(ST_Collect(fp.geom, cs.geom)),
                                        %s,
                                        FALSE
                                    ),
                                    3
                                )::geography,
                                %s
                            )::geometry::geography,
                            -%s
                        )::geometry,
                        3
                    )
                )
            ),
            updated_at = %s,
            latest_detection_time = GREATEST(fp.latest_detection_time, cs.latest_detection_time),
            detection_count = fp.detection_count + cs.detection_count
        FROM cluster_stats AS cs
        WHERE fp.id = %s
        """
        link_sql = """
        INSERT INTO public.fire_perimeter_points (
            fire_perimeter_id,
            point_source_key,
            linked_at
        )
        SELECT %s, p.source_key, %s
        FROM public.points AS p
        WHERE p.source_key = ANY(%s)
        ON CONFLICT (fire_perimeter_id, point_source_key) DO NOTHING
        """
        with _managed_connection(self._connection_factory()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    update_sql,
                    (
                        normalized_keys,
                        point_buffer_meters,
                        CONNECTED_HULL_TARGET_PERCENT,
                        CONNECTED_HULL_TARGET_PERCENT,
                        CONNECTED_HULL_TARGET_PERCENT,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        cycle_time,
                        perimeter_id,
                    ),
                )
                cursor.execute(link_sql, (perimeter_id, cycle_time, normalized_keys))
            connection.commit()

    def consolidate_perimeters(
        self,
        perimeter_ids: Sequence[str],
        point_source_keys: Sequence[str],
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        normalized_perimeter_ids = _unique_ids(perimeter_ids)
        normalized_keys = _unique_point_keys(point_source_keys)
        if not normalized_perimeter_ids or not normalized_keys:
            return

        insert_sql = """
        WITH inherited_points AS (
            SELECT DISTINCT point_source_key
            FROM public.fire_perimeter_points
            WHERE fire_perimeter_id = ANY(%s)
        ),
        cluster_points AS (
            SELECT source_key AS point_source_key, geom
            FROM public.points
            WHERE source_key = ANY(%s)
        ),
        buffered_cluster_points AS (
            SELECT ST_Buffer(geom::geography, %s)::geometry AS geom
            FROM cluster_points
        ),
        candidate_union AS (
            SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
            FROM public.fire_perimeters
            WHERE id = ANY(%s)
        ),
        cluster_union AS (
            SELECT ST_Multi(
                ST_CollectionExtract(
                    ST_Buffer(
                        ST_Buffer(
                            ST_CollectionExtract(
                                ST_ConcaveHull(
                                    ST_UnaryUnion(ST_Collect(geom)),
                                    %s,
                                    FALSE
                                ),
                                3
                            )::geography,
                            %s
                        )::geometry::geography,
                        -%s
                    )::geometry,
                    3
                )
            ) AS geom
            FROM buffered_cluster_points
        ),
        combined_geom AS (
            SELECT ST_Multi(
                ST_CollectionExtract(
                    ST_Buffer(
                        ST_Buffer(
                            ST_CollectionExtract(
                                ST_ConcaveHull(
                                    ST_UnaryUnion(ST_Collect(cu.geom, clu.geom)),
                                    %s,
                                    FALSE
                                ),
                                3
                            )::geography,
                            %s
                        )::geometry::geography,
                        -%s
                    )::geometry,
                    3
                )
            ) AS geom
            FROM candidate_union AS cu
            CROSS JOIN cluster_union AS clu
        ),
        all_point_keys AS (
            SELECT point_source_key FROM inherited_points
            UNION
            SELECT point_source_key FROM cluster_points
        ),
        point_stats AS (
            SELECT
                MIN(p.acquisition_time) AS first_detection_time,
                MAX(p.acquisition_time) AS latest_detection_time,
                COUNT(*)::integer AS detection_count
            FROM public.points AS p
            JOIN all_point_keys AS apk
              ON apk.point_source_key = p.source_key
        )
        INSERT INTO public.fire_perimeters (
            created_at,
            updated_at,
            first_detection_time,
            latest_detection_time,
            detection_count,
            merged,
            geom,
            centroid
        )
        SELECT
            %s,
            %s,
            ps.first_detection_time,
            ps.latest_detection_time,
            ps.detection_count,
            FALSE,
            cg.geom,
            ST_Centroid(cg.geom)
        FROM point_stats AS ps
        CROSS JOIN combined_geom AS cg
        RETURNING id::text
        """
        link_sql = """
        WITH inherited_points AS (
            SELECT DISTINCT point_source_key
            FROM public.fire_perimeter_points
            WHERE fire_perimeter_id = ANY(%s)
        ),
        all_point_keys AS (
            SELECT point_source_key FROM inherited_points
            UNION
            SELECT source_key AS point_source_key
            FROM public.points
            WHERE source_key = ANY(%s)
        )
        INSERT INTO public.fire_perimeter_points (
            fire_perimeter_id,
            point_source_key,
            linked_at
        )
        SELECT %s, apk.point_source_key, %s
        FROM all_point_keys AS apk
        ON CONFLICT (fire_perimeter_id, point_source_key) DO NOTHING
        """
        mark_merged_sql = """
        UPDATE public.fire_perimeters
        SET merged = TRUE,
            updated_at = %s
        WHERE id = ANY(%s)
        """
        with _managed_connection(self._connection_factory()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    insert_sql,
                    (
                        normalized_perimeter_ids,
                        normalized_keys,
                        point_buffer_meters,
                        normalized_perimeter_ids,
                        CONNECTED_HULL_TARGET_PERCENT,
                        CONNECTED_HULL_TARGET_PERCENT,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        perimeter_smoothing_meters,
                        cycle_time,
                        cycle_time,
                    ),
                )
                perimeter_id = str(cursor.fetchone()[0])
                cursor.execute(
                    link_sql,
                    (
                        normalized_perimeter_ids,
                        normalized_keys,
                        perimeter_id,
                        cycle_time,
                    ),
                )
                cursor.execute(
                    mark_merged_sql,
                    (cycle_time, normalized_perimeter_ids),
                )
            connection.commit()


def build_clusters(
    points: Sequence[NormalizedPoint],
    *,
    cluster_threshold_km: float,
) -> list[PerimeterCluster]:
    if not points:
        return []

    labels = do_clustering_dbscan(
        [(point.latitude, point.longitude) for point in points],
        cluster_threshold_km,
    )

    grouped_points: dict[int, list[NormalizedPoint]] = defaultdict(list)
    for label, point in zip(labels, points, strict=False):
        grouped_points[label].append(point)

    clusters: list[PerimeterCluster] = []
    for grouped in grouped_points.values():
        grouped.sort(key=lambda point: point.source_key)
        clusters.append(
            PerimeterCluster(
                point_source_keys=tuple(point.source_key for point in grouped),
                first_detection_time=min(point.acquisition_time for point in grouped),
                sort_latitude=min(point.latitude for point in grouped),
                sort_longitude=min(point.longitude for point in grouped),
            )
        )

    # A stable order keeps iterative same-cycle merges deterministic.
    clusters.sort(
        key=lambda cluster: (
            cluster.first_detection_time,
            cluster.sort_latitude,
            cluster.sort_longitude,
            cluster.point_source_keys[0],
        )
    )
    return clusters


def do_clustering_dbscan(
    data: Sequence[tuple[float, float]],
    max_thresh_km: float,
) -> list[int]:
    if not data:
        return []

    if len(data) < 3:
        return list(range(len(data)))

    try:
        import numpy as np
        from sklearn.cluster import DBSCAN

        points = np.asarray(data, dtype=float)
        points_rad = np.radians(points)
        labels = DBSCAN(
            eps=max_thresh_km / EARTH_RADIUS_KM,
            min_samples=1,
            metric="haversine",
            algorithm="ball_tree",
        ).fit_predict(points_rad)
        return labels.astype(int).tolist()
    except ImportError:
        # With min_samples=1, DBSCAN reduces to connected components under eps-neighborhood.
        return _fallback_component_labels(data, max_thresh_km)


def _filter_eligible_points(points: Sequence[NormalizedPoint]) -> list[NormalizedPoint]:
    return [
        point
        for point in points
        if _normalize_confidence(point.confidence) in {"n", "h"}
    ]


def _normalize_confidence(confidence: str | None) -> str | None:
    if confidence is None:
        return None
    normalized = confidence.strip().lower()
    return normalized or None


def _fallback_component_labels(
    data: Sequence[tuple[float, float]],
    max_thresh_km: float,
) -> list[int]:
    labels = [-1] * len(data)
    current_label = 0
    for index in range(len(data)):
        if labels[index] != -1:
            continue
        labels[index] = current_label
        pending = [index]
        while pending:
            current_index = pending.pop()
            for neighbor_index in range(len(data)):
                if labels[neighbor_index] != -1:
                    continue
                if (
                    _haversine_km(data[current_index], data[neighbor_index])
                    <= max_thresh_km
                ):
                    labels[neighbor_index] = current_label
                    pending.append(neighbor_index)
        current_label += 1
    return labels


def _haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1 = left
    lat2, lon2 = right
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(haversine))


def _summary_to_dict(summary: PerimeterCycleSummary) -> dict[str, int]:
    return {
        "perimeter_points_eligible": summary.eligible_points,
        "perimeter_clusters": summary.clusters,
        "perimeters_created": summary.created,
        "perimeters_updated": summary.updated,
        "perimeters_consolidated": summary.consolidated,
        "perimeter_clusters_skipped": summary.skipped,
    }


def _unique_point_keys(point_source_keys: Sequence[str]) -> list[str]:
    return _unique_ids(point_source_keys)


def _unique_ids(values: Sequence[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values

from __future__ import annotations

from datetime import UTC, datetime
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from api_service.app import create_app
from api_service.config import ApiConfig
from api_service.cursor import encode_cursor
from api_service.models import (
    BBox,
    CursorBoundary,
    PerimeterRecord,
    PerimetersQuery,
    PointRecord,
    PointsPage,
    PointsQuery,
)


class FakePointsRepository:
    def __init__(self, page: PointsPage | None = None) -> None:
        self.page = page or PointsPage(records=[], has_more=False, next_cursor=None)
        self.last_query: PointsQuery | None = None
        self.last_page_size: int | None = None

    def fetch_points(self, query: PointsQuery, *, page_size: int) -> PointsPage:
        self.last_query = query
        self.last_page_size = page_size
        return self.page


class FakePerimetersRepository:
    def __init__(self, records: list[PerimeterRecord] | None = None) -> None:
        self.records = records or []
        self.last_query: PerimetersQuery | None = None

    def fetch_perimeters(self, query: PerimetersQuery) -> list[PerimeterRecord]:
        self.last_query = query
        return self.records


def sample_record(
    *,
    acquisition_time: datetime = datetime(2026, 4, 16, 15, 30, tzinfo=UTC),
    source_key: str = "36.35788|-114.91005|2026-04-16T15:30+00:00|VIIRS_NOAA20_NRT",
) -> PointRecord:
    return PointRecord(
        id=uuid4(),
        source_key=source_key,
        satellite="VIIRS_NOAA20_NRT",
        version_tag="2.0NRT",
        acquisition_time=acquisition_time,
        ingest_time=datetime(2026, 4, 16, 15, 35, tzinfo=UTC),
        created_at=datetime(2026, 4, 16, 15, 35, tzinfo=UTC),
        updated_at=datetime(2026, 4, 16, 15, 35, tzinfo=UTC),
        latitude=36.35788,
        longitude=-114.91005,
        confidence="n",
        frp=0.68,
        bright_ti4=304.68,
        bright_ti5=284.34,
        scan=0.39,
        track=0.44,
        daynight="N",
    )


def sample_perimeter_record(*, merged: bool = False) -> PerimeterRecord:
    return PerimeterRecord(
        id=uuid4(),
        created_at=datetime(2026, 4, 16, 15, 35, tzinfo=UTC),
        updated_at=datetime(2026, 4, 17, 15, 35, tzinfo=UTC),
        first_detection_time=datetime(2026, 4, 16, 15, 30, tzinfo=UTC),
        latest_detection_time=datetime(2026, 4, 17, 16, 15, tzinfo=UTC),
        detection_count=4,
        merged=merged,
        geometry={
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [-114.92, 36.35],
                        [-114.90, 36.35],
                        [-114.90, 36.37],
                        [-114.92, 36.37],
                        [-114.92, 36.35],
                    ]
                ]
            ],
        },
    )


class FastApiTests(unittest.TestCase):
    def _build_client(
        self,
        repository: FakePointsRepository | None = None,
        *,
        perimeters_repository: FakePerimetersRepository | None = None,
    ) -> TestClient:
        app = create_app(
            ApiConfig(
                database_dsn="postgresql://unused",
                page_size=2,
                max_time_range_days=10,
                allowed_origins=("http://localhost:3000",),
            ),
            repository=repository or FakePointsRepository(),
            perimeters_repository=perimeters_repository or FakePerimetersRepository(),
        )
        return TestClient(app)

    def test_get_points_returns_geojson_wrapper_and_pagination(self) -> None:
        record = sample_record()
        page = PointsPage(
            records=[record],
            has_more=True,
            next_cursor=CursorBoundary(
                acquisition_time=record.acquisition_time,
                source_key=record.source_key,
            ),
        )
        repository = FakePointsRepository(page)
        client = self._build_client(repository)

        response = client.get(
            "/v1/points",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-16T23:59:00Z",
                "bbox": "-125,30,-110,40",
                "satellite": "VIIRS_NOAA20_NRT",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["has_more"])
        self.assertIsInstance(body["next_cursor"], str)
        self.assertEqual(body["points"]["type"], "FeatureCollection")
        self.assertEqual(len(body["points"]["features"]), 1)
        feature = body["points"]["features"][0]
        self.assertEqual(feature["geometry"]["type"], "Point")
        self.assertEqual(feature["geometry"]["coordinates"], [-114.91005, 36.35788])
        self.assertEqual(feature["properties"]["source_key"], record.source_key)
        self.assertEqual(feature["properties"]["satellite"], "VIIRS_NOAA20_NRT")
        self.assertEqual(repository.last_page_size, 2)
        self.assertEqual(repository.last_query.filters["satellite"], "VIIRS_NOAA20_NRT")

    def test_invalid_bbox_returns_400(self) -> None:
        client = self._build_client(FakePointsRepository())

        response = client.get(
            "/v1/points",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-16T23:59:00Z",
                "bbox": "-125,30,-110",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["parameter"], "bbox")

    def test_unsupported_parameter_returns_400(self) -> None:
        client = self._build_client(FakePointsRepository())

        response = client.get(
            "/v1/points",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-16T23:59:00Z",
                "bbox": "-125,30,-110,40",
                "foo": "bar",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["parameter"], "foo")

    def test_cursor_mismatch_returns_400(self) -> None:
        query = PointsQuery(
            start_time=datetime(2026, 4, 16, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 16, 23, 59, tzinfo=UTC),
            bbox=BBox(west=-125, south=30, east=-110, north=40),
            filters={"satellite": "VIIRS_NOAA20_NRT"},
        )
        cursor = encode_cursor(
            query,
            CursorBoundary(
                acquisition_time=datetime(2026, 4, 16, 12, 0, tzinfo=UTC),
                source_key="cursor-key",
            ),
        )

        client = self._build_client(FakePointsRepository())
        response = client.get(
            "/v1/points",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-16T23:59:00Z",
                "bbox": "-125,30,-110,40",
                "satellite": "VIIRS_SNPP_NRT",
                "cursor": cursor,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["parameter"], "cursor")

    def test_valid_cursor_is_decoded_into_query_boundary(self) -> None:
        base_query = PointsQuery(
            start_time=datetime(2026, 4, 16, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 16, 23, 59, tzinfo=UTC),
            bbox=BBox(west=-125, south=30, east=-110, north=40),
            filters={"satellite": "VIIRS_NOAA20_NRT"},
        )
        boundary = CursorBoundary(
            acquisition_time=datetime(2026, 4, 16, 12, 0, tzinfo=UTC),
            source_key="cursor-key",
        )
        repository = FakePointsRepository()
        client = self._build_client(repository)

        response = client.get(
            "/v1/points",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-16T23:59:00Z",
                "bbox": "-125,30,-110,40",
                "satellite": "VIIRS_NOAA20_NRT",
                "cursor": encode_cursor(base_query, boundary),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(repository.last_query)
        self.assertEqual(repository.last_query.cursor, boundary)

    def test_cors_headers_are_returned_for_allowed_origin(self) -> None:
        client = self._build_client(FakePointsRepository())

        response = client.get(
            "/v1/points",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-16T23:59:00Z",
                "bbox": "-125,30,-110,40",
            },
            headers={"Origin": "http://localhost:3000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")

    def test_get_perimeters_returns_feature_collection(self) -> None:
        repository = FakePerimetersRepository([sample_perimeter_record()])
        client = self._build_client(perimeters_repository=repository)

        response = client.get(
            "/v1/perimeters",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-20T23:59:00Z",
                "bbox": "-125,30,-110,40",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["type"], "FeatureCollection")
        self.assertEqual(len(body["features"]), 1)
        self.assertEqual(body["features"][0]["geometry"]["type"], "MultiPolygon")
        self.assertFalse(repository.last_query.merged)

    def test_get_perimeters_accepts_merged_true_filter(self) -> None:
        repository = FakePerimetersRepository()
        client = self._build_client(perimeters_repository=repository)

        response = client.get(
            "/v1/perimeters",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-20T23:59:00Z",
                "bbox": "-125,30,-110,40",
                "merged": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(repository.last_query.merged)

    def test_get_perimeters_rejects_invalid_merged_value(self) -> None:
        client = self._build_client()

        response = client.get(
            "/v1/perimeters",
            params={
                "start_time": "2026-04-16T00:00:00Z",
                "end_time": "2026-04-20T23:59:00Z",
                "bbox": "-125,30,-110,40",
                "merged": "maybe",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["parameter"], "merged")


if __name__ == "__main__":
    unittest.main()

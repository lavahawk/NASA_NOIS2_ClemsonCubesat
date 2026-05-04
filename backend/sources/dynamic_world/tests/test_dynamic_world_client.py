from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import dynamic_world as dw
from dynamic_world import client as client_module


class DynamicWorldClientTests(unittest.TestCase):
    def test_single_query_day_normalization_uses_utc_day(self) -> None:
        client = dw.DynamicWorldClient()
        normalized = client._normalize_day("2024-05-04T23:30:00-05:00")
        self.assertEqual(normalized.isoformat(), "2024-05-05")

    def test_batch_query_interval_derivation(self) -> None:
        client = dw.DynamicWorldClient()
        start, end = client._derive_batch_interval(date(2024, 5, 4), 7)
        self.assertEqual(start.isoformat(), "2024-04-27")
        self.assertEqual(end.isoformat(), "2024-05-12")

    def test_rejects_empty_batch_requests(self) -> None:
        client = dw.DynamicWorldClient()
        client._initialized = True
        with self.assertRaises(dw.DynamicWorldEmptyBatchError):
            client.get_land_cover_batch(when="2024-05-04", requests=[])

    def test_initializes_with_explicit_credentials_and_project(self) -> None:
        fake_ee = Mock()
        credentials = object()
        with patch.object(client_module, "ee", fake_ee):
            client = dw.DynamicWorldClient(credentials=credentials, project="demo-project")
            client._initialize_ee()
        fake_ee.Initialize.assert_called_once_with(
            credentials=credentials, project="demo-project"
        )

    def test_initializes_with_ambient_defaults_when_no_credentials(self) -> None:
        fake_ee = Mock()
        with patch.object(client_module, "ee", fake_ee):
            client = dw.DynamicWorldClient()
            client._initialize_ee()
        fake_ee.Initialize.assert_called_once_with()

    def test_authentication_failures_raise_typed_error(self) -> None:
        fake_ee = Mock()
        fake_ee.Initialize.side_effect = RuntimeError("boom")
        with patch.object(client_module, "ee", fake_ee):
            client = dw.DynamicWorldClient()
            with self.assertRaises(dw.DynamicWorldAuthenticationError):
                client._initialize_ee()

    def test_exact_day_image_selection_prefers_earliest_time(self) -> None:
        client = dw.DynamicWorldClient()
        requested = date(2024, 5, 4)
        metadata = [
            {
                "system_index": "late",
                "system_id": "late",
                "time_start": 20,
                "date": requested,
                "date_str": requested.isoformat(),
            },
            {
                "system_index": "early",
                "system_id": "early",
                "time_start": 10,
                "date": requested,
                "date_str": requested.isoformat(),
            },
        ]
        metadata.sort(key=lambda item: item["time_start"])
        selected = client._resolve_image_for_day(requested, metadata, 7)
        self.assertEqual(selected["system_index"], "early")

    def test_nearest_scene_fallback_prefers_shortest_distance_then_earliest_time(self) -> None:
        client = dw.DynamicWorldClient()
        requested = date(2024, 5, 4)
        metadata = [
            {
                "system_index": "two-days-away",
                "system_id": "two-days-away",
                "time_start": 100,
                "date": date(2024, 5, 6),
                "date_str": "2024-05-06",
            },
            {
                "system_index": "one-day-late",
                "system_id": "one-day-late",
                "time_start": 50,
                "date": date(2024, 5, 5),
                "date_str": "2024-05-05",
            },
            {
                "system_index": "one-day-early",
                "system_id": "one-day-early",
                "time_start": 40,
                "date": date(2024, 5, 3),
                "date_str": "2024-05-03",
            },
        ]
        selected = client._resolve_image_for_day(requested, metadata, 7)
        self.assertEqual(selected["system_index"], "one-day-early")

    def test_no_data_when_no_image_is_within_tolerance(self) -> None:
        client = dw.DynamicWorldClient()
        requested = date(2024, 5, 4)
        metadata = [
            {
                "system_index": "far",
                "system_id": "far",
                "time_start": 10,
                "date": date(2024, 5, 20),
                "date_str": "2024-05-20",
            }
        ]
        self.assertIsNone(client._resolve_image_for_day(requested, metadata, 3))

    def test_no_data_when_sampled_pixel_is_null(self) -> None:
        client = dw.DynamicWorldClient()
        result = client._format_result(
            longitude=-82.0,
            latitude=34.0,
            requested_day=date(2024, 5, 4),
            selected_metadata={
                "system_index": "img",
                "system_id": "img",
                "time_start": 10,
                "date": date(2024, 5, 4),
                "date_str": "2024-05-04",
            },
            sampled_values=None,
            include_probabilities=True,
            min_top1_probability=None,
        )
        self.assertIsNone(result.matched_image_date)
        self.assertIsNone(result.label_name)

    def test_label_mapping_and_low_confidence_flag(self) -> None:
        client = dw.DynamicWorldClient()
        result = client._format_result(
            longitude=-82.0,
            latitude=34.0,
            requested_day=date(2024, 5, 4),
            selected_metadata={
                "system_index": "img",
                "system_id": "img",
                "time_start": 10,
                "date": date(2024, 5, 4),
                "date_str": "2024-05-04",
            },
            sampled_values={
                "label": 4,
                "water": 0.01,
                "trees": 0.05,
                "grass": 0.08,
                "flooded_vegetation": 0.02,
                "crops": 0.4,
                "shrub_and_scrub": 0.14,
                "built": 0.12,
                "bare": 0.1,
                "snow_and_ice": 0.08,
            },
            include_probabilities=True,
            min_top1_probability=0.5,
        )
        self.assertEqual(result.label_name, dw.DynamicWorldLabel.CROPS)
        self.assertEqual(result.top1_probability, 0.4)
        self.assertTrue(result.is_low_confidence)
        self.assertIsNotNone(result.probabilities)

    def test_metadata_cache_reuses_interval_result(self) -> None:
        client = dw.DynamicWorldClient(max_metadata_cache_size=2)
        collection = object()
        expected = [{"system_index": "a"}]
        fetcher = Mock(return_value=expected)
        client._fetch_interval_metadata = fetcher  # type: ignore[method-assign]

        result_one = client._get_interval_metadata(
            date(2024, 5, 1), date(2024, 5, 10), collection
        )
        result_two = client._get_interval_metadata(
            date(2024, 5, 1), date(2024, 5, 10), collection
        )

        self.assertIs(result_one, expected)
        self.assertIs(result_two, expected)
        fetcher.assert_called_once_with(collection)

    def test_single_query_filters_collection_by_point_bounds(self) -> None:
        class FakeClient(dw.DynamicWorldClient):
            def __init__(self) -> None:
                super().__init__()
                self.collection_geometry = None

            def _initialize_ee(self) -> None:
                self._initialized = True

            def _build_point(self, longitude: float, latitude: float) -> tuple[float, float]:
                return (longitude, latitude)

            def _get_collection_for_interval(
                self, start: date, end: date, geometry=None
            ) -> str:
                self.collection_geometry = geometry
                return "collection"

            def _get_interval_metadata(self, start: date, end: date, collection: str):
                return [
                    {
                        "system_index": "img-1",
                        "system_id": "img-1",
                        "time_start": 10,
                        "date": date(2025, 4, 20),
                        "date_str": "2025-04-20",
                    }
                ]

            def _get_image_from_collection(self, collection: str, system_index: str) -> str:
                return system_index

            def _sample_point(self, image: str, point: tuple[float, float]):
                return {
                    "label": 6,
                    "water": 0.01,
                    "trees": 0.02,
                    "grass": 0.02,
                    "flooded_vegetation": 0.01,
                    "crops": 0.03,
                    "shrub_and_scrub": 0.03,
                    "built": 0.8,
                    "bare": 0.05,
                    "snow_and_ice": 0.03,
                }

        client = FakeClient()
        result = client.get_land_cover(
            when="2025-04-20",
            longitude=-100.0,
            latitude=-45.0,
        )

        self.assertEqual(client.collection_geometry, (-100.0, -45.0))
        self.assertEqual(result.label_name, dw.DynamicWorldLabel.BUILT)

    def test_batch_sampling_uses_one_selected_image_and_preserves_order(self) -> None:
        class FakeClient(dw.DynamicWorldClient):
            def __init__(self) -> None:
                super().__init__()
                self.selected_images: list[str] = []

            def _initialize_ee(self) -> None:
                self._initialized = True

            def _get_collection_for_interval(self, start: date, end: date) -> str:
                return "collection"

            def _get_interval_metadata(self, start: date, end: date, collection: str):
                return [
                    {
                        "system_index": "img-1",
                        "system_id": "img-1",
                        "time_start": 10,
                        "date": date(2024, 5, 4),
                        "date_str": "2024-05-04",
                    }
                ]

            def _get_image_from_collection(self, collection: str, system_index: str) -> str:
                self.selected_images.append(system_index)
                return system_index

            def _sample_points(self, image: str, requests: list[dw.DynamicWorldPointRequest]):
                if image != "img-1":
                    raise AssertionError(f"expected img-1, got {image!r}")
                return [
                    {
                        "request_id": 1,
                        "label": 1,
                        "water": 0.01,
                        "trees": 0.7,
                        "grass": 0.03,
                        "flooded_vegetation": 0.01,
                        "crops": 0.05,
                        "shrub_and_scrub": 0.05,
                        "built": 0.1,
                        "bare": 0.03,
                        "snow_and_ice": 0.02,
                    },
                    {
                        "request_id": 0,
                        "label": 6,
                        "water": 0.01,
                        "trees": 0.02,
                        "grass": 0.02,
                        "flooded_vegetation": 0.01,
                        "crops": 0.03,
                        "shrub_and_scrub": 0.03,
                        "built": 0.8,
                        "bare": 0.05,
                        "snow_and_ice": 0.03,
                    },
                ]

        client = FakeClient()
        results = client.get_land_cover_batch(
            when=datetime(2024, 5, 4, 12, 0, tzinfo=timezone.utc),
            requests=[
                dw.DynamicWorldPointRequest(longitude=-82.12, latitude=34.67),
                dw.DynamicWorldPointRequest(longitude=-82.13, latitude=34.68),
            ],
            include_probabilities=False,
        )

        self.assertEqual(client.selected_images, ["img-1"])
        self.assertEqual(
            [result.label_name for result in results],
            [dw.DynamicWorldLabel.BUILT, dw.DynamicWorldLabel.TREES],
        )
        self.assertEqual([result.longitude for result in results], [-82.12, -82.13])


if __name__ == "__main__":
    unittest.main()

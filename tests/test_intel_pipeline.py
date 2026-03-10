# tests/test_intel_pipeline.py
"""Tests for intel_pipeline module.

All tests mock the database — no Oracle connection required.
"""

import json
from unittest.mock import MagicMock, patch

import numpy as np

from intel_pipeline import IntelligencePipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_BASE_MS = 1767571200000  # 2026-01-05T00:00:00Z (Monday)
_HOUR_MS = 3_600_000


def _make_event_row(lat, lon, timestamp_ms, report_type, region="madrid"):
    """Return a tuple matching the column order used by build_user_vectors."""
    return (lat, lon, timestamp_ms, report_type, region)


def _mock_cursor(rows=None, description=None, fetchone_val=None, fetchmany_batches=None):
    """Create a mock cursor with configurable behaviour."""
    cursor = MagicMock()
    if description is not None:
        cursor.description = description
    if rows is not None:
        cursor.fetchall.return_value = rows
    if fetchone_val is not None:
        cursor.fetchone.return_value = fetchone_val
    if fetchmany_batches is not None:
        cursor.fetchmany.side_effect = fetchmany_batches
    return cursor


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineInit:
    """IntelligencePipeline can be instantiated."""

    def test_init(self):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)
        assert pipeline.db is db


class TestBuildUserVectors:
    """build_user_vectors fetches events, builds vectors, and MERGEs into Oracle."""

    def test_processes_qualifying_users(self):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        # We need multiple db.execute calls to return different cursors.
        # Call sequence:
        #   1. MAX(cnt) query -> fetchone returns (500,)
        #   2. qualifying users query -> fetchall returns 1 user
        #   3. per-user events query -> fetchall returns events
        #   4. MERGE INTO upsert

        max_cursor = _mock_cursor(fetchone_val=(500,))

        user_rows = [("user_alpha", 25, "2026-01-05T08:00:00Z", "2026-02-05T18:00:00Z")]
        user_desc = [("USERNAME",), ("CNT",), ("FIRST_SEEN",), ("LAST_SEEN",)]
        users_cursor = _mock_cursor(rows=user_rows, description=user_desc)

        events = [
            _make_event_row(40.42, -3.70, _BASE_MS + i * _HOUR_MS, "POLICE") for i in range(25)
        ]
        events_desc = [
            ("LATITUDE",),
            ("LONGITUDE",),
            ("TIMESTAMP_MS",),
            ("REPORT_TYPE",),
            ("REGION",),
        ]
        events_cursor = _mock_cursor(rows=events, description=events_desc)

        merge_cursor = MagicMock()

        db.execute.side_effect = [max_cursor, users_cursor, events_cursor, merge_cursor]

        result = pipeline.build_user_vectors(min_events=20)

        assert result == 1
        # Should have called execute 4 times: max, users, events, merge
        assert db.execute.call_count == 4
        # The 4th call should be the MERGE INTO
        merge_call_sql = db.execute.call_args_list[3][0][0]
        assert "MERGE INTO user_behavioral_vectors" in merge_call_sql
        # commit should be called
        db.commit.assert_called()

    def test_skips_users_with_no_events(self):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        max_cursor = _mock_cursor(fetchone_val=(100,))
        user_rows = [("empty_user", 20, "2026-01-05T08:00:00Z", "2026-02-05T18:00:00Z")]
        user_desc = [("USERNAME",), ("CNT",), ("FIRST_SEEN",), ("LAST_SEEN",)]
        users_cursor = _mock_cursor(rows=user_rows, description=user_desc)

        # Return no events
        events_desc = [
            ("LATITUDE",),
            ("LONGITUDE",),
            ("TIMESTAMP_MS",),
            ("REPORT_TYPE",),
            ("REGION",),
        ]
        events_cursor = _mock_cursor(rows=[], description=events_desc)

        db.execute.side_effect = [max_cursor, users_cursor, events_cursor]

        result = pipeline.build_user_vectors(min_events=20)
        assert result == 0

    def test_returns_zero_when_no_qualifying_users(self):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        max_cursor = _mock_cursor(fetchone_val=(10,))
        users_cursor = _mock_cursor(
            rows=[],
            description=[("USERNAME",), ("CNT",), ("FIRST_SEEN",), ("LAST_SEEN",)],
        )

        db.execute.side_effect = [max_cursor, users_cursor]

        result = pipeline.build_user_vectors(min_events=20)
        assert result == 0


class TestRunRoutineInference:
    """run_routine_inference fetches vectorized users and upserts routines."""

    @patch("intel_pipeline.infer_routines")
    def test_processes_users_and_upserts(self, mock_infer):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        # First call: get usernames
        usernames_cursor = _mock_cursor(rows=[("user_a",), ("user_b",)])

        # For each user: fetch events, then MERGE per routine
        events_desc = [("LATITUDE",), ("LONGITUDE",), ("TIMESTAMP_MS",), ("REPORT_TYPE",)]
        events_a = [(40.42, -3.70, _BASE_MS + i * _HOUR_MS, "POLICE") for i in range(25)]
        events_cursor_a = _mock_cursor(rows=events_a, description=events_desc)

        events_b = [(41.38, 2.17, _BASE_MS + i * _HOUR_MS, "JAM") for i in range(30)]
        events_cursor_b = _mock_cursor(rows=events_b, description=events_desc)

        # infer_routines returns one routine per user
        mock_infer.side_effect = [
            {
                "HOME": {
                    "latitude": 40.42,
                    "longitude": -3.70,
                    "confidence": 0.9,
                    "typical_hours": [23, 0, 1],
                    "typical_days": [0, 1, 2],
                    "evidence_count": 15,
                }
            },
            {},  # user_b has no routines
        ]

        merge_cursor = MagicMock()

        # Sequence: usernames, events_a, merge_home, events_b
        db.execute.side_effect = [usernames_cursor, events_cursor_a, merge_cursor, events_cursor_b]

        result = pipeline.run_routine_inference(min_events=20)
        assert result == 2
        assert mock_infer.call_count == 2
        db.commit.assert_called()

    @patch("intel_pipeline.infer_routines")
    def test_returns_zero_when_no_vectorized_users(self, mock_infer):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        usernames_cursor = _mock_cursor(rows=[])
        db.execute.side_effect = [usernames_cursor]

        result = pipeline.run_routine_inference()
        assert result == 0
        mock_infer.assert_not_called()


class TestFindSimilarUsers:
    """find_similar_users uses Oracle VECTOR_DISTANCE."""

    def test_returns_empty_when_user_not_found(self):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        cursor = _mock_cursor(fetchone_val=None)
        db.execute.return_value = cursor

        result = pipeline.find_similar_users("nonexistent_user")
        assert result == []

    def test_returns_similar_users(self):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        # First query: get target vector
        vec = np.zeros(44).tolist()
        vector_cursor = _mock_cursor(fetchone_val=(vec,))

        # Second query: VECTOR_DISTANCE results
        similar_rows = [
            ("similar_user_1", 0.05),
            ("similar_user_2", 0.12),
        ]
        similar_desc = [("USERNAME",), ("DISTANCE",)]
        similar_cursor = _mock_cursor(rows=similar_rows, description=similar_desc)

        db.execute.side_effect = [vector_cursor, similar_cursor]

        result = pipeline.find_similar_users("target_user", top_k=2)
        assert len(result) == 2
        assert result[0]["username"] == "similar_user_1"
        assert result[0]["distance"] == 0.05
        assert result[1]["username"] == "similar_user_2"

    def test_queries_vector_distance(self):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        vec = np.zeros(44).tolist()
        vector_cursor = _mock_cursor(fetchone_val=(vec,))
        similar_cursor = _mock_cursor(rows=[], description=[("USERNAME",), ("DISTANCE",)])
        db.execute.side_effect = [vector_cursor, similar_cursor]

        pipeline.find_similar_users("some_user", top_k=5)

        # Second execute call should contain VECTOR_DISTANCE
        second_call_sql = db.execute.call_args_list[1][0][0]
        assert "VECTOR_DISTANCE" in second_call_sql


class TestBuildCooccurrenceGraph:
    """build_cooccurrence_graph fetches events and upserts edges."""

    @patch("intel_pipeline.find_cooccurrences")
    def test_calls_find_cooccurrences(self, mock_find):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        cols_desc = [("USERNAME",), ("LATITUDE",), ("LONGITUDE",), ("TIMESTAMP_MS",), ("REGION",)]
        # Return events in one fetchmany batch, then empty
        events_rows = [
            ("user_a", 40.42, -3.70, _BASE_MS, "madrid"),
            ("user_b", 40.42, -3.70, _BASE_MS + 1000, "madrid"),
        ]
        cursor = MagicMock()
        cursor.description = cols_desc
        cursor.fetchmany.side_effect = [events_rows, []]

        db.execute.return_value = cursor

        mock_find.return_value = [
            {
                "user_a": "user_a",
                "user_b": "user_b",
                "co_count": 5,
                "avg_distance_m": 100.0,
                "avg_time_gap_s": 60.0,
            },
        ]

        result = pipeline.build_cooccurrence_graph()
        assert result == 1
        mock_find.assert_called_once()
        db.commit.assert_called()

    @patch("intel_pipeline.find_cooccurrences")
    def test_no_edges_when_no_cooccurrences(self, mock_find):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        cursor = MagicMock()
        cursor.description = [
            ("USERNAME",),
            ("LATITUDE",),
            ("LONGITUDE",),
            ("TIMESTAMP_MS",),
            ("REGION",),
        ]
        cursor.fetchmany.side_effect = [[], []]
        db.execute.return_value = cursor

        mock_find.return_value = []

        result = pipeline.build_cooccurrence_graph()
        assert result == 0

    @patch("intel_pipeline.find_cooccurrences")
    def test_region_filter(self, mock_find):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        cursor = MagicMock()
        cursor.description = [
            ("USERNAME",),
            ("LATITUDE",),
            ("LONGITUDE",),
            ("TIMESTAMP_MS",),
            ("REGION",),
        ]
        cursor.fetchmany.side_effect = [[], []]
        db.execute.return_value = cursor

        mock_find.return_value = []

        pipeline.build_cooccurrence_graph(region="madrid")

        # The SQL should contain WHERE region = :1
        sql = db.execute.call_args_list[0][0][0]
        assert "WHERE region = :1" in sql


class TestGenerateUserDossier:
    """generate_user_dossier gathers intel and calls LLM."""

    def test_returns_none_when_user_not_found(self):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        cursor = MagicMock()
        cursor.description = [("USERNAME",), ("EVENT_COUNT",), ("REGION",)]
        cursor.fetchone.return_value = None
        db.execute.return_value = cursor

        result = pipeline.generate_user_dossier("ghost_user")
        assert result is None

    @patch("intel_pipeline.generate_dossier")
    def test_generates_and_stores_dossier(self, mock_gen):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        # Mock the user_behavioral_vectors query
        user_desc = [
            ("USERNAME",),
            ("REGION",),
            ("EVENT_COUNT",),
            ("FIRST_SEEN",),
            ("LAST_SEEN",),
            ("CENTROID_LAT",),
            ("CENTROID_LON",),
            ("GEO_SPREAD_KM",),
            ("HOUR_HISTOGRAM",),
            ("DOW_HISTOGRAM",),
            ("TYPE_DISTRIBUTION",),
            ("CADENCE_STATS",),
            ("BEHAVIOR_VECTOR",),
        ]
        user_row = (
            "test_user",
            "madrid",
            50,
            "2026-01-05T08:00:00Z",
            "2026-02-05T18:00:00Z",
            40.42,
            -3.70,
            1.5,
            json.dumps([0.0] * 24),
            json.dumps([0.0] * 7),
            json.dumps({"POLICE": 30, "JAM": 20}),
            json.dumps({"mean": 5.0, "std": 2.0, "median": 4.0}),
            [0.0] * 44,
        )
        user_cursor = MagicMock()
        user_cursor.description = user_desc
        user_cursor.fetchone.return_value = user_row

        # Mock the routines query
        routines_desc = [
            ("USERNAME",),
            ("ROUTINE_TYPE",),
            ("LATITUDE",),
            ("LONGITUDE",),
            ("CONFIDENCE",),
        ]
        routines_rows = [
            ("test_user", "HOME", 40.45, -3.69, 0.91),
        ]
        routines_cursor = MagicMock()
        routines_cursor.description = routines_desc
        routines_cursor.fetchall.return_value = routines_rows

        # Mock find_similar_users — we mock at the method level
        # (it makes its own db.execute calls so easier to patch at pipeline level)
        pipeline.find_similar_users = MagicMock(
            return_value=[
                {"username": "similar_1", "distance": 0.1},
            ]
        )

        # Mock co-occurrence partners query
        co_cursor = MagicMock()
        co_cursor.fetchall.return_value = [
            ("test_user", "partner_a", 7),
        ]

        # Mock the UPDATE call
        update_cursor = MagicMock()

        # Sequence: user vectors, routines, co-occurrences, update
        db.execute.side_effect = [user_cursor, routines_cursor, co_cursor, update_cursor]

        mock_gen.return_value = "Intelligence dossier for test_user..."

        result = pipeline.generate_user_dossier("test_user")

        assert result == "Intelligence dossier for test_user..."
        mock_gen.assert_called_once()
        # Verify the profile passed to generate_dossier
        profile_arg = mock_gen.call_args[0][0]
        assert profile_arg["username"] == "test_user"
        assert profile_arg["event_count"] == 50
        assert profile_arg["region"] == "madrid"
        # Verify dossier was stored
        db.commit.assert_called()

    @patch("intel_pipeline.generate_dossier")
    def test_does_not_store_when_llm_returns_none(self, mock_gen):
        db = MagicMock()
        pipeline = IntelligencePipeline(db)

        user_desc = [
            ("USERNAME",),
            ("REGION",),
            ("EVENT_COUNT",),
            ("FIRST_SEEN",),
            ("LAST_SEEN",),
            ("CENTROID_LAT",),
            ("CENTROID_LON",),
            ("GEO_SPREAD_KM",),
            ("HOUR_HISTOGRAM",),
            ("DOW_HISTOGRAM",),
            ("TYPE_DISTRIBUTION",),
            ("CADENCE_STATS",),
            ("BEHAVIOR_VECTOR",),
        ]
        user_row = (
            "test_user",
            "madrid",
            50,
            "2026-01-05T08:00:00Z",
            "2026-02-05T18:00:00Z",
            40.42,
            -3.70,
            1.5,
            json.dumps([0.0] * 24),
            json.dumps([0.0] * 7),
            json.dumps({"POLICE": 30}),
            json.dumps({"mean": 5.0, "std": 2.0, "median": 4.0}),
            [0.0] * 44,
        )
        user_cursor = MagicMock()
        user_cursor.description = user_desc
        user_cursor.fetchone.return_value = user_row

        routines_cursor = MagicMock()
        routines_cursor.description = [
            ("USERNAME",),
            ("ROUTINE_TYPE",),
            ("LATITUDE",),
            ("LONGITUDE",),
            ("CONFIDENCE",),
        ]
        routines_cursor.fetchall.return_value = []

        pipeline.find_similar_users = MagicMock(return_value=[])

        co_cursor = MagicMock()
        co_cursor.fetchall.return_value = []

        db.execute.side_effect = [user_cursor, routines_cursor, co_cursor]

        mock_gen.return_value = None

        result = pipeline.generate_user_dossier("test_user")
        assert result is None
        # Should NOT call UPDATE or commit when dossier is None
        # (only the 3 SELECT calls happened)
        assert db.execute.call_count == 3

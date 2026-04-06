# tests/test_dossier_builder.py
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database


@pytest.fixture
def db_with_events(tmp_path):
    db_path = str(tmp_path / "dossier_test.db")
    db = Database(db_path)
    base_ts = 1_700_000_000_000
    for i in range(5):
        db.execute(
            """INSERT INTO events (username, latitude, longitude, timestamp_ms,
               timestamp_utc, report_type, subtype, event_hash, raw_json,
               collected_at, grid_cell)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "dossieruser",
                40.4168 + i * 0.01,
                -3.7038 + i * 0.01,
                base_ts + i * 3600_000,
                "2023-11-14T12:00:00Z",
                "POLICE",
                "",
                f"dos_{i}",
                "{}",
                "2023-11-14T12:00:00Z",
                "test_cell",
            ),
        )
    db.conn.commit()
    yield db
    db.close()


@pytest.fixture
def empty_db(tmp_path):
    db_path = str(tmp_path / "empty_test.db")
    db = Database(db_path)
    yield db
    db.close()


def test_build_dossier_basic(db_with_events):
    from dossier_builder import build_dossier

    result = build_dossier("dossieruser", db_with_events)
    assert result["username"] == "dossieruser"
    assert result["total_events"] == 5
    assert "generated_at" in result
    # All section keys present
    for key in (
        "report",
        "privacy_score",
        "trips",
        "social",
        "fingerprint",
        "anomalies",
        "ai_narrative",
    ):
        assert key in result


def test_build_dossier_empty_events(empty_db):
    from dossier_builder import build_dossier

    result = build_dossier("nobody", empty_db)
    assert result["username"] == "nobody"
    assert result["total_events"] == 0


def test_report_section_failure(db_with_events):
    from dossier_builder import build_dossier

    with patch("dossier_builder.build_dossier.__module__", "dossier_builder"):
        with patch.dict("sys.modules", {"report_generator": MagicMock(side_effect=ImportError)}):
            # Force a fresh import path by patching at the call site
            pass

    # Even if report_generator fails, other sections still populate
    with patch("builtins.__import__", side_effect=_selective_import_error("report_generator")):
        result = build_dossier("dossieruser", db_with_events)
        assert result["report"] is None
        # Other sections should still be attempted
        assert "privacy_score" in result


def test_privacy_score_section_failure(db_with_events):
    from dossier_builder import build_dossier

    with patch("builtins.__import__", side_effect=_selective_import_error("privacy_score")):
        result = build_dossier("dossieruser", db_with_events)
        assert result["privacy_score"] is None


def test_render_dossier_html():
    from dossier_builder import render_dossier_html

    dossier = {
        "username": "testuser",
        "generated_at": "2024-01-01T00:00:00Z",
        "total_events": 10,
        "report": None,
        "privacy_score": None,
        "trips": None,
        "social": None,
        "fingerprint": None,
        "anomalies": None,
        "ai_narrative": None,
    }
    html = render_dossier_html(dossier)
    assert "<html" in html
    assert "testuser" in html
    assert "OSINT Intelligence Dossier" in html


def test_render_dossier_html_with_data():
    from dossier_builder import render_dossier_html

    dossier = {
        "username": "richuser",
        "generated_at": "2024-01-01T00:00:00Z",
        "total_events": 50,
        "report": {
            "active_days": 10,
            "area_km2": 5.2,
            "event_types": [{"type": "POLICE", "count": 30, "pct": 60}],
            "locations": [{"label": "home", "lat": 40.41, "lon": -3.70, "count": 20}],
        },
        "privacy_score": {
            "overall_score": 72,
            "sub_scores": {
                "home_inference": 80,
                "work_inference": 65,
                "schedule_predictability": 70,
                "route_predictability": 55,
                "identity_exposure": 90,
                "trackability": 60,
            },
        },
        "trips": [
            {
                "start_time": "2024-01-01T08:00:00",
                "end_time": "2024-01-01T08:30:00",
                "distance_km": 12.5,
                "duration_min": 30,
                "label": "commute",
            }
        ],
        "social": {
            "total_connections": 3,
            "community_id": 1,
            "top_connections": [
                {"source": "richuser", "target": "friend1", "weight": 5, "type": "co-located"}
            ],
        },
        "fingerprint": [0.0] * 168,
        "anomalies": {
            "anomaly_score": 45,
            "time_anomalies": ["Late night activity at 3am"],
            "location_anomalies": [],
            "frequency_anomalies": [],
        },
        "ai_narrative": None,
    }
    html = render_dossier_html(dossier)
    assert "richuser" in html
    assert "POLICE" in html
    assert "home" in html
    assert "commute" in html
    assert "friend1" in html


def test_ai_narrative_fallback():
    from dossier_builder import render_dossier_html

    dossier = {
        "username": "noai",
        "generated_at": "2024-01-01T00:00:00Z",
        "total_events": 0,
        "report": None,
        "privacy_score": None,
        "trips": None,
        "social": None,
        "fingerprint": None,
        "anomalies": None,
        "ai_narrative": None,
    }
    html = render_dossier_html(dossier)
    assert "Ollama not running" in html


# Helper to selectively fail imports
def _selective_import_error(module_name):
    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def custom_import(name, *args, **kwargs):
        if name == module_name:
            raise ImportError(f"Mocked import error for {name}")
        return original_import(name, *args, **kwargs)

    return custom_import

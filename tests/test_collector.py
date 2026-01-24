# tests/test_collector.py
import pytest
from collector import generate_event_hash, process_alert

def test_generate_event_hash_consistent():
    hash1 = generate_event_hash(
        username="testuser",
        latitude=40.42,
        longitude=-3.70,
        timestamp_ms=1737709200000,
        report_type="police"
    )
    hash2 = generate_event_hash(
        username="testuser",
        latitude=40.42,
        longitude=-3.70,
        timestamp_ms=1737709200000,
        report_type="police"
    )
    assert hash1 == hash2

def test_generate_event_hash_different_for_different_input():
    hash1 = generate_event_hash(
        username="testuser",
        latitude=40.42,
        longitude=-3.70,
        timestamp_ms=1737709200000,
        report_type="police"
    )
    hash2 = generate_event_hash(
        username="otheruser",
        latitude=40.42,
        longitude=-3.70,
        timestamp_ms=1737709200000,
        report_type="police"
    )
    assert hash1 != hash2

def test_process_alert_extracts_fields():
    alert = {
        "type": "POLICE",
        "subtype": "POLICE_VISIBLE",
        "latitude": 40.42,
        "longitude": -3.70,
        "country": "ES",
        "reportBy": "testuser123",
        "pubMillis": 1737709200000
    }

    event = process_alert(alert, grid_cell="test_cell")

    assert event["username"] == "testuser123"
    assert event["latitude"] == 40.42
    assert event["longitude"] == -3.70
    assert event["report_type"] == "POLICE"
    assert event["subtype"] == "POLICE_VISIBLE"
    assert event["grid_cell"] == "test_cell"
    assert "event_hash" in event
    assert "collected_at" in event
    assert "timestamp_utc" in event
    assert "raw_json" in event

def test_process_alert_handles_missing_username():
    alert = {
        "type": "JAM",
        "latitude": 40.42,
        "longitude": -3.70,
        "pubMillis": 1737709200000
    }

    event = process_alert(alert, grid_cell="test_cell")

    assert event["username"] == "anonymous"
    assert event["report_type"] == "JAM"

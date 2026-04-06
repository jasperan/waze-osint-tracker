"""Tests for the /api/social-graph data shapes that the D3 widget depends on.

Validates node/edge structure, community field, limit parameter, and ego network.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Create a Flask test client with a temporary database seeded with co-located events."""
    db_path = str(tmp_path / "test_widget.db")
    db = Database(db_path)

    base_ts = 1_700_000_000_000
    # Insert co-located events for alice and bob (close in time and space)
    for i in range(5):
        ts = base_ts + i * 60_000
        for username, lat_off in [("alice", 0), ("bob", 0.0001)]:
            db.execute(
                """INSERT INTO events (username, latitude, longitude, timestamp_ms,
                   timestamp_utc, report_type, subtype, event_hash, raw_json,
                   collected_at, grid_cell)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    username,
                    40.4168 + lat_off,
                    -3.7038,
                    ts + int(lat_off * 200_000_000),
                    "2023-11-14T12:00:00Z",
                    "POLICE",
                    "",
                    f"hash_{username}_{i}",
                    "{}",
                    "2023-11-14T12:00:00Z",
                    "test_cell",
                ),
            )
    # carol is isolated (different location, different time)
    db.execute(
        """INSERT INTO events (username, latitude, longitude, timestamp_ms,
           timestamp_utc, report_type, subtype, event_hash, raw_json,
           collected_at, grid_cell)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "carol",
            41.0,
            -4.0,
            base_ts + 500_000,
            "2023-11-14T12:08:00Z",
            "HAZARD",
            "",
            "hash_carol_0",
            "{}",
            "2023-11-14T12:08:00Z",
            "test_cell",
        ),
    )
    db.conn.commit()

    import web.app as webapp

    original_paths = webapp.DB_PATHS.copy()
    original_db_path = webapp.DB_PATH
    webapp.DB_PATHS = {"test": db_path}
    webapp.DB_PATH = db_path
    monkeypatch.setattr(webapp, "_load_web_config", lambda: {"database_type": "sqlite"})

    webapp.app.config["TESTING"] = True
    client = webapp.app.test_client()
    yield client

    webapp.DB_PATHS = original_paths
    webapp.DB_PATH = original_db_path


def test_full_graph_returns_nodes_and_edges(app_client):
    """Full graph endpoint returns correct top-level keys."""
    resp = app_client.get("/api/social-graph?limit=200")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


def test_node_has_required_fields(app_client):
    """Each node must have id, event_count, top_type, and community."""
    resp = app_client.get("/api/social-graph")
    data = json.loads(resp.data)
    for node in data["nodes"]:
        assert "id" in node, "Node missing 'id'"
        assert "event_count" in node, "Node missing 'event_count'"
        assert "top_type" in node, "Node missing 'top_type'"
        assert "community" in node, "Node missing 'community'"


def test_edge_has_required_fields(app_client):
    """Each edge must have source, target, weight, and relationship."""
    resp = app_client.get("/api/social-graph?min_cooccurrences=1")
    data = json.loads(resp.data)
    for edge in data["edges"]:
        assert "source" in edge, "Edge missing 'source'"
        assert "target" in edge, "Edge missing 'target'"
        assert "weight" in edge, "Edge missing 'weight'"
        assert "relationship" in edge, "Edge missing 'relationship'"


def test_community_field_is_integer(app_client):
    """Community field on each node should be an integer."""
    resp = app_client.get("/api/social-graph")
    data = json.loads(resp.data)
    for node in data["nodes"]:
        assert isinstance(node["community"], int), f"Community not int: {node['community']}"


def test_limit_parameter_caps_events(app_client):
    """The limit parameter should be accepted without error."""
    resp = app_client.get("/api/social-graph?limit=2")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "nodes" in data


def test_ego_network_returns_subgraph(app_client):
    """Ego network endpoint returns a subgraph containing the queried user."""
    resp = app_client.get("/api/social-graph/alice")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "nodes" in data
    assert "edges" in data
    user_ids = [n["id"] for n in data["nodes"]]
    assert "alice" in user_ids


def test_ego_network_unknown_user(app_client):
    """Ego network for a nonexistent user should return empty graph, not error."""
    resp = app_client.get("/api/social-graph/nonexistent_user_xyz")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "nodes" in data
    assert "edges" in data

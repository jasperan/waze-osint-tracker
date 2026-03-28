# tests/test_social_graph.py
"""Tests for social_graph module: graph building, ego networks, community detection."""

import pytest

from social_graph import build_social_graph, detect_communities, get_ego_network

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_LAT, BASE_LON = 40.4168, -3.7038  # Madrid center
MINUTE_MS = 60_000


def _event(username, lat, lon, ts_ms, report_type="POLICE"):
    return {
        "username": username,
        "latitude": lat,
        "longitude": lon,
        "timestamp_ms": ts_ms,
        "report_type": report_type,
    }


def _colocated_pair(user_a, user_b, count, base_ts=1_000_000_000_000, report_type="POLICE"):
    """Generate *count* pairs of events where user_a and user_b are at the same
    location and time (co-occurring). Each pair is separated by 10 minutes so
    they register as distinct co-occurrences."""
    events = []
    for i in range(count):
        ts = base_ts + i * 10 * MINUTE_MS
        # user_a event
        events.append(_event(user_a, BASE_LAT, BASE_LON, ts, report_type))
        # user_b event within 100m and 60s
        events.append(_event(user_b, BASE_LAT + 0.0005, BASE_LON, ts + 60_000, report_type))
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_user_events():
    """alice+bob co-occur 4 times, bob+charlie 3 times, dave is isolated."""
    events = []
    # alice + bob: 4 co-occurrences (POLICE)
    events.extend(_colocated_pair("alice", "bob", 4, base_ts=1_000_000_000_000))
    # bob + charlie: 3 co-occurrences (JAM), offset in time to avoid mixing
    events.extend(
        _colocated_pair("bob", "charlie", 3, base_ts=2_000_000_000_000, report_type="JAM")
    )
    # dave: isolated user with 2 events far away in space and time
    events.append(_event("dave", 35.0, 139.0, 3_000_000_000_000, "HAZARD"))
    events.append(_event("dave", 35.0, 139.0, 3_000_000_060_000, "HAZARD"))
    return events


@pytest.fixture
def sample_graph(multi_user_events):
    return build_social_graph(
        multi_user_events,
        min_cooccurrences=3,
        spatial_threshold_m=500,
        temporal_threshold_s=300,
    )


# ---------------------------------------------------------------------------
# build_social_graph tests
# ---------------------------------------------------------------------------


class TestBuildSocialGraph:
    def test_all_users_appear_as_nodes(self, sample_graph):
        node_ids = {n["id"] for n in sample_graph["nodes"]}
        assert node_ids == {"alice", "bob", "charlie", "dave"}

    def test_edge_count(self, sample_graph):
        # alice-bob and bob-charlie
        assert len(sample_graph["edges"]) == 2

    def test_edge_weights(self, sample_graph):
        edge_map = {(e["source"], e["target"]): e for e in sample_graph["edges"]}
        ab = edge_map.get(("alice", "bob"))
        assert ab is not None
        assert ab["weight"] >= 4  # at least 4 co-occurrences

        bc = edge_map.get(("bob", "charlie"))
        assert bc is not None
        assert bc["weight"] >= 3

    def test_edge_has_distance_and_time_gap(self, sample_graph):
        for edge in sample_graph["edges"]:
            assert "avg_distance_m" in edge
            assert "avg_time_gap_s" in edge
            assert edge["avg_distance_m"] >= 0
            assert edge["avg_time_gap_s"] >= 0

    def test_edge_relationship_type(self, sample_graph):
        for edge in sample_graph["edges"]:
            assert edge["relationship"] in {
                "SAME_PERSON",
                "CONVOY",
                "SIMILAR_ROUTINE",
                "WEAK_MATCH",
            }

    def test_node_event_count(self, sample_graph):
        node_map = {n["id"]: n for n in sample_graph["nodes"]}
        # alice has 4 events (one per co-occurrence with bob)
        assert node_map["alice"]["event_count"] == 4
        # bob: 4 from alice pair + 3 from charlie pair = 7
        assert node_map["bob"]["event_count"] == 7
        assert node_map["charlie"]["event_count"] == 3
        assert node_map["dave"]["event_count"] == 2

    def test_node_top_type(self, sample_graph):
        node_map = {n["id"]: n for n in sample_graph["nodes"]}
        assert node_map["alice"]["top_type"] == "POLICE"
        assert node_map["dave"]["top_type"] == "HAZARD"
        # bob has 4 POLICE + 3 JAM, so POLICE wins
        assert node_map["bob"]["top_type"] == "POLICE"
        assert node_map["charlie"]["top_type"] == "JAM"

    def test_isolated_node_has_no_edges(self, sample_graph):
        dave_edges = [
            e for e in sample_graph["edges"] if e["source"] == "dave" or e["target"] == "dave"
        ]
        assert dave_edges == []

    def test_empty_events(self):
        graph = build_social_graph([])
        assert graph == {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# get_ego_network tests
# ---------------------------------------------------------------------------


class TestEgoNetwork:
    def test_depth_1_from_alice(self, sample_graph):
        ego = get_ego_network(sample_graph, "alice", depth=1)
        ego_ids = {n["id"] for n in ego["nodes"]}
        # alice sees bob at depth 1, but not charlie or dave
        assert "alice" in ego_ids
        assert "bob" in ego_ids
        assert "charlie" not in ego_ids
        assert "dave" not in ego_ids

    def test_depth_2_from_alice(self, sample_graph):
        ego = get_ego_network(sample_graph, "alice", depth=2)
        ego_ids = {n["id"] for n in ego["nodes"]}
        # alice -> bob -> charlie (2 hops), dave is unreachable
        assert "alice" in ego_ids
        assert "bob" in ego_ids
        assert "charlie" in ego_ids
        assert "dave" not in ego_ids

    def test_ego_edges_only_between_included_nodes(self, sample_graph):
        ego = get_ego_network(sample_graph, "alice", depth=1)
        ego_ids = {n["id"] for n in ego["nodes"]}
        for edge in ego["edges"]:
            assert edge["source"] in ego_ids
            assert edge["target"] in ego_ids

    def test_nonexistent_user(self, sample_graph):
        ego = get_ego_network(sample_graph, "nobody", depth=2)
        assert ego == {"nodes": [], "edges": []}

    def test_ego_on_empty_graph(self):
        empty = {"nodes": [], "edges": []}
        ego = get_ego_network(empty, "alice", depth=2)
        assert ego == {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# detect_communities tests
# ---------------------------------------------------------------------------


class TestDetectCommunities:
    def test_connected_users_same_community(self, sample_graph):
        comms = detect_communities(sample_graph)
        # alice and bob are connected, should be in the same community
        assert comms["alice"] == comms["bob"]

    def test_bob_and_charlie_same_community(self, sample_graph):
        comms = detect_communities(sample_graph)
        # bob and charlie are connected; by transitivity through bob,
        # alice, bob, charlie should all end up in one community
        assert comms["bob"] == comms["charlie"]

    def test_isolated_node_separate_community(self, sample_graph):
        comms = detect_communities(sample_graph)
        # dave has no edges, so should be in a different community
        connected_community = comms["alice"]
        assert comms["dave"] != connected_community

    def test_community_ids_are_zero_based(self, sample_graph):
        comms = detect_communities(sample_graph)
        ids = set(comms.values())
        assert min(ids) == 0
        # IDs should be sequential from 0
        assert ids == set(range(len(ids)))

    def test_all_users_assigned(self, sample_graph):
        comms = detect_communities(sample_graph)
        node_ids = {n["id"] for n in sample_graph["nodes"]}
        assert set(comms.keys()) == node_ids

    def test_empty_graph(self):
        empty = {"nodes": [], "edges": []}
        comms = detect_communities(empty)
        assert comms == {}

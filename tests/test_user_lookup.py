from __future__ import annotations

from user_lookup import find_user_match


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self, tracked_row, event_row):
        self.tracked_row = tracked_row
        self.event_row = event_row

    def execute(self, query, params):
        if "FROM tracked_users" in query:
            return _FakeResult(self.tracked_row)
        return _FakeResult(self.event_row)


def test_find_user_match_prefers_tracked_user_metadata():
    dbs = [
        (
            "europe",
            _FakeDB(
                {"event_count": 4, "last_seen": "2026-04-03T00:00:00+00:00"},
                {"event_count": 99, "last_seen_ms": 1},
            ),
        ),
        (
            "americas",
            _FakeDB(
                {"event_count": 2, "last_seen": "2026-04-02T00:00:00+00:00"},
                {"event_count": 99, "last_seen_ms": 2},
            ),
        ),
    ]

    match = find_user_match("alice", dbs)

    assert match is not None
    assert match["region"] == "europe"
    assert match["event_count"] == 4


def test_find_user_match_falls_back_to_events_when_tracked_users_missing():
    dbs = [
        (
            "asia",
            _FakeDB(
                None,
                {"event_count": 3, "last_seen_ms": 1234},
            ),
        )
    ]

    match = find_user_match("bob", dbs)

    assert match is not None
    assert match["region"] == "asia"
    assert match["event_count"] == 3
    assert match["last_seen_ms"] == 1234

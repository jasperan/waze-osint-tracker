"""Real-time anomaly feed — micro-batch adapter for streaming anomaly detection."""

import logging
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AnomalyFeed:
    """Micro-batch anomaly detector with sliding window baseline.

    Maintains a sliding window of recent events for baseline statistics.
    On each check_batch() call, runs anomaly detection on the batch
    and cross-references with geofence zones.
    """

    def __init__(self, window_size: int = 1000):
        self._window: deque = deque(maxlen=window_size)
        self._geofence_mgr = None
        self._recent_anomalies: deque = deque(maxlen=100)
        self._init_geofence()

    def _init_geofence(self):
        """Try to load geofence manager, fail silently."""
        try:
            from geofence import GeofenceManager

            # GeofenceManager requires a db handle; defer until we have one
            self._geofence_cls = GeofenceManager
        except Exception as e:
            logger.debug("Geofence not available: %s", e)
            self._geofence_cls = None

    def _get_geofence_mgr(self, db=None):
        """Lazily instantiate GeofenceManager when a db is available."""
        if self._geofence_mgr is not None:
            return self._geofence_mgr
        if self._geofence_cls is None or db is None:
            return None
        try:
            self._geofence_mgr = self._geofence_cls(db)
        except Exception as e:
            logger.debug("Could not init GeofenceManager: %s", e)
            self._geofence_mgr = None
        return self._geofence_mgr

    def check_batch(self, new_events: list[dict], db=None) -> list[dict]:
        """Run anomaly detection on a micro-batch of new events.

        1. Add new events to sliding window
        2. Run detect_anomalies on window to get baseline scores
        3. For each new event, check if it's anomalous
        4. Cross-reference with geofence
        5. Return list of anomaly alerts
        """
        if not new_events:
            return []

        # Add to window
        self._window.extend(new_events)

        # Run batch detection on full window for baseline
        from anomaly_detection import detect_anomalies

        result = detect_anomalies(list(self._window))

        if not result["anomalies"]:
            return []

        # Build lookup of new event identifiers for fast matching
        new_set = set()
        for ev in new_events:
            key = (
                ev.get("username", ""),
                ev.get("timestamp_ms", ev.get("timestamp", "")),
                ev.get("latitude"),
                ev.get("longitude"),
            )
            new_set.add(key)

        # Map anomalies back to new events
        alerts: list[dict] = []
        gfm = self._get_geofence_mgr(db)

        for anom in result["anomalies"]:
            anom_type = anom.get("type", "unknown")
            score = anom.get("score", 0.0)

            # Find the originating event from the new batch
            matched_event = self._match_anomaly_to_event(anom, new_events)
            if matched_event is None:
                continue

            username = matched_event.get("username", "unknown")
            lat = matched_event.get("latitude")
            lon = matched_event.get("longitude")

            # Determine timestamp
            ts_ms = matched_event.get("timestamp_ms")
            if ts_ms:
                timestamp = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
            else:
                timestamp = matched_event.get(
                    "timestamp_utc",
                    matched_event.get("timestamp", datetime.now(timezone.utc).isoformat()),
                )

            # Check geofence
            geofence_name = None
            if gfm is not None and lat is not None and lon is not None:
                try:
                    gf_alerts = gfm.check_event(matched_event)
                    if gf_alerts:
                        geofence_name = gf_alerts[0].get("geofence_name")
                except Exception as e:
                    logger.debug("Geofence check failed: %s", e)

            alert = {
                "username": username,
                "anomaly_type": anom_type,
                "score": round(score, 2),
                "timestamp": timestamp,
                "geofence_name": geofence_name,
                "lat": float(lat) if lat is not None else None,
                "lon": float(lon) if lon is not None else None,
            }
            alerts.append(alert)

        self._recent_anomalies.extend(alerts)
        return alerts

    def _match_anomaly_to_event(self, anomaly: dict, new_events: list[dict]) -> dict | None:
        """Match an anomaly result back to a specific new event."""
        details = anomaly.get("details", {})
        anom_type = anomaly.get("type", "")

        if anom_type == "time":
            # Time anomalies carry timestamp_ms in details
            target_ts = details.get("timestamp_ms")
            if target_ts is not None:
                for ev in new_events:
                    if ev.get("timestamp_ms") == target_ts:
                        return ev

        elif anom_type == "location":
            # Location anomalies carry lat/lon in details
            target_lat = details.get("latitude")
            target_lon = details.get("longitude")
            if target_lat is not None and target_lon is not None:
                for ev in new_events:
                    if (
                        ev.get("latitude") is not None
                        and abs(float(ev["latitude"]) - target_lat) < 1e-6
                        and ev.get("longitude") is not None
                        and abs(float(ev["longitude"]) - target_lon) < 1e-6
                    ):
                        return ev

        elif anom_type == "frequency":
            # Frequency anomalies are per-day, not per-event; pick the last
            # new event from that day as representative
            target_date = details.get("date")
            if target_date:
                for ev in reversed(new_events):
                    ts_ms = ev.get("timestamp_ms")
                    if ts_ms is None:
                        continue
                    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                    if dt.strftime("%Y-%m-%d") == target_date:
                        return ev

        # Fallback: return the first new event if we couldn't match
        return new_events[0] if new_events else None

    def get_recent(self, limit: int = 100) -> list[dict]:
        """Return most recent anomalies."""
        items = list(self._recent_anomalies)
        return items[-limit:]

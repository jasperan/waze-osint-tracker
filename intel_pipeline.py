# intel_pipeline.py
"""Intelligence pipeline: orchestrates vector construction, routine inference,
co-occurrence detection, and dossier generation against Oracle 26ai."""

import json
import logging
from typing import Optional

import numpy as np

from intel_cooccurrence import find_cooccurrences
from intel_dossier import generate_dossier
from intel_routines import infer_routines
from intel_vectors import REGION_BBOXES, build_behavioral_vector

logger = logging.getLogger(__name__)


class IntelligencePipeline:
    """Orchestrates the full behavioral intelligence pipeline."""

    def __init__(self, db):
        """
        Args:
            db: OracleDatabase instance
        """
        self.db = db

    def build_user_vectors(self, min_events: int = 20, region: str = None):
        """Build behavioral vectors for all qualifying users."""
        logger.info("Building behavioral vectors (min_events=%d)", min_events)

        # Get max event count for normalization
        cursor = self.db.execute(
            "SELECT MAX(cnt) FROM (SELECT COUNT(*) cnt FROM events GROUP BY username)"
        )
        max_count = cursor.fetchone()[0] or 1

        # Get qualifying users
        query = """
            SELECT username, COUNT(*) as cnt,
                   MIN(timestamp_utc) as first_seen, MAX(timestamp_utc) as last_seen
            FROM events
            GROUP BY username
            HAVING COUNT(*) >= :1
        """
        params = (min_events,)
        cursor = self.db.execute(query, params)
        columns = [col[0].lower() for col in cursor.description]
        users = [dict(zip(columns, row)) for row in cursor.fetchall()]

        logger.info("Found %d users with >= %d events", len(users), min_events)
        processed = 0

        for user_row in users:
            username = user_row["username"]

            # Fetch user's events
            cursor = self.db.execute(
                "SELECT latitude, longitude, timestamp_ms, report_type, region "
                "FROM events WHERE username = :1 ORDER BY timestamp_ms",
                (username,),
            )
            cols = [c[0].lower() for c in cursor.description]
            events = [dict(zip(cols, r)) for r in cursor.fetchall()]

            if not events:
                continue

            # Determine region from most frequent
            region_counts = {}
            for e in events:
                r = e.get("region", "global")
                region_counts[r] = region_counts.get(r, 0) + 1
            primary_region = max(region_counts, key=region_counts.get)
            bbox = REGION_BBOXES.get(primary_region, REGION_BBOXES["global"])

            # Build vector
            vec = build_behavioral_vector(events, bbox, max_event_count=max_count)

            # Compute features for storage
            from datetime import datetime, timezone

            from intel_vectors import build_dow_histogram, build_hour_histogram

            hours = [
                datetime.fromtimestamp(e["timestamp_ms"] / 1000, tz=timezone.utc).hour
                for e in events
            ]
            dows = [
                datetime.fromtimestamp(e["timestamp_ms"] / 1000, tz=timezone.utc).weekday()
                for e in events
            ]

            lats = [e["latitude"] for e in events]
            lons = [e["longitude"] for e in events]
            mean_lat = sum(lats) / len(lats)
            mean_lon = sum(lons) / len(lons)

            from intel_vectors import haversine_km

            distances = [haversine_km(lat, lon, mean_lat, mean_lon) for lat, lon in zip(lats, lons)]
            geo_spread = float(np.std(distances)) if len(distances) > 1 else 0.0

            type_counts = {}
            for e in events:
                t = e["report_type"]
                type_counts[t] = type_counts.get(t, 0) + 1

            sorted_ts = sorted(e["timestamp_ms"] for e in events)
            gaps = (
                [(sorted_ts[i + 1] - sorted_ts[i]) / 3600000.0 for i in range(len(sorted_ts) - 1)]
                if len(sorted_ts) > 1
                else [0]
            )

            # Upsert into user_behavioral_vectors
            vec_list = vec.tolist()
            self.db.execute(
                """
                MERGE INTO user_behavioral_vectors t
                USING (SELECT :1 AS username FROM DUAL) s
                ON (t.username = s.username)
                WHEN MATCHED THEN UPDATE SET
                    region = :2, event_count = :3,
                    first_seen = TO_TIMESTAMP_TZ(:4, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM'),
                    last_seen = TO_TIMESTAMP_TZ(:5, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM'),
                    centroid_lat = :6, centroid_lon = :7, geo_spread_km = :8,
                    hour_histogram = :9, dow_histogram = :10,
                    type_distribution = :11, cadence_stats = :12,
                    behavior_vector = :13,
                    vector_updated_at = SYSTIMESTAMP
                WHEN NOT MATCHED THEN INSERT (
                    username, region, event_count, first_seen, last_seen,
                    centroid_lat, centroid_lon, geo_spread_km,
                    hour_histogram, dow_histogram, type_distribution, cadence_stats,
                    behavior_vector, vector_updated_at
                ) VALUES (
                    :1, :2, :3,
                    TO_TIMESTAMP_TZ(:4, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM'),
                    TO_TIMESTAMP_TZ(:5, 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM'),
                    :6, :7, :8,
                    :9, :10, :11, :12, :13, SYSTIMESTAMP
                )
            """,
                (
                    username,
                    primary_region,
                    len(events),
                    str(user_row["first_seen"]),
                    str(user_row["last_seen"]),
                    mean_lat,
                    mean_lon,
                    round(geo_spread, 2),
                    json.dumps(build_hour_histogram(hours)),
                    json.dumps(build_dow_histogram(dows)),
                    json.dumps(type_counts),
                    json.dumps(
                        {
                            "mean": round(float(np.mean(gaps)), 2),
                            "std": round(float(np.std(gaps)), 2),
                            "median": round(float(np.median(gaps)), 2),
                        }
                    ),
                    vec_list,
                ),
            )

            processed += 1
            if processed % 100 == 0:
                self.db.commit()
                logger.info("  Processed %d/%d users", processed, len(users))

        self.db.commit()
        logger.info("Vector construction complete: %d users processed", processed)
        return processed

    def run_routine_inference(self, min_events: int = 20):
        """Run routine inference for all qualifying users."""
        logger.info("Running routine inference")

        cursor = self.db.execute(
            "SELECT DISTINCT username FROM user_behavioral_vectors WHERE event_count >= :1",
            (min_events,),
        )
        usernames = [row[0] for row in cursor.fetchall()]
        processed = 0

        for username in usernames:
            cursor = self.db.execute(
                "SELECT latitude, longitude, timestamp_ms, report_type "
                "FROM events WHERE username = :1",
                (username,),
            )
            cols = [c[0].lower() for c in cursor.description]
            events = [dict(zip(cols, r)) for r in cursor.fetchall()]

            routines = infer_routines(events)
            for routine_type, data in routines.items():
                self.db.execute(
                    """
                    MERGE INTO user_routines t
                    USING (SELECT :1 AS username, :2 AS routine_type FROM DUAL) s
                    ON (t.username = s.username AND t.routine_type = s.routine_type)
                    WHEN MATCHED THEN UPDATE SET
                        latitude = :3, longitude = :4, confidence = :5,
                        typical_hours = :6, typical_days = :7, evidence_count = :8
                    WHEN NOT MATCHED THEN INSERT
                        (username, routine_type, latitude, longitude, confidence,
                         typical_hours, typical_days, evidence_count)
                    VALUES (:1, :2, :3, :4, :5, :6, :7, :8)
                """,
                    (
                        username,
                        routine_type,
                        data["latitude"],
                        data["longitude"],
                        data["confidence"],
                        json.dumps(data.get("typical_hours", [])),
                        json.dumps(data.get("typical_days", [])),
                        data.get("evidence_count", 0),
                    ),
                )

            processed += 1
            if processed % 100 == 0:
                self.db.commit()

        self.db.commit()
        logger.info("Routine inference complete: %d users", processed)
        return processed

    def find_similar_users(self, username: str, top_k: int = 10):
        """Find most behaviorally similar users via Oracle AI Vector Search."""
        cursor = self.db.execute(
            "SELECT behavior_vector FROM user_behavioral_vectors WHERE username = :1", (username,)
        )
        row = cursor.fetchone()
        if not row:
            return []

        target_vector = row[0]

        cursor = self.db.execute(
            """
            SELECT username,
                   VECTOR_DISTANCE(behavior_vector, :1, COSINE) AS distance
            FROM user_behavioral_vectors
            WHERE username != :2 AND event_count >= 20
            ORDER BY VECTOR_DISTANCE(behavior_vector, :1, COSINE) ASC
            FETCH FIRST :3 ROWS ONLY
        """,
            (target_vector, username, top_k),
        )

        columns = [c[0].lower() for c in cursor.description]
        return [dict(zip(columns, r)) for r in cursor.fetchall()]

    def build_cooccurrence_graph(self, region: str = None):
        """Build co-occurrence edges from events."""
        logger.info("Building co-occurrence graph")

        query = "SELECT username, latitude, longitude, timestamp_ms, region FROM events"
        params = ()
        if region:
            query += " WHERE region = :1"
            params = (region,)
        query += " ORDER BY timestamp_ms"

        cursor = self.db.execute(query, params)
        cols = [c[0].lower() for c in cursor.description]

        # Process in chunks to manage memory
        edges_total = 0
        batch = []
        while True:
            rows = cursor.fetchmany(50000)
            if not rows:
                break
            batch.extend(dict(zip(cols, r)) for r in rows)

        edges = find_cooccurrences(batch)
        for edge in edges:
            self.db.execute(
                """
                MERGE INTO user_co_occurrences t
                USING (SELECT :1 AS user_a, :2 AS user_b FROM DUAL) s
                ON (t.user_a = s.user_a AND t.user_b = s.user_b)
                WHEN MATCHED THEN UPDATE SET
                    co_count = :3, avg_distance_m = :4, avg_time_gap_s = :5,
                    last_co = SYSTIMESTAMP
                WHEN NOT MATCHED THEN INSERT
                    (user_a, user_b, co_count, avg_distance_m, avg_time_gap_s,
                     first_co, last_co)
                VALUES (:1, :2, :3, :4, :5, SYSTIMESTAMP, SYSTIMESTAMP)
            """,
                (
                    edge["user_a"],
                    edge["user_b"],
                    edge["co_count"],
                    edge["avg_distance_m"],
                    edge["avg_time_gap_s"],
                ),
            )
            edges_total += 1

        self.db.commit()
        logger.info("Co-occurrence graph: %d edges", edges_total)
        return edges_total

    def generate_user_dossier(self, username: str) -> Optional[str]:
        """Generate LLM dossier for a single user."""
        # Gather all intelligence
        cursor = self.db.execute(
            "SELECT * FROM user_behavioral_vectors WHERE username = :1", (username,)
        )
        cols = [c[0].lower() for c in cursor.description]
        user_row = cursor.fetchone()
        if not user_row:
            return None
        user_data = dict(zip(cols, user_row))

        # Get routines
        cursor = self.db.execute("SELECT * FROM user_routines WHERE username = :1", (username,))
        rcols = [c[0].lower() for c in cursor.description]
        routines = {r[1]: dict(zip(rcols, r)) for r in cursor.fetchall()}  # routine_type -> data

        # Get similar users
        similar = self.find_similar_users(username, top_k=3)

        # Get co-occurrence partners
        cursor = self.db.execute(
            """
            SELECT user_a, user_b, co_count FROM user_co_occurrences
            WHERE user_a = :1 OR user_b = :1
            ORDER BY co_count DESC FETCH FIRST 3 ROWS ONLY
        """,
            (username,),
        )
        co_partners = []
        for row in cursor.fetchall():
            partner = row[1] if row[0] == username else row[0]
            co_partners.append({"username": partner, "co_count": row[2]})

        # Build profile dict
        cadence = (
            json.loads(user_data.get("cadence_stats", "{}"))
            if isinstance(user_data.get("cadence_stats"), str)
            else user_data.get("cadence_stats", {})
        )
        type_dist = (
            json.loads(user_data.get("type_distribution", "{}"))
            if isinstance(user_data.get("type_distribution"), str)
            else user_data.get("type_distribution", {})
        )

        profile = {
            "username": username,
            "event_count": user_data["event_count"],
            "days_active": 45,  # approximate
            "first_seen": str(user_data.get("first_seen", "")),
            "last_seen": str(user_data.get("last_seen", "")),
            "region": user_data.get("region", ""),
            "type_distribution": type_dist,
            "routines": {
                k: {
                    "latitude": v.get("latitude"),
                    "longitude": v.get("longitude"),
                    "confidence": v.get("confidence"),
                }
                for k, v in routines.items()
            },
            "peak_hours": [8, 9, 17, 18],
            "peak_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "cadence_mean_hours": cadence.get("mean", 0),
            "cadence_std_hours": cadence.get("std", 0),
            "similar_users": [
                {"username": s["username"], "similarity": 1 - s.get("distance", 0)} for s in similar
            ],
            "co_occurrence_partners": co_partners,
            "prediction": None,
        }

        dossier = generate_dossier(profile)
        if dossier:
            self.db.execute(
                """
                UPDATE user_behavioral_vectors
                SET dossier = :1, dossier_updated_at = SYSTIMESTAMP
                WHERE username = :2
            """,
                (dossier, username),
            )
            self.db.commit()

        return dossier

"""Encounter prediction module — predict when and where two users might meet."""

from itertools import combinations
from typing import Dict, List

from intel_prediction import predict_presence
from utils import haversine_km


def predict_encounters(
    events_a: List[Dict],
    events_b: List[Dict],
    distance_threshold_km: float = 2.0,
    min_confidence: float = 0.1,
) -> List[Dict]:
    """Predict likely encounters between two users across all day/hour slots.

    For each (dow, hour) combination, calls predict_presence for both users.
    If both return predictions within distance_threshold_km, computes an
    encounter probability and a confidence-weighted meeting point.

    Returns a list of encounter dicts sorted by probability descending.
    """
    encounters: List[Dict] = []

    for dow in range(7):
        for hour in range(24):
            pred_a = predict_presence(events_a, dow, hour)
            pred_b = predict_presence(events_b, dow, hour)

            if pred_a is None or pred_b is None:
                continue

            dist = haversine_km(
                pred_a["latitude"],
                pred_a["longitude"],
                pred_b["latitude"],
                pred_b["longitude"],
            )

            if dist >= distance_threshold_km:
                continue

            proximity_factor = max(0.0, 1.0 - dist / distance_threshold_km)
            probability = pred_a["confidence"] * pred_b["confidence"] * proximity_factor

            if probability < min_confidence:
                continue

            # Confidence-weighted midpoint
            total_conf = pred_a["confidence"] + pred_b["confidence"]
            if total_conf == 0:
                weight_a = 0.5
            else:
                weight_a = pred_a["confidence"] / total_conf
            weight_b = 1.0 - weight_a

            meeting_lat = pred_a["latitude"] * weight_a + pred_b["latitude"] * weight_b
            meeting_lon = pred_a["longitude"] * weight_a + pred_b["longitude"] * weight_b

            radius = max(pred_a["radius_km"], pred_b["radius_km"])

            encounters.append(
                {
                    "dow": dow,
                    "hour": hour,
                    "latitude": round(meeting_lat, 6),
                    "longitude": round(meeting_lon, 6),
                    "probability": round(probability, 6),
                    "radius_km": round(radius, 4),
                    "distance_km": round(dist, 4),
                    "evidence_a": pred_a["evidence_count"],
                    "evidence_b": pred_b["evidence_count"],
                }
            )

    encounters.sort(key=lambda e: e["probability"], reverse=True)
    return encounters


def find_hotspot_encounters(
    user_events: Dict[str, List[Dict]],
    top_n: int = 20,
    distance_threshold_km: float = 2.0,
    min_events_per_user: int = 5,
) -> List[Dict]:
    """Find the most likely encounters across all user pairs.

    Takes a dict mapping usernames to their event lists. For every pair where
    both users have at least min_events_per_user events, runs predict_encounters
    and keeps the top 3 results per pair. Returns the top_n overall, sorted by
    probability descending, with user_a and user_b fields added.
    """
    all_encounters: List[Dict] = []

    # Filter users with enough events
    eligible = {
        user: evts for user, evts in user_events.items() if len(evts) >= min_events_per_user
    }

    for user_a, user_b in combinations(sorted(eligible.keys()), 2):
        pair_encounters = predict_encounters(
            eligible[user_a],
            eligible[user_b],
            distance_threshold_km=distance_threshold_km,
        )
        # Keep top 3 per pair
        for enc in pair_encounters[:3]:
            enc["user_a"] = user_a
            enc["user_b"] = user_b
            all_encounters.append(enc)

    all_encounters.sort(key=lambda e: e["probability"], reverse=True)
    return all_encounters[:top_n]

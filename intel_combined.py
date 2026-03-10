# intel_combined.py
"""Fuse vector similarity and graph co-occurrence signals for identity correlation."""

from math import log1p


def compute_combined_score(
    vector_similarity: float,
    graph_co_count: int,
    max_co_count: int,
    alpha: float = 0.6,
) -> float:
    """Return a combined score blending vector similarity with log-normalized graph co-occurrence.

    Parameters
    ----------
    vector_similarity : float
        Cosine similarity between two user embedding vectors (0-1).
    graph_co_count : int
        Number of co-occurrence edges between the two users in the graph.
    max_co_count : int
        Maximum co-occurrence count observed across all user pairs (used for normalization).
    alpha : float
        Weight given to vector similarity (1-alpha goes to graph score). Default 0.6.
    """
    graph_score = log1p(graph_co_count) / log1p(max_co_count) if max_co_count > 0 else 0.0
    return alpha * vector_similarity + (1 - alpha) * graph_score


def classify_relationship(
    vector_similarity: float,
    graph_co_count: int,
    max_co_count: int,
    alpha: float = 0.6,
) -> str:
    """Classify the relationship between two users based on combined scoring.

    Returns one of: SAME_PERSON, CONVOY, SIMILAR_ROUTINE, WEAK_MATCH.
    """
    combined = compute_combined_score(vector_similarity, graph_co_count, max_co_count, alpha)
    cosine_distance = 1 - vector_similarity

    if combined > 0.85 and (cosine_distance < 0.05 or graph_co_count > 20):
        return "SAME_PERSON"
    if combined > 0.6 and graph_co_count > 10 and cosine_distance > 0.2:
        return "CONVOY"
    if cosine_distance < 0.15 and graph_co_count < 3:
        return "SIMILAR_ROUTINE"
    return "WEAK_MATCH"

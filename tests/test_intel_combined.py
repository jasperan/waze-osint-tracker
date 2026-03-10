# tests/test_intel_combined.py
from intel_combined import classify_relationship, compute_combined_score


def test_combined_score():
    """High vector_sim + decent graph co-occurrence should yield score > 0.7."""
    score = compute_combined_score(
        vector_similarity=0.9,
        graph_co_count=15,
        max_co_count=30,
    )
    assert score > 0.7, f"Expected score > 0.7, got {score}"


def test_classify_same_person():
    """Near-identical vectors with high co-occurrence → SAME_PERSON."""
    label = classify_relationship(
        vector_similarity=0.98,
        graph_co_count=25,
        max_co_count=30,
    )
    assert label == "SAME_PERSON"


def test_classify_convoy():
    """Moderate similarity but many co-occurrences → CONVOY."""
    label = classify_relationship(
        vector_similarity=0.5,
        graph_co_count=15,
        max_co_count=30,
    )
    assert label == "CONVOY"


def test_classify_similar_routine():
    """High vector similarity but almost no co-occurrence → SIMILAR_ROUTINE."""
    label = classify_relationship(
        vector_similarity=0.90,
        graph_co_count=1,
        max_co_count=30,
    )
    assert label == "SIMILAR_ROUTINE"

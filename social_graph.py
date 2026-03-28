# social_graph.py
"""Social graph construction, ego-network extraction, and community detection
from Waze co-occurrence data."""

import random
from collections import Counter, defaultdict, deque
from typing import Dict, List

from intel_combined import classify_relationship
from intel_cooccurrence import find_cooccurrences


def build_social_graph(
    events: List[Dict],
    min_cooccurrences: int = 3,
    spatial_threshold_m: float = 500,
    temporal_threshold_s: float = 300,
) -> Dict:
    """Build a social graph from raw Waze events.

    Returns {"nodes": [...], "edges": [...]} where:
      - nodes have {id, event_count, top_type}
      - edges have {source, target, weight, avg_distance_m, avg_time_gap_s, relationship}

    All users that appear in events get a node, even if they have zero edges.
    Edges are created only for pairs meeting the min_cooccurrences threshold.
    """
    if not events:
        return {"nodes": [], "edges": []}

    # Collect per-user stats for node metadata
    user_event_counts: Dict[str, int] = Counter()
    user_type_counts: Dict[str, Counter] = defaultdict(Counter)
    for ev in events:
        u = ev["username"]
        user_event_counts[u] += 1
        rtype = ev.get("report_type", "unknown")
        user_type_counts[u][rtype] += 1

    # Build nodes
    nodes = []
    for username, count in user_event_counts.items():
        top_type = user_type_counts[username].most_common(1)[0][0]
        nodes.append({"id": username, "event_count": count, "top_type": top_type})

    # Find co-occurrences
    cooccurrences = find_cooccurrences(
        events,
        spatial_threshold_m=spatial_threshold_m,
        temporal_threshold_s=temporal_threshold_s,
        min_count=min_cooccurrences,
    )

    # Determine max co-count for relationship classification
    max_co_count = max((c["co_count"] for c in cooccurrences), default=0)

    # Build edges
    edges = []
    for co in cooccurrences:
        # We don't have vector similarity here, so pass 0.0 and let
        # classify_relationship work from the graph signal alone.
        relationship = classify_relationship(
            vector_similarity=0.0,
            graph_co_count=co["co_count"],
            max_co_count=max_co_count,
        )
        edges.append(
            {
                "source": co["user_a"],
                "target": co["user_b"],
                "weight": co["co_count"],
                "avg_distance_m": co["avg_distance_m"],
                "avg_time_gap_s": co["avg_time_gap_s"],
                "relationship": relationship,
            }
        )

    return {"nodes": nodes, "edges": edges}


def get_ego_network(graph: Dict, username: str, depth: int = 2) -> Dict:
    """Extract an ego network around *username* using BFS up to *depth* hops.

    Returns a subgraph dict with the same {"nodes", "edges"} structure,
    containing only the nodes reachable within *depth* hops and their
    interconnecting edges.
    """
    if not graph["nodes"] and not graph["edges"]:
        return {"nodes": [], "edges": []}

    # Build adjacency from edges
    adj: Dict[str, set] = defaultdict(set)
    for edge in graph["edges"]:
        adj[edge["source"]].add(edge["target"])
        adj[edge["target"]].add(edge["source"])

    # BFS
    visited: set = set()
    queue: deque = deque()
    if username not in {n["id"] for n in graph["nodes"]}:
        return {"nodes": [], "edges": []}

    queue.append((username, 0))
    visited.add(username)
    while queue:
        current, d = queue.popleft()
        if d < depth:
            for neighbor in adj[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, d + 1))

    # Build subgraph
    node_lookup = {n["id"]: n for n in graph["nodes"]}
    sub_nodes = [node_lookup[uid] for uid in visited if uid in node_lookup]
    sub_edges = [e for e in graph["edges"] if e["source"] in visited and e["target"] in visited]

    return {"nodes": sub_nodes, "edges": sub_edges}


def detect_communities(graph: Dict) -> Dict[str, int]:
    """Weighted label propagation community detection.

    Each node starts with a unique label. On each iteration, every node
    adopts the label with the highest summed edge weight among its neighbors.
    Ties are broken randomly. Iterates until convergence or max 50 iterations.

    Returns {username: community_id} with 0-based sequential IDs.
    """
    if not graph["nodes"]:
        return {}

    # Build weighted adjacency
    adj: Dict[str, List[tuple]] = defaultdict(list)
    for edge in graph["edges"]:
        adj[edge["source"]].append((edge["target"], edge["weight"]))
        adj[edge["target"]].append((edge["source"], edge["weight"]))

    # Initialize each node with its own label
    labels: Dict[str, str] = {n["id"]: n["id"] for n in graph["nodes"]}
    node_ids = [n["id"] for n in graph["nodes"]]

    for _ in range(50):
        changed = False
        # Shuffle to break ordering bias
        order = list(node_ids)
        random.shuffle(order)

        for node in order:
            if not adj[node]:
                continue

            # Sum weights per neighbor label
            label_weights: Dict[str, float] = defaultdict(float)
            for neighbor, weight in adj[node]:
                label_weights[labels[neighbor]] += weight

            if not label_weights:
                continue

            max_weight = max(label_weights.values())
            candidates = [lbl for lbl, w in label_weights.items() if w == max_weight]
            best = random.choice(candidates)

            if labels[node] != best:
                labels[node] = best
                changed = True

        if not changed:
            break

    # Normalize to 0-based sequential IDs
    unique_labels = sorted(set(labels.values()))
    label_map = {lbl: idx for idx, lbl in enumerate(unique_labels)}
    return {node: label_map[lbl] for node, lbl in labels.items()}

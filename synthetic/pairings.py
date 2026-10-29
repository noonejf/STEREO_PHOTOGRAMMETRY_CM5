"""Labelled branch pairings: the training set for the crossing decision.

`processing/graph_tracer.py` turns the mask's skeleton into a graph and asks
one question at every node: which two of the branches meeting here are the
same strand passing through. Answer them all and the cable reads straight
off the graph. The shipped answer is `_pair_score`, a small function of
tangent agreement and width agreement.

This module produces the data to learn a better one, and the labels are
exact rather than inferred. The generator knows the true centreline, so
walking it over the graph gives the sequence of edges the real cable uses,
and every consecutive pair in that sequence is a true pairing at the node
they share. Every other pair at that node is a negative.

**Why this is a different question from the branch scorer**, which was
measured twice and never paid. That model scored one step of a pixel walk,
and at a crossing the two strands are locally identical, so the evidence it
needed was not in its input. Here the unit is a pair of whole branches and
the features are properties of those branches: the direction each one
leaves the node in, how far it runs before the next node, how thick it is.
Those differ between the right pairing and the wrong one, which is the
whole reason the geometric version already works.
"""
from __future__ import annotations

import numpy as np

FEATURE_NAMES = [
    "straightness",      # -cos between the two tangents; 1 = straight through
    "width_agree",       # 1 - |w1-w2| / (w1+w2)
    "width_mean",        # mean half-width of the two branches, in node widths
    "len_min",           # shorter branch, in wire radii
    "len_max",           # longer branch, in wire radii
    "degree",            # how many branches meet at this node
    "straight_rank",     # 0 = straightest pair at this node, 1 = next, ...
    "straight_margin",   # how far ahead of the next best pair it is
    "node_width",        # distance transform at the node, in wire radii
    "turn_sym",          # |angle(t1) - angle(t2)| symmetry about straight
]
N_FEATURES = len(FEATURE_NAMES)


def pair_features(graph, nid, e1, e2, straight_table=None):
    """Features for the hypothesis "e1 and e2 are one strand through nid"."""
    t1 = graph.tangent_at(e1, nid)
    t2 = graph.tangent_at(e2, nid)
    if not t1.any() or not t2.any():
        return None
    straight = -float(np.dot(t1, t2))
    w1 = graph.width_at(e1, nid)
    w2 = graph.width_at(e2, nid)
    r = max(graph.wire_radius, 1e-6)
    width_agree = 1.0 - abs(w1 - w2) / max(w1 + w2, 1e-6)
    l1 = graph.edge_length(e1) / r
    l2 = graph.edge_length(e2) / r

    rank, margin = 0.0, 0.0
    if straight_table:
        vals = sorted(straight_table.values(), reverse=True)
        here = straight_table.get((min(e1, e2), max(e1, e2)), straight)
        rank = float(vals.index(here)) if here in vals else 0.0
        margin = float(here - vals[1]) if len(vals) > 1 else 1.0

    nx, ny = graph.nodes[nid]["xy"]
    h, w = graph.dt.shape
    node_w = float(graph.dt[int(np.clip(ny, 0, h - 1)),
                            int(np.clip(nx, 0, w - 1))]) / r

    a1 = float(np.arctan2(t1[1], t1[0]))
    a2 = float(np.arctan2(t2[1], t2[0]))
    d = abs(((a1 - a2 + np.pi) % (2 * np.pi)) - np.pi)
    turn_sym = abs(d - np.pi) / np.pi

    return np.array([straight, width_agree, 0.5 * (w1 + w2) / r,
                     min(l1, l2), max(l1, l2),
                     float(len(graph.incident[nid])), rank, margin,
                     node_w, turn_sym], dtype=np.float32)


def true_edge_sequence(graph, path_xy, max_dist_radii=2.0):
    """Which graph edges the true centreline runs along, in order."""
    from scipy.spatial import cKDTree
    pts = np.asarray(path_xy, dtype=np.float32)
    coords, owner = [], []
    for eid, e in enumerate(graph.edges):
        for xy in e["pts"]:
            coords.append(xy)
            owner.append(eid)
    if not coords:
        return []
    tree = cKDTree(np.asarray(coords, np.float32))
    tol = max_dist_radii * graph.wire_radius
    d, idx = tree.query(pts, k=1, distance_upper_bound=tol)
    owner = np.asarray(owner, np.int32)
    seq = []
    for di, ii in zip(d, idx):
        if not np.isfinite(di) or ii >= len(owner):
            continue
        eid = int(owner[ii])
        if not seq or seq[-1] != eid:
            seq.append(eid)
    return seq


def true_pairings(graph, path_xy):
    """``{(node, e1, e2)}`` for every crossing the true cable passes through."""
    seq = true_edge_sequence(graph, path_xy)
    out = set()
    for a, b in zip(seq[:-1], seq[1:]):
        ea, eb = graph.edges[a], graph.edges[b]
        shared = {ea["u"], ea["v"]} & {eb["u"], eb["v"]}
        for nid in shared:
            out.add((nid, min(a, b), max(a, b)))
    return out


def harvest(graph, path_xy):
    """Rows of (features, label) over every candidate pair at every node."""
    truth = true_pairings(graph, path_xy)
    X, y, meta = [], [], []
    for nid, eids in graph.incident.items():
        if len(eids) < 2:
            continue
        table = {}
        for i in range(len(eids)):
            for j in range(i + 1, len(eids)):
                a, b = eids[i], eids[j]
                t1 = graph.tangent_at(a, nid)
                t2 = graph.tangent_at(b, nid)
                if t1.any() and t2.any():
                    table[(min(a, b), max(a, b))] = -float(np.dot(t1, t2))
        for i in range(len(eids)):
            for j in range(i + 1, len(eids)):
                a, b = eids[i], eids[j]
                f = pair_features(graph, nid, a, b, table)
                if f is None:
                    continue
                X.append(f)
                y.append(1 if (nid, min(a, b), max(a, b)) in truth else 0)
                meta.append((nid, a, b))
    if not X:
        return (np.zeros((0, N_FEATURES), np.float32),
                np.zeros((0,), np.int8), [])
    return np.stack(X), np.asarray(y, np.int8), meta

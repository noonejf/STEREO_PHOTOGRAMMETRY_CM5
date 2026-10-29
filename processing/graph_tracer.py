"""Trace the cable by resolving every crossing at once, not one step at a time.

Three tracers now exist and they fail for three different reasons, which is
worth stating plainly before reading the code.

`SmartWireTracker` walks the mask pixel by pixel and chooses a branch at
each crossing from a weighted formula. Its mistakes are local: it commits
to a strand and only discovers the problem much later, if at all.

`geodesic_tracer` finds the globally cheapest curve between the two ends.
That is the right objective for a tensioned tether and the wrong one for a
tangle, and not because of any parameter: a minimal path is the **shortest**
route, while a tangled cable between two nearby ends is a **long** one. No
cost image fixes an objective pointing the wrong way.

This module takes the third formulation, which is the one the curvilinear
network literature uses (Turetken and Fua; see
`Documentation/Investigacion/Trazado_IA/`). The skeleton of the mask is a
graph: nodes where strands meet, edges where the cable runs on its own. A
crossing is not a decision about where to step next, it is a question about
which two of the branches meeting there are the same strand passing
through. Answer that question at every node, and the graph falls apart into
a handful of smooth curves; the cable is then just the one that joins the
two endpoints, read off without any search.

**Why this can beat a per-step scorer when a per-step scorer could not.**
A learned branch scorer was measured twice and never paid. The reason was
not the model: at a crossing the two strands are locally identical, so the
information needed is not in the input. Here the unit of decision is the
pairing of two whole branches, and the evidence is the thing that is
actually different between the right answer and the wrong one: a cable
passing through a crossing continues in the direction it arrived, and keeps
its width. Both are properties of the branches, not of the pixel.

The pairing is scored by `_pair_score`, which is deliberately a small,
readable function of tangent agreement and width agreement. It is the
natural place for a learned model, and the labels are free: the generator
knows the true centreline, so it knows the true pairing at every junction.
That is `synthetic/pairings.py`.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

import cv2
import numpy as np

logger = logging.getLogger(__name__)

try:
    from skimage.morphology import skeletonize
except ImportError:  # pragma: no cover
    skeletonize = None

NEIGH8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

#: How far along a branch to look when measuring the direction it leaves a
#: node in. Too short and the measurement is skeleton noise; too long and a
#: genuinely curving cable looks like it is turning away.
TANGENT_LEN = 14

#: A pairing is only accepted when the two branches are closer to opposite
#: than this. cos(-0.2) is about 100 degrees, so a branch leaving at a right
#: angle is never called a continuation.
MIN_STRAIGHTNESS = 0.2

#: Spurs shorter than this many wire radii are pruning artifacts of the
#: skeletonisation, not branches, and are dropped before anything else.
SPUR_RADII = 2.5

#: How far apart two loose ends may be, in wire radii, and still be joined
#: across the gap. This is what makes the graph usable on real masks. The
#: synthetic benchmark never needed it: its masks come out in one piece 59
#: times in 60. The masks the segmenter produces from camera frames come
#: out in 3, 15 and 26 pieces, and a graph in pieces cannot be walked from
#: one end of the cable to the other at all.
MAX_GAP_RADII = 8.0

#: Width the graph is built at. Skeletonising a 1920x1440 mask and walking
#: its chains costs about four seconds; at 960 it is under one, and the
#: cable is still ten pixels wide there, so nothing that matters is lost.
#: The path is scaled back to the caller's coordinates. Same reasoning and
#: same number as `processing/endpoint_model.py`.
WORK_WIDTH = 960

#: And they are only joined if each one is pointing at the other. A gap is
#: bridged because the cable evidently continues through it, not because
#: two unrelated ends happen to be near each other.
GAP_ALIGN = 0.5


class SkeletonGraph:
    """Nodes where the skeleton branches or ends, edges where it does not."""

    def __init__(self, mask, wire_radius=None, max_gap_radii=MAX_GAP_RADII):
        if skeletonize is None:
            raise RuntimeError("scikit-image is required for the graph tracer")
        self.binary = (mask > 127).astype(np.uint8) if mask.max() > 1 \
            else (mask > 0).astype(np.uint8)
        self.skel = skeletonize(self.binary > 0).astype(np.uint8)
        dt = cv2.distanceTransform(self.binary, cv2.DIST_L2, 5)
        self.dt = dt
        self.wire_radius = float(wire_radius if wire_radius is not None
                                 else max(np.median(dt[self.skel > 0]) if
                                          (self.skel > 0).any() else 3.0, 1.0))
        self._build()
        self.bridges = self._bridge_gaps(max_gap_radii)

    # -- construction ----------------------------------------------------
    def _neighbour_count(self, skel):
        k = np.ones((3, 3), np.float32)
        k[1, 1] = 0
        return (cv2.filter2D(skel.astype(np.float32), -1, k) * skel)

    def _build(self):
        skel = self.skel
        self._walk_budget = int(skel.sum()) + 8
        nb = self._neighbour_count(skel)
        # a node pixel is an end (1 neighbour) or a branch point (3 or more).
        # Adjacent branch pixels are one node, so they are labelled together.
        node_px = ((skel > 0) & ((nb < 1.5) | (nb > 2.5))).astype(np.uint8)

        # Merge branch points that sit within about a wire width of each
        # other. This is not a tidy-up, it is what makes the pairing
        # possible at all. Thinning does not turn a crossing of a cable
        # with real width into one X node: it produces two T nodes a few
        # pixels apart, joined by a stub. Measured on the mask that
        # prompted this module, 27 nodes of degree 3 and only 3 of degree
        # 4, with the shortest edges 3 to 6 pixels long at a wire radius
        # of 4.4. A degree-3 node has no pair to make, so the walk dies at
        # the first crossing. Dilating the branch pixels before labelling
        # glues each split crossing back into the single degree-4 node it
        # physically is. Ends (degree 1) are never dilated, or two nearby
        # tips would fuse into one.
        branch_px = ((skel > 0) & (nb > 2.5)).astype(np.uint8)
        r = max(1, int(round(1.3 * self.wire_radius)))
        if branch_px.any():
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
            grown = cv2.dilate(branch_px, k) & (skel > 0)
            node_px = np.maximum(node_px, grown.astype(np.uint8))
        n_lab, lab = cv2.connectedComponents(node_px, connectivity=8)
        self.node_label = lab
        # One pass over the node pixels, grouped by label. This used to be
        # np.nonzero(lab == i) inside the loop, which scans the whole
        # 1920x1440 frame once per node: 92 nodes, 11.4 of the 18.4
        # seconds the graph took to build on a real mask. The result is
        # identical, it just stops re-reading the image 92 times.
        self.nodes = {}
        nys, nxs = np.nonzero(node_px)
        if len(nys):
            nlabs = lab[nys, nxs]
            order = np.argsort(nlabs, kind="stable")
            nys, nxs, nlabs = nys[order], nxs[order], nlabs[order]
            bounds = np.flatnonzero(np.diff(nlabs)) + 1
            for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(nlabs)]):
                i = int(nlabs[a])
                if i == 0:
                    continue
                xs, ys = nxs[a:b], nys[a:b]
                self.nodes[i] = {"xy": (float(xs.mean()), float(ys.mean())),
                                 "px": list(zip(xs.tolist(), ys.tolist())),
                                 "degree": 0}

        h, w = skel.shape
        self.edges = []                 # each: dict(u, v, pts)
        self.incident = defaultdict(list)
        seen = set()

        for nid, node in self.nodes.items():
            for (sx, sy) in node["px"]:
                for dx, dy in NEIGH8:
                    x, y = sx + dx, sy + dy
                    if not (0 <= x < w and 0 <= y < h) or not skel[y, x]:
                        continue
                    if lab[y, x] == nid:
                        continue
                    key = (nid, sx, sy, x, y)
                    if key in seen:
                        continue
                    pts, end_node = self._walk(x, y, (sx, sy), lab, nid)
                    if end_node is None:
                        continue
                    rev = (end_node, pts[-1][0], pts[-1][1],
                           pts[-2][0] if len(pts) > 1 else sx,
                           pts[-2][1] if len(pts) > 1 else sy)
                    seen.add(key)
                    seen.add(rev)
                    eid = len(self.edges)
                    self.edges.append({"u": nid, "v": end_node,
                                       "pts": [(sx, sy)] + pts})
                    self.incident[nid].append(eid)
                    if end_node != nid:
                        self.incident[end_node].append(eid)
                    else:
                        self.incident[nid].append(eid)   # self loop, twice

        for nid in self.nodes:
            self.nodes[nid]["degree"] = len(self.incident[nid])

    def _bridge_gaps(self, max_gap_radii):
        """Join loose ends that are evidently the same cable across a gap.

        A broken mask gives a broken graph, and a broken graph has no path
        from one end of the cable to the other, so the tracer returns
        whatever fragment it started in. Measured on six real frames, the
        segmenter's masks came out in 1, 3, 7, 9, 15 and 26 pieces.

        Two conditions, both necessary. The ends have to be close, within
        ``max_gap_radii`` wire radii, and each has to be **pointing at the
        other**: the cable arrives at the first end heading towards the
        second, and vice versa. Distance alone would staple together two
        unrelated strands that happen to pass near each other, which is the
        same mistake as the geodesic's shortcut, and it is worse here
        because a wrong bridge is invisible afterwards.
        """
        if max_gap_radii <= 0:
            return 0
        tips = [nid for nid, e in self.incident.items() if len(e) == 1]
        if len(tips) < 2:
            return 0
        max_gap = max_gap_radii * self.wire_radius
        added = 0
        for i in range(len(tips)):
            for j in range(i + 1, len(tips)):
                u, v = tips[i], tips[j]
                pu = np.array(self.nodes[u]["xy"], np.float32)
                pv = np.array(self.nodes[v]["xy"], np.float32)
                d = float(np.linalg.norm(pv - pu))
                if d < 1e-6 or d > max_gap:
                    continue
                # the tangent at a tip points INTO the cable, so the cable
                # continues past the tip along its negative
                tu = -self.tangent_at(self.incident[u][0], u)
                tv = -self.tangent_at(self.incident[v][0], v)
                if not tu.any() or not tv.any():
                    continue
                uv = (pv - pu) / d
                if float(np.dot(tu, uv)) < GAP_ALIGN:
                    continue
                if float(np.dot(tv, -uv)) < GAP_ALIGN:
                    continue
                n = max(2, int(round(d)))
                pts = [(int(round(pu[0] + (pv[0] - pu[0]) * t / n)),
                        int(round(pu[1] + (pv[1] - pu[1]) * t / n)))
                       for t in range(n + 1)]
                eid = len(self.edges)
                self.edges.append({"u": u, "v": v, "pts": pts,
                                   "bridge": True})
                self.incident[u].append(eid)
                self.incident[v].append(eid)
                self.nodes[u]["degree"] = len(self.incident[u])
                self.nodes[v]["degree"] = len(self.incident[v])
                added += 1
        return added

    def _walk(self, x, y, came_from, lab, start_node):
        """Follow a degree-2 chain until another node pixel is reached."""
        h, w = self.skel.shape
        pts = [(x, y)]
        prev = came_from
        cur = (x, y)
        # Bounded by the skeleton, not by the image. It used to be
        # self.skel.size, which is 2.7 million on a 1920x1440 frame, and a
        # closed loop of degree-2 pixels with no node on it never hits a
        # return, so each one spun the full bound. That single wrong
        # constant was 18 of the 18.4 seconds the graph took to build on a
        # real mask; real masks have such loops because the segmenter
        # leaves small closed blobs.
        for _ in range(self._walk_budget):
            if lab[cur[1], cur[0]] > 0 and lab[cur[1], cur[0]] != start_node:
                return pts, int(lab[cur[1], cur[0]])
            if lab[cur[1], cur[0]] == start_node and len(pts) > 2:
                return pts, start_node
            nxt = None
            for dx, dy in NEIGH8:
                nx_, ny_ = cur[0] + dx, cur[1] + dy
                if not (0 <= nx_ < w and 0 <= ny_ < h) or not self.skel[ny_, nx_]:
                    continue
                if (nx_, ny_) == prev:
                    continue
                nxt = (nx_, ny_)
                if lab[ny_, nx_] > 0:
                    break
            if nxt is None:
                return pts, None
            prev = cur
            cur = nxt
            pts.append(cur)
        return pts, None

    # -- geometry --------------------------------------------------------
    def edge_length(self, eid):
        return len(self.edges[eid]["pts"])

    def tangent_at(self, eid, nid, length=TANGENT_LEN):
        """Unit vector pointing away from node ``nid`` along edge ``eid``."""
        e = self.edges[eid]
        pts = e["pts"]
        if e["u"] == nid and e["v"] == nid:
            # a self loop leaves the node twice; use whichever end is asked
            pass
        if e["v"] == nid and e["u"] != nid:
            pts = pts[::-1]
        n = min(len(pts) - 1, max(2, length))
        if n < 1:
            return np.zeros(2, np.float32)
        a = np.array(pts[0], np.float32)
        b = np.array(pts[n], np.float32)
        v = b - a
        nrm = float(np.linalg.norm(v))
        return v / nrm if nrm > 1e-6 else np.zeros(2, np.float32)

    def width_at(self, eid, nid, length=TANGENT_LEN):
        e = self.edges[eid]
        pts = e["pts"] if e["v"] != nid or e["u"] == nid else e["pts"][::-1]
        take = pts[:max(2, min(len(pts), length))]
        vals = [self.dt[y, x] for x, y in take]
        return float(np.median(vals)) if vals else 0.0


def _pair_score(graph, nid, e1, e2):
    """How much two branches at a node look like one strand passing through.

    Straightness dominates: a cable through a crossing leaves in the
    direction it arrived, so the two tangents point opposite ways and their
    dot product is near -1. Width is the tiebreaker, because the two strands
    at a crossing are usually at different depths and so different apparent
    thicknesses.
    """
    t1 = graph.tangent_at(e1, nid)
    t2 = graph.tangent_at(e2, nid)
    if not t1.any() or not t2.any():
        return -1.0
    straight = -float(np.dot(t1, t2))        # 1.0 when exactly opposite
    if straight < MIN_STRAIGHTNESS:
        return -1.0
    w1 = graph.width_at(e1, nid)
    w2 = graph.width_at(e2, nid)
    width_agree = 1.0 - abs(w1 - w2) / max(w1 + w2, 1e-6)
    return float(straight + 0.25 * width_agree)


def pair_branches(graph, score_fn=_pair_score):
    """Decide, at every node, which branches are the same strand.

    Greedy over the best-scoring pair first, which for the degrees that
    occur here (mostly 3 and 4) is the maximum weight matching anyway.
    Returns ``{(node, edge): partner_edge}``.
    """
    # collect every candidate first, so a learned scorer can be called once
    # instead of once per pair; sklearn's per-call overhead dominates here
    items = []
    for nid, eids in graph.incident.items():
        if len(eids) < 2:
            continue
        for i in range(len(eids)):
            for j in range(i + 1, len(eids)):
                items.append((nid, eids[i], eids[j]))

    batched = getattr(score_fn, "__self__", None)
    scores = None
    if batched is not None and hasattr(batched, "score_many"):
        scores = batched.score_many(graph, items)
    by_node = {}
    for k, (nid, a, b) in enumerate(items):
        sc = scores[k] if scores is not None else score_fn(graph, nid, a, b)
        if sc > 0:
            by_node.setdefault(nid, []).append((sc, a, b))

    pairing = {}
    for nid, cand in by_node.items():
        cand.sort(reverse=True)
        used = set()
        for s, a, b in cand:
            if a in used or b in used:
                continue
            used.add(a)
            used.add(b)
            pairing[(nid, a)] = b
            pairing[(nid, b)] = a
    return pairing


def _nearest_edge(graph, xy):
    best, bd = None, 1e18
    for eid, e in enumerate(graph.edges):
        pts = np.asarray(e["pts"], np.float32)
        d = np.min((pts[:, 0] - xy[0]) ** 2 + (pts[:, 1] - xy[1]) ** 2)
        if d < bd:
            bd, best = d, eid
    return best, float(np.sqrt(bd))


def _nearest_node(graph, xy):
    best, bd = None, 1e18
    for nid, nd in graph.nodes.items():
        px = np.asarray(nd["px"], np.float32)
        d = np.min((px[:, 0] - xy[0]) ** 2 + (px[:, 1] - xy[1]) ** 2)
        if d < bd:
            bd, best = d, nid
    return best, float(np.sqrt(bd))


def _seeds(graph, xy):
    """Every (edge, node-to-leave-from) a walk could start at.

    The endpoint is a pixel, and after the crossings are merged it can sit
    inside a node rather than on an edge, so seeding only from the nearest
    edge loses the start entirely. Both cases are enumerated and the caller
    keeps whichever walk turns out best.
    """
    out = []
    eid, ed = _nearest_edge(graph, xy)
    nid, nd = _nearest_node(graph, xy)
    if nid is not None and nd <= ed + 1e-6:
        for e in graph.incident[nid]:
            out.append((e, nid))
    if eid is not None:
        e = graph.edges[eid]
        out.append((eid, e["u"]))
        if e["v"] != e["u"]:
            out.append((eid, e["v"]))
    seen, uniq = set(), []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def _ordered_continuations(graph, node, eid, pairing, visited):
    """Branches to try on leaving ``node``, best first.

    The pairing decided at this node comes first: it is the answer to the
    question "which branch is this same strand". Everything else follows in
    order of how straight it would be, because at the messy nodes, where
    thinning merged more than two strands and no clean pair exists,
    carrying straight on is still the best guess available.

    Returning a list rather than one choice is the point. With a few dozen
    edges the tracer can afford to be wrong and come back, which it cannot
    afford over tens of thousands of pixels.
    """
    out = []
    nxt = pairing.get((node, eid))
    if nxt is not None and nxt not in visited:
        out.append(nxt)
    t_in = -graph.tangent_at(eid, node)       # direction of travel, arriving
    rest = []
    for cand in graph.incident[node]:
        if cand == eid or cand in visited or cand in out:
            continue
        t_out = graph.tangent_at(cand, node)
        rest.append((float(np.dot(t_in, t_out)), cand))
    rest.sort(reverse=True)
    out.extend(c for _, c in rest)
    return out


def _search(graph, seeds, pairing, target_edges, target_nodes,
            max_expand=40000, time_budget_s=3.0):
    """Depth-first over the edge graph, keeping the best path to the end.

    "Best" is the one that **covers the most cable**, measured as the total
    length of the edges it uses, not the shortest. That is the opposite of
    the geodesic tracer's objective and it is deliberate: between two ends
    of a tangled cable the true route is the long one, and the short one is
    the mistake. Reaching the far endpoint always beats not reaching it.

    The search is exhaustive up to ``max_expand`` expansions, which a graph
    of a few dozen edges reaches only in the worst tangles. The pairing is
    what keeps it cheap in practice: it is tried first at every node, so
    the first path found is usually already the right one and everything
    after it is confirmation.
    """
    # A wall-clock budget as well as an expansion cap. On three of the
    # twenty real frames the expansion cap alone let the search run 15 to
    # 18 seconds, which is not a number to hand an operator waiting on a
    # mask. The search keeps its best answer so far, so stopping early
    # degrades the result instead of losing it.
    best = None
    expand = 0
    deadline = time.time() + time_budget_s if time_budget_s else None
    for eid0, node0 in seeds:
        e0 = graph.edges[eid0]
        far0 = e0["v"] if e0["u"] == node0 else e0["u"]
        stack = [(eid0, far0, (eid0,), graph.edge_length(eid0))]
        while stack:
            eid, node, used, length = stack.pop()
            expand += 1
            if expand > max_expand:
                break
            if deadline is not None and not (expand & 1023)                     and time.time() > deadline:
                expand = max_expand + 1
                break
            if eid in target_edges or node in target_nodes:
                cand = (True, length, used)
                if best is None or cand[:2] > best[:2]:
                    best = cand
                continue
            nxts = _ordered_continuations(graph, node, eid, pairing, set(used))
            if not nxts:
                cand = (False, length, used)
                if best is None or cand[:2] > best[:2]:
                    best = cand
                continue
            # pushed in reverse so the preferred branch is explored first
            for nxt in reversed(nxts):
                e = graph.edges[nxt]
                far = e["v"] if e["u"] == node else e["u"]
                stack.append((nxt, far, used + (nxt,),
                              length + graph.edge_length(nxt)))
        if expand > max_expand:
            break
    return best, expand


def _attach(pts, start, end):
    """Make the chain begin at ``start`` and finish at ``end``."""
    if not pts:
        return pts
    s = (int(start[0]), int(start[1]))
    e = (int(end[0]), int(end[1]))
    d0 = (pts[0][0] - s[0]) ** 2 + (pts[0][1] - s[1]) ** 2
    dn = (pts[-1][0] - s[0]) ** 2 + (pts[-1][1] - s[1]) ** 2
    if dn < d0:
        pts = pts[::-1]
    if (pts[0][0], pts[0][1]) != s:
        pts = [s] + list(pts)
    if (pts[-1][0], pts[-1][1]) != e:
        pts = list(pts) + [e]
    return pts


def _stitch(graph, used, first_node):
    """Turn a sequence of edge ids into one chain of pixels."""
    pts = []
    node = first_node
    for i, eid in enumerate(used):
        e = graph.edges[eid]
        seg = list(e["pts"]) if e["u"] == node else list(e["pts"])[::-1]
        if i and pts and seg and pts[-1] == seg[0]:
            seg = seg[1:]
        pts.extend(seg)
        node = e["v"] if e["u"] == node else e["u"]
    return pts


def default_score_fn():
    """The learned pairing model when it is available, geometry otherwise.

    Unlike the other two learned components in this repo, this one is on by
    default, because unlike them it won the end-to-end measurement: 97.1
    against 95.4, and 98.1 against 90.4 on knots. `processing/pair_model.py`
    still refuses to load a pickle that did not record beating the rule,
    and `LINKU_PAIR_MODEL=0` forces the rule back.
    """
    try:
        from processing.pair_model import get_scorer
        scorer = get_scorer()
    except Exception:                       # noqa: BLE001
        scorer = None
    if scorer is None:
        return _pair_score
    return scorer.score


def trace(mask, start, end, wire_radius=None, score_fn=None,
          max_expand=40000, time_budget_s=3.0, work_width=WORK_WIDTH):
    """Resolve every crossing, then read the cable off the graph.

    ``start`` and ``end`` are (x, y). Returns ``(path, info)``.
    ``info['reached']`` says whether the path arrived at the far endpoint;
    when it did not, the pairing is wrong somewhere and the caller should
    keep whatever its own tracer produced.
    """
    h0, w0 = mask.shape[:2]
    scale = 1.0
    if work_width and w0 > work_width:
        scale = work_width / float(w0)
        mask = cv2.resize(mask, (work_width, max(2, int(round(h0 * scale)))),
                          interpolation=cv2.INTER_NEAREST)
        start = (start[0] * scale, start[1] * scale)
        end = (end[0] * scale, end[1] * scale)
        if wire_radius is not None:
            wire_radius = wire_radius * scale

    graph = SkeletonGraph(mask, wire_radius)
    info = {"nodes": len(graph.nodes), "edges": len(graph.edges),
            "bridges": graph.bridges, "scale": scale}
    if not graph.edges:
        return None, info

    if score_fn is None:
        score_fn = default_score_fn()
    info["scorer"] = ("learned" if score_fn is not _pair_score
                      else "geometric")
    pairing = pair_branches(graph, score_fn)
    info["pairings"] = len(pairing) // 2

    end_seeds = _seeds(graph, end)
    target_edges = {e for e, _ in end_seeds}
    target_nodes = set()
    nid, nd = _nearest_node(graph, end)
    _, ed = _nearest_edge(graph, end)
    if nid is not None and nd <= ed + 1e-6:
        target_nodes.add(nid)

    seeds = _seeds(graph, start)
    best, expand = _search(graph, seeds, pairing, target_edges, target_nodes,
                           max_expand, time_budget_s)
    info["expansions"] = expand
    if best is None:
        return None, info

    reached, length, used = best
    # the walk left the first edge at whichever of its nodes is not the one
    # the seed started from, so recover that orientation for the stitch
    e0 = graph.edges[used[0]]
    seed_node = None
    for eid, node in seeds:
        if eid == used[0]:
            seed_node = node
            break
    if seed_node is None:
        seed_node = e0["u"]
    pts = _stitch(graph, used, seed_node)

    binary = graph.binary
    cov = np.zeros_like(binary)
    r = int(max(2, round(graph.wire_radius)))
    for x, y in pts:
        cv2.circle(cov, (int(x), int(y)), r, 1, -1)
    # The graph only knows about skeleton pixels, and the endpoints the
    # detector hands over are not always on the skeleton: after the
    # crossings are merged, a tip can sit inside a node. Without this the
    # path stops a few pixels short at both ends, which costs nothing on a
    # tangle and showed up as 99.9 instead of 100.0 on a catenary, where
    # there is nothing else to lose.
    pts = _attach(pts, start, end)

    info["reached"] = bool(reached)
    info["edges_used"] = len(used)
    info["mask_coverage"] = round(
        float(((cov > 0) & (binary > 0)).sum()) / max(int(binary.sum()), 1), 3)
    if len(pts) < 2:
        return None, info
    if scale != 1.0:
        inv = 1.0 / scale
        out, seen = [], set()
        for x, y in pts:
            q = (int(round(x * inv)), int(round(y * inv)))
            if q not in seen:
                seen.add(q)
                out.append(q)
        pts = out
    return [(int(x), int(y)) for x, y in pts], info


#: A path may reach the far endpoint and still have skipped most of the
#: cable, when the pairing sent it down a shortcut that happens to arrive.
#: Reaching is therefore necessary and not sufficient, and a path that
#: covers less than this fraction of the mask is reported as a failure so
#: the caller falls back. Measured on real frames: one case reached the
#: end having covered 0.9% of the mask, and another covered 37% where the
#: DFS covered twice as much of the hand-drawn cable.
MIN_MASK_COVERAGE = 0.45


def track_wire(mask, start, end, wire_radius=None,
               min_coverage=MIN_MASK_COVERAGE, **kw):
    """`SmartWireTracker.track_wire`'s result contract, graph tracer inside.

    Returns the same dictionary the GUI and `StereoProcessor` already
    consume, so a caller can swap tracers without touching anything
    downstream. ``success`` is False when the path did not reach the far
    endpoint, which is the caller's signal to fall back.
    """
    path, info = trace(mask, start, end, wire_radius=wire_radius, **kw)
    cov = float(info.get("mask_coverage", 0.0))
    ok = bool(path) and bool(info.get("reached")) and cov >= min_coverage
    info["rejected_for"] = (None if ok else
                            ("no path" if not path else
                             "did not reach the far endpoint"
                             if not info.get("reached") else
                             f"covered only {100 * cov:.0f}% of the mask"))
    return {
        "success": ok,
        "path": path or [],
        "coverage": float(info.get("mask_coverage", 0.0)),
        "dt_profile": [],
        "decision_points_2d": [],
        "tracer": "graph",
        "graph_info": info,
    }

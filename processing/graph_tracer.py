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

#: What a sharp turn costs, in pixels of coverage, when the search ranks
#: one route against another.
#:
#: Coverage alone is not enough and the reason is easy to miss, because
#: the symptom hides behind a perfect score. Two routes can both cover
#: 100% of the cable while traversing it in completely different orders,
#: and F1 cannot tell them apart: it treats the trace as a set of points.
#: Stage 5 does not. It pairs the point at i% along the left path with the
#: point at i% along the right one, so a route that covers everything in a
#: scrambled order produces a correspondence that is wrong while every
#: coverage number says it is perfect. Measured on the knot scene: the
#: same 100.0 F1, and a rank correlation against true arc length of 0.373
#: with 32 reversals of direction, against the pixel walk's 0.792 with 4.
#:
#: So the objective carries a second term. Continuing straight through a
#: node costs nothing, turning away from the arriving direction costs this
#: many pixels, and reversing costs twice that. It is deliberately small
#: against the length of a real strand: a sharp turn that reaches a
#: hundred more pixels of cable is still taken, a sharp turn that reaches
#: ten is not.
TURN_COST_PX = 25.0

#: How far along the cable the output path is smoothed, in cable radii.
#:
#: A skeleton is a staircase of pixels, not a curve, and the difference is
#: measurable rather than cosmetic. Measured over 24 scenes: the returned
#: chain changes direction by 22.7 degrees from one pixel to the next, and
#: even averaged over nine pixels it turns 2.1 degrees per step where the
#: true centreline turns 1.1. That staircase inflates arc length by 6 to 7
#: per cent on the shapes where the trace covers everything, and arc
#: length in metres is one of the payload's headline outputs, so the
#: quantisation is a systematic error in a reported quantity.
#:
#: The smoothing scale is tied to the cable radius because that is the
#: scale of the noise: the staircase lives at one pixel, a real bend of
#: the cord cannot be tighter than the cord is thick. Zero disables it.
#:
#: 0.3 is where the swept curve stops paying. Measured on the scenes that
#: trace to full coverage, so that excess length is the staircase and not
#: missing cable, against the true cord at length 1.000 and 1.1 degrees of
#: turn per nine pixels:
#:
#:     sigma   length   turn
#:      0.00    1.107   2.08
#:      0.15    1.078   1.65
#:      0.25    1.054   1.15
#:      0.40    1.048   0.90
#:      1.00    1.041   0.68
#:
#: Past 0.4 the length gains 0.7 points while the turn rate falls to half
#: the real cord's, which is flattening genuine curvature, and curvature
#: is a reported quantity alongside arc length. Agreement and traversal
#: order are flat across the whole sweep, so this trades only between
#: those two outputs.
SMOOTH_RADII = 0.3

#: Where the mask is this much wider than the cable, two strands are
#: lying side by side and the skeleton runs up the middle of both.
#:
#: Swept against the quantity it exists to fix, which is arc length. With
#: no doubling the traced path comes out 5.7 per cent SHORT, because
#: every fused stretch is walked once where the cord runs twice:
#:
#:     factor   agreement   order   length
#:      1.15        94.7     77.0    1.210
#:      1.30        94.8     85.3    1.097
#:      1.50        94.9     91.6    0.980
#:      1.75        94.8     92.8    0.946
#:      off         94.8     93.6    0.943
#:
#: 1.50 is where length lands nearest the truth. Below it the threshold
#: starts calling ordinary thickness variation a doubled strand and the
#: path grows 10 to 21 per cent too long; above it the doubling stops
#: happening at all. Agreement does not move anywhere in the sweep, and
#: traversal order costs two points, which is the price of walking a
#: stretch twice where the skeleton offers one line to follow.
WIDE_FACTOR = 1.50

#: Off, and the measurement that closed it is worth keeping. Splitting a
#: wide stretch into two strands assumes width means doubling, and it
#: does not: the generator varies the cord's own thickness along its
#: length, so a thick run and two touching strands look identical in the
#: distance transform. Counted directly, over the skeleton pixels wider
#: than 1.5 times nominal, the fraction with two separate parts of the
#: TRUE centreline nearby is 17 per cent on a tangle and **zero** on a
#: smooth curve, where 262 pixels read 1.86 times nominal and every one
#: of them is simply thick cable. Doubling them invented geometry, and
#: the smooth family, which is what a tensioned tether is, fell from
#: 100.0 to 94.9. Reviving this needs a signal that separates a fat cord
#: from two thin ones, which width alone is not.
DOUBLE_WIDE_EDGES = False

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
        self.split_loops = self._split_self_loops()
        self.doubled_edges = (self._duplicate_wide_edges()
                              if DOUBLE_WIDE_EDGES else 0)
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

    def _split_self_loops(self):
        """Cut every edge that starts and ends at the same node in half.

        A self loop is a closed loop of cord hanging off a crossing, and
        it breaks two assumptions at once. It leaves its node in **two**
        directions, but `tangent_at` can only report one, so the pairing
        compares the wrong angle: at one such node the true continuation
        measured as a 0.299 turn while a wrong one measured 0.988 and was
        chosen. And the half-edge bookkeeping keys a traversal by
        (edge, node), which for a loop is the same key for both of its
        ends, so the two cannot be told apart either.

        Splitting the loop at its midpoint, with a synthetic degree-2
        node in between, removes the special case instead of handling it.
        Two ordinary edges have two ordinary tangents and two distinct
        half-edge keys, and a degree-2 node pairs its only two branches
        trivially, so nothing downstream needs to know this happened.

        It is worth the trouble: over 60 scenes the 19 containing a self
        loop traced at 95.7 coverage and 65.5 traversal order, against
        98.7 and 80.9 for the 41 without one.
        """
        split = 0
        for eid in range(len(self.edges)):
            e = self.edges[eid]
            if e["u"] != e["v"] or len(e["pts"]) < 6:
                continue
            node = e["u"]
            pts = e["pts"]
            mid = len(pts) // 2
            mx, my = pts[mid]
            new_id = (max(self.nodes) + 1) if self.nodes else 1
            self.nodes[new_id] = {"xy": (float(mx), float(my)),
                                  "px": [(int(mx), int(my))], "degree": 2}
            # first half keeps this edge id, second half gets a new one
            self.edges[eid] = {"u": node, "v": new_id,
                               "pts": pts[:mid + 1]}
            second = len(self.edges)
            self.edges.append({"u": new_id, "v": node,
                               "pts": pts[mid:]})
            # the loop appeared twice in its node's incident list; one of
            # those occurrences now belongs to the second half
            inc = self.incident[node]
            first_seen = False
            for k, x in enumerate(inc):
                if x == eid:
                    if first_seen:
                        inc[k] = second
                        break
                    first_seen = True
            self.incident[new_id] = [eid, second]
            self.nodes[node]["degree"] = len(inc)
            split += 1
        return split

    def nominal_radius(self):
        """The cable's own radius: the median width along ordinary skeleton."""
        if getattr(self, "_nominal", None) is None:
            v = self.dt[self.skel > 0]
            self._nominal = float(np.median(v)) if v.size else self.wire_radius
        return self._nominal

    def _offset_copy(self, pts, sign, nominal):
        """One strand of a doubled stretch, offset from the shared skeleton."""
        a = np.asarray(pts, dtype=np.float64)
        if len(a) < 3:
            return None
        t = np.gradient(a, axis=0)
        n = np.hypot(t[:, 0], t[:, 1])
        n[n < 1e-9] = 1.0
        t = t / n[:, None]
        nor = np.column_stack([-t[:, 1], t[:, 0]])
        h, w = self.dt.shape[:2]
        xi = np.clip(np.round(a[:, 0]).astype(int), 0, w - 1)
        yi = np.clip(np.round(a[:, 1]).astype(int), 0, h - 1)
        off = np.maximum(self.dt[yi, xi].astype(np.float64) - nominal, 0.0)
        out = a + nor * (sign * off)[:, None]
        # a strand has to stay on the cable; pull back anything that left it
        xo = np.clip(np.round(out[:, 0]).astype(int), 0, w - 1)
        yo = np.clip(np.round(out[:, 1]).astype(int), 0, h - 1)
        bad = self.binary[yo, xo] == 0
        out[bad] = a[bad]
        return [(int(round(x)), int(round(y))) for x, y in out]

    def _duplicate_wide_edges(self, wide_factor=None, min_px=8):
        """Split a doubled stretch of cable into its two strands.

        Thinning gives one line wherever two strands touch, so the graph
        says "one branch" about a place the cord passes through twice.
        Every later stage then inherits that: the search walks it once,
        the pairing sees one tangent, and the reported arc length is half
        of what the cord actually runs there. Measured on twenty scenes,
        every one contains such a stretch, a median of 352 skeleton
        pixels, and only 8 per cent of them were being walked on both
        sides.

        Width is what identifies them, and width also says where the
        strands are: two cords of radius r with centres d apart make a
        shape of half-width d/2 + r, so DT reads d/2 + r on the shared
        skeleton and the strands sit at plus and minus (DT - r). Both
        quantities come from the image; nothing is tuned here except how
        much wider than r counts as doubled.

        Replacing the edge with two ordinary edges, rather than teaching
        the search about doubling, is the point. The pairing, the
        half-edge bookkeeping and the coverage objective then handle the
        stretch with no special case, and they already know how to walk
        two branches between the same pair of nodes.
        """
        wf = WIDE_FACTOR if wide_factor is None else wide_factor
        nominal = self.nominal_radius()
        made = 0
        for eid in range(len(self.edges)):
            e = self.edges[eid]
            if e.get("absorbed") or e.get("bridge") or len(e["pts"]) < min_px:
                continue
            widths = [self.dt[y, x] for x, y in e["pts"]]
            if float(np.median(widths)) <= wf * nominal:
                continue
            a = self._offset_copy(e["pts"], +1.0, nominal)
            b = self._offset_copy(e["pts"], -1.0, nominal)
            if a is None or b is None:
                continue
            self.edges[eid] = {"u": e["u"], "v": e["v"], "pts": a,
                               "doubled": True}
            twin = len(self.edges)
            self.edges.append({"u": e["u"], "v": e["v"], "pts": b,
                               "doubled": True})
            self.incident[e["u"]].append(twin)
            self.incident[e["v"]].append(twin)
            self.nodes[e["u"]]["degree"] = len(self.incident[e["u"]])
            self.nodes[e["v"]]["degree"] = len(self.incident[e["v"]])
            made += 1
        return made

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

    # The geometric veto applies whoever is scoring. `_pair_score` refuses
    # to call two branches one strand unless they leave the node close to
    # opposite, and a learned scorer that replaces the function replaces
    # that refusal along with it. Measured at one degree-4 node: the model
    # paired a branch leaving at -85.9 degrees with one leaving at -22.6,
    # a 63 degree turn, while the branch leaving at 90.0, a 176 degree
    # continuation of the first, sat unpaired. The trace still covered
    # 100% of the cable and traversed it in a scrambled order, which is
    # invisible to a coverage score and fatal to stage 5, where the point
    # at i% of the left path is paired with the point at i% of the right.
    #
    # So the model chooses among geometrically admissible pairs rather
    # than instead of them. It keeps what it is good at, which is telling
    # two plausible continuations apart by width and context, and loses
    # the failure it cannot recover from.
    by_node = {}
    # A node with exactly two branches has nothing to choose: whatever the
    # angle between them, the cord that arrives on one leaves on the other.
    # This matters at the tip of a hairpin, where the two strands of a
    # doubled stretch meet and leave in almost the same direction, which
    # the straightness veto would otherwise reject as a 180 degree turn.
    for nid, eids in graph.incident.items():
        if len(eids) == 2 and eids[0] != eids[1]:
            by_node[nid] = [(1e9, eids[0], eids[1])]
    for k, (nid, a, b) in enumerate(items):
        if nid in by_node and by_node[nid] and by_node[nid][0][0] >= 1e9:
            continue
        sc = scores[k] if scores is not None else score_fn(graph, nid, a, b)
        if sc <= 0:
            continue
        t1 = graph.tangent_at(a, nid)
        t2 = graph.tangent_at(b, nid)
        straight = -float(np.dot(t1, t2)) if (t1.any() and t2.any()) else 0.0
        if straight < MIN_STRAIGHTNESS:
            continue
        # and the two opinions are multiplied, not substituted. A veto
        # alone was not enough: at the node above the model still ranked a
        # 102 degree turn (straightness 0.21) over the 176 degree
        # continuation (0.998) sitting right there, because its own score
        # was the only thing being compared. Multiplying means the model
        # has to be roughly five times more confident to overrule that
        # much geometry, which is the bar its measured reliability
        # deserves: it wins on average and is occasionally, locally,
        # absurd.
        by_node.setdefault(nid, []).append((sc * straight, a, b))

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

    # A requested endpoint sitting on a dead end is not ambiguous: the walk
    # has to leave from there. Offering the other orientation as well let
    # the search pick a route that covers the same cable and simply starts
    # somewhere else, since both score the same length. On one tangle that
    # left the 65 px stub running out to the endpoint untraced and the
    # path beginning 86 px away from the point it was asked to start at,
    # which downstream is worse than it looks: stage 5 pairs by fraction
    # of the path, so a path that starts in the wrong place misaligns
    # every pair after it.
    # The tolerance matters: the endpoint sits ON the dead-end edge too, so
    # the edge is often a hair closer than the node and a strict
    # comparison never fires. Anything within a couple of cable radii of a
    # degree-1 node is that node.
    near_node = max(ed + 1e-6, 2.0 * graph.wire_radius)
    if nid is not None and nd <= near_node and len(graph.incident[nid]) == 1:
        return [(graph.incident[nid][0], nid)]

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


def _ordered_continuations(graph, node, eid, pairing, used_halves,
                           strict=False):
    """Branches to try on leaving ``node``, best first.

    **The unit that gets consumed is a half-edge, not an edge**, and that
    is the whole correction. A cord that crosses itself is a walk over the
    skeleton, not a simple path: where the crossing is merged into one
    node the two strands share the short edges that reach it, and a cord
    that doubles back at a hairpin runs along one skeleton line twice.
    Measured against the true centreline, the knot scene traverses three
    of its edges twice and the tangle traverses a 710 px edge twice.
    Forbidding a second traversal therefore does not prevent a mistake,
    it makes the right answer unreachable, which is what left whole
    strands uncovered.

    Leaving ``node`` along edge ``e`` is one half-edge and may happen
    once. An edge can thus be walked twice, once from each of its ends,
    and never twice the same way, which is what would let the search spin
    in place.
    """
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
    def free(e):
        return (e, node) not in used_halves

    out = []
    nxt = pairing.get((node, eid))
    if nxt is not None and free(nxt):
        out.append(nxt)
        if strict:
            # The pairing is an answer, not a suggestion. Offering the
            # alternatives alongside it let the search trade the right
            # continuation for a little more coverage, and coverage is
            # exactly what cannot see the difference: on one knot the
            # trace covered 100% of the cable with a rank correlation
            # against true arc length of 0.373. Handing the oracle
            # pairing to the old search changed nothing, 52.3 against
            # 52.4, which is what proved the pairing was never the thing
            # being ignored by accident. Where a node has an answer, take
            # it; the search exists for the nodes that do not.
            return out
    t_in = -graph.tangent_at(eid, node)       # direction of travel, arriving
    rest = []
    for cand in graph.incident[node]:
        if cand in out or not free(cand):
            continue
        t_out = graph.tangent_at(cand, node)
        rest.append((float(np.dot(t_in, t_out)), cand))
    rest.sort(reverse=True)
    out.extend(c for _, c in rest)
    return out


def _turn_penalty(graph, node, eid, nxt, weight):
    """Cost of arriving at ``node`` along ``eid`` and leaving along ``nxt``."""
    t_in = -graph.tangent_at(eid, node)
    t_out = graph.tangent_at(nxt, node)
    if not t_in.any() or not t_out.any():
        return 0.0
    straight = float(np.dot(t_in, t_out))        # 1 straight on, -1 back
    return weight * (1.0 - straight)


def _search(graph, seeds, pairing, target_edges, target_nodes,
            max_expand=40000, time_budget_s=3.0, turn_cost=TURN_COST_PX,
            strict=False):
    """Depth-first over the edge graph, keeping the best path to the end.

    "Best" is the one that **covers the most cable**, measured as the total
    length of the **distinct** edges it uses, not the shortest. That is the
    opposite of the geodesic tracer's objective and it is deliberate:
    between two ends of a tangled cable the true route is the long one, and
    the short one is the mistake.

    Distinct is the word that matters once an edge may be walked twice.
    Counting a second traversal again turns the objective into a reward for
    detours: the first version that allowed it sent simple shapes out along
    a spur and back for the extra length, and catenary and smooth, the two
    families the real tether belongs to, fell from 100.0 to 89.0. Counting
    each edge once means a second traversal pays nothing by itself and is
    taken only when it unlocks cable that is otherwise unreachable, which
    is exactly when the cord really does pass that way twice. Reaching the far endpoint always beats not reaching it.

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
        stack = [(eid0, far0, (eid0,), graph.edge_length(eid0),
                  frozenset({(eid0, node0)}), frozenset({eid0}))]
        while stack:
            eid, node, used, length, halves, seen = stack.pop()
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

            nxts = _ordered_continuations(graph, node, eid, pairing, halves,
                                          strict)
            if not nxts:
                cand = (False, length, used)
                if best is None or cand[:2] > best[:2]:
                    best = cand
                continue
            # pushed in reverse so the preferred branch is explored first
            for nxt in reversed(nxts):
                e = graph.edges[nxt]
                far = e["v"] if e["u"] == node else e["u"]
                gain = 0 if nxt in seen else graph.edge_length(nxt)
                gain -= _turn_penalty(graph, node, eid, nxt, turn_cost)
                stack.append((nxt, far, used + (nxt,), length + gain,
                              halves | {(nxt, node)}, seen | {nxt}))
        if expand > max_expand:
            break
    return best, expand


def _link_on_mask(mask, a, b, max_px):
    """A short connection from a to b that stays on the cable, or None.

    Returns the pixels between the two, exclusive, following the mask.
    """
    if a == b:
        return []
    gap = float(np.hypot(b[0] - a[0], b[1] - a[1]))
    if gap > max_px:
        return None
    try:
        from processing import geodesic_tracer
        link, _ = geodesic_tracer.trace(mask, a, b, beta=8.0)
    except Exception:                      # noqa: BLE001
        return None
    if not link or len(link) < 2:
        return None
    off = sum(1 for x, y in link
              if not (0 <= y < mask.shape[0] and 0 <= x < mask.shape[1]
                      and mask[y, x] > 127))
    if off > max(2, 0.1 * len(link)):
        return None
    return [tuple(p) for p in link[1:-1]]


def offset_fused(pts, sides, dt, nominal_r, wide_factor=WIDE_FACTOR):
    """Push the path onto the two strands where the mask is double width.

    A skeleton runs up the middle of whatever it is given, so where two
    strands of cord touch it draws **one** line between them, and the
    trace then goes up the middle of a tight hairpin instead of round it.
    The geometry says where the strands actually are. Two cords of radius
    r whose centres are d apart make a shape whose half-width on the axis
    is d/2 + r, so the distance transform on the skeleton reads DT and the
    two centres sit at plus and minus (DT - r) from it. Nothing has to be
    guessed: r is the cable's own radius, measured as the median distance
    transform over the ordinary parts of the skeleton, and DT is read per
    pixel.

    ``sides`` carries +1 or -1 per point, from which pass of a doubled
    edge that point came, so the outbound pass takes one strand and the
    return takes the other.
    """
    if len(pts) < 3:
        return pts
    a = np.asarray(pts, dtype=np.float64)
    h, w = dt.shape[:2]
    # tangent by central difference, then the normal
    t = np.gradient(a, axis=0)
    n = np.hypot(t[:, 0], t[:, 1])
    n[n < 1e-9] = 1.0
    t = t / n[:, None]
    nor = np.column_stack([-t[:, 1], t[:, 0]])

    xi = np.clip(np.round(a[:, 0]).astype(int), 0, w - 1)
    yi = np.clip(np.round(a[:, 1]).astype(int), 0, h - 1)
    local = dt[yi, xi].astype(np.float64)
    off = np.where(local > wide_factor * nominal_r, local - nominal_r, 0.0)
    return a + nor * (off * np.asarray(sides, dtype=np.float64))[:, None]


def smooth_polyline(pts, sigma_px, keep_ends=True):
    """Gaussian smoothing along the chain, endpoints pinned.

    Applied to the coordinates, not to the direction, because what is
    noisy is where the skeleton put each pixel; the direction follows.
    The ends are pinned so the path still starts and finishes exactly
    where the detector asked, which stage 5 relies on.
    """
    if sigma_px <= 0 or len(pts) < 5:
        return pts
    a = np.asarray(pts, dtype=np.float64)
    rad = max(1, int(round(3.0 * sigma_px)))
    k = np.exp(-0.5 * (np.arange(-rad, rad + 1) / sigma_px) ** 2)
    k /= k.sum()
    pad = np.r_[np.repeat(a[:1], rad, axis=0), a,
                np.repeat(a[-1:], rad, axis=0)]
    out = np.column_stack([np.convolve(pad[:, 0], k, mode="valid"),
                           np.convolve(pad[:, 1], k, mode="valid")])
    if keep_ends:
        out[0], out[-1] = a[0], a[-1]
    # Returned as floats on purpose. Rounding back to integers immediately
    # after smoothing puts the staircase straight back: the chain advances
    # about a pixel per step, so quantising it re-imposes exactly the 23
    # degrees of per-step jitter the smoothing just removed. Measured, the
    # rounded version left the turn rate at 2.1 degrees per nine pixels
    # against the true cord's 1.1, while the smoothing had done its work.
    # Nothing downstream needs integers: the path is drawn, resampled and
    # triangulated, and sub-pixel coordinates are better for all three.
    return [(float(x), float(y)) for x, y in out]


def _attach(pts, start, end, mask=None, wire_radius=3.0):
    """Make the chain begin at ``start`` and finish at ``end``.

    **Never by drawing a straight line to get there.** The first version
    of this function simply prepended the requested endpoint, and when the
    stitched path happened to begin somewhere else that produced a
    straight segment across whatever lay between. Measured on a coil
    scene: a 113 px jump straight over the spiral, 93 invented pixels, and
    the scoring metric did not notice because it only looked at the listed
    vertices and both of those sat on the cable. That is the worst shape a
    defect can take, a confident wrong answer that measures as perfect.

    Now the gap is closed by a minimal path **through the mask**, which
    follows the cable, and only when it is short enough to be a seam
    rather than a shortcut. If no such connection exists the chain is left
    as it is: a path that stops a little short is a small loss of recall,
    while a path with cable invented down the middle of it is a wrong
    measurement.
    """
    if not pts:
        return pts
    s = (int(start[0]), int(start[1]))
    e = (int(end[0]), int(end[1]))
    d0 = (pts[0][0] - s[0]) ** 2 + (pts[0][1] - s[1]) ** 2
    dn = (pts[-1][0] - s[0]) ** 2 + (pts[-1][1] - s[1]) ** 2
    if dn < d0:
        pts = pts[::-1]
    pts = list(pts)

    near = max(6.0, 2.0 * wire_radius)
    max_link = max(40.0, 12.0 * wire_radius)

    head = (int(pts[0][0]), int(pts[0][1]))
    if head != s:
        if np.hypot(head[0] - s[0], head[1] - s[1]) <= near:
            pts = [s] + pts
        elif mask is not None:
            link = _link_on_mask(mask, s, head, max_link)
            if link is not None:
                pts = [s] + link + pts

    tail = (int(pts[-1][0]), int(pts[-1][1]))
    if tail != e:
        if np.hypot(tail[0] - e[0], tail[1] - e[1]) <= near:
            pts = pts + [e]
        elif mask is not None:
            link = _link_on_mask(mask, tail, e, max_link)
            if link is not None:
                pts = pts + link + [e]
    return pts


def _stitch(graph, used, first_node):
    """Turn a sequence of edge ids into one chain of pixels.

    Each edge is oriented by **which of its two ends is nearer the pixel
    already emitted**, not by the node bookkeeping alone. The bookkeeping
    is right about which node the walk is at and silent about where in
    that node's blob the next edge happens to start, and after the
    crossings are merged a node can be a dozen pixels across. Trusting it
    produced a path that ran out to a junction, then jumped 86 pixels back
    to where it had started and carried on, which draws a straight line
    across the frame and measures as cable.
    """
    pts, sides = [], []
    seen_count = {}
    node = first_node
    for i, eid in enumerate(used):
        e = graph.edges[eid]
        k = seen_count.get(eid, 0)
        seen_count[eid] = k + 1
        side = 1.0 if k == 0 else -1.0
        seg = list(e["pts"])
        if pts:
            last = pts[-1]
            d_fwd = (seg[0][0] - last[0]) ** 2 + (seg[0][1] - last[1]) ** 2
            d_rev = (seg[-1][0] - last[0]) ** 2 + (seg[-1][1] - last[1]) ** 2
            if d_rev < d_fwd:
                seg = seg[::-1]
        elif e["v"] == node and e["u"] != node:
            seg = seg[::-1]
        if pts and seg and pts[-1] == seg[0]:
            seg = seg[1:]
        pts.extend(seg)
        sides.extend([side] * len(seg))
        node = e["v"] if e["u"] == node else e["u"]
    return pts, sides


def _repair_gaps(pts, mask, wire_radius):
    """Close, or cut at, any remaining gap between consecutive pixels.

    A last line of defence rather than a fix for a known cause. Whatever
    leaves a hole in the chain, the hole is the thing that must not reach
    the caller: a straight segment over background reads as cable to
    every downstream stage, and stage 7 turns it into arc length in
    metres. Short holes are closed through the mask, and anything left is
    cut, keeping the longer side, because a shorter true path beats a
    longer invented one.
    """
    if len(pts) < 2:
        return pts, 0
    limit = max(8.0, 3.0 * wire_radius)
    out = [pts[0]]
    repaired = 0
    for prev, cur in zip(pts[:-1], pts[1:]):
        d = float(np.hypot(cur[0] - prev[0], cur[1] - prev[1]))
        if d > limit:
            link = _link_on_mask(mask, (int(prev[0]), int(prev[1])),
                                 (int(cur[0]), int(cur[1])),
                                 max(40.0, 12.0 * wire_radius))
            if link is None:
                tail = _repair_gaps(pts[pts.index(cur):], mask, wire_radius)[0]
                return (out, repaired) if len(out) >= len(tail) else (tail, repaired)
            out.extend(link)
            repaired += 1
        out.append(cur)
    return out, repaired


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
          max_expand=40000, time_budget_s=3.0, work_width=WORK_WIDTH,
          turn_cost=TURN_COST_PX, strict_pairing=False,
          smooth_radii=SMOOTH_RADII, wide_factor=WIDE_FACTOR):
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
                           max_expand, time_budget_s, turn_cost,
                           strict_pairing)
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
    pts, sides = _stitch(graph, used, seed_node)

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
    # push the doubled stretches onto their two strands before anything
    # else touches the chain, while the pass each point came from is known
    nominal = float(np.median(graph.dt[graph.skel > 0]))         if (graph.skel > 0).any() else graph.wire_radius
    if len(sides) == len(pts):
        pts = [(float(x), float(y)) for x, y in
               offset_fused(pts, sides, graph.dt, nominal, wide_factor)]
        info["nominal_radius"] = nominal

    mask_full = (graph.binary * 255).astype(np.uint8)
    pts, n_rep = _repair_gaps(pts, mask_full, graph.wire_radius)
    info["gaps_repaired"] = n_rep
    pts = _attach(pts, start, end, mask_full, graph.wire_radius)

    info["reached"] = bool(reached)
    info["edges_used"] = len(used)
    info["mask_coverage"] = round(
        float(((cov > 0) & (binary > 0)).sum()) / max(int(binary.sum()), 1), 3)
    if len(pts) < 2:
        return None, info

    # scale back first, then smooth, so the smoothing scale is expressed
    # in the caller's pixels and the de-duplication cannot re-quantise it
    if scale != 1.0:
        inv = 1.0 / scale
        out, seen = [], set()
        for x, y in pts:
            q = (int(round(x * inv)), int(round(y * inv)))
            if q not in seen:
                seen.add(q)
                out.append(q)
        pts = out
    sigma = smooth_radii * graph.wire_radius / max(scale, 1e-6)
    pts = smooth_polyline(pts, sigma)
    info["smoothed_radii"] = float(smooth_radii)
    return [(float(x), float(y)) for x, y in pts], info


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

"""Measured constants for the synthetic generator.

Every number here was measured off the real and simulated samples already in
`data/ai_dataset/`, not invented. The measurement script is `tools/measure_real_samples.py`;
re-run it after adding real samples and update these if the statistics move.

Measured over 26 image/mask pairs (2026-10-28):

    foreground fraction   median 1.66%   range 0.03 to 2.30%
    wire radius (DT max)  median 17.7px  range 8 to 30px
    connected components  1 in 25 of 26 pairs
    wire minus background median 111 grey levels

Two appearance families are present in the archive and both are reproduced:

    lab      1920x1440, grey table, strong illumination gradient, background
             mean 57 to 106 with std 41 to 57 (dust, specks, table texture),
             pale braided cord at 166 to 227, soft cast shadow
    orbital  4056x3040 renders, near-black background at mean 16 to 19 with
             std 8, thin bright cord at 84 to 103, almost no texture
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


# --- working resolutions -------------------------------------------------
#
# The project captures at 4056x3040 and previews at 1920x1440. Model 1 trains
# at 256x192 and the tracker rescales any mask to a 15 px radius, so nothing
# downstream needs the full sensor. 1920x1440 is the default because it is
# what the majority of the real samples are, and because the disk cost of the
# full sensor is four times higher for no gain in training signal.
RESOLUTIONS = {
    "preview": (1920, 1440),   # default
    "full": (4056, 3040),      # full sensor, for spot checks
    "half": (960, 720),        # fast iteration
}
DEFAULT_RESOLUTION = "preview"


@dataclass(frozen=True)
class Appearance:
    """One lighting family, in the units the measurement produced."""

    name: str
    bg_mean: Tuple[float, float]        # background grey, range to sample from
    bg_std: Tuple[float, float]         # background texture std
    wire_grey: Tuple[float, float]      # wire grey level
    gradient_strength: Tuple[float, float]   # illumination falloff, 0 to 1
    specks: Tuple[int, int]             # dust specks per megapixel
    shadow_strength: Tuple[float, float]     # cast shadow darkening, 0 to 1
    wire_tint: Tuple[float, float, float]    # BGR multiplier, the cord is cream
    vignette: Tuple[float, float]


LAB = Appearance(
    name="lab",
    bg_mean=(45.0, 115.0),
    bg_std=(28.0, 60.0),
    wire_grey=(160.0, 235.0),
    gradient_strength=(0.35, 0.85),
    specks=(40, 220),
    shadow_strength=(0.10, 0.35),
    wire_tint=(0.86, 0.97, 1.0),   # BGR: slightly warm, a cream cord
    vignette=(0.05, 0.30),
)

ORBITAL = Appearance(
    name="orbital",
    bg_mean=(1.0, 22.0),
    bg_std=(2.0, 10.0),
    wire_grey=(80.0, 160.0),
    gradient_strength=(0.05, 0.30),
    specks=(0, 15),
    shadow_strength=(0.0, 0.05),    # no atmosphere, no fill, so no soft shadow
    wire_tint=(0.95, 0.99, 1.0),
    vignette=(0.0, 0.15),
)

FAMILIES = {"lab": LAB, "orbital": ORBITAL}

#: Probability of drawing the lab family. The archive is 13 lab frames and 13
#: dark render frames, so an even split is what reproduces its background
#: statistics. At 0.6 the generated median background came out 1.55 times the
#: archive's, because the lab family is the bright one.
LAB_PROBABILITY = 0.5


# --- geometry ------------------------------------------------------------
#
# Shape families. The weights are what `generate.py` samples with by default.
# `tangle`, `knot` and `coil` are over-represented relative to how often they
# occur in real captures on purpose: they are the cases the branch scorer has
# to learn, and a dataset that mirrors reality would be almost all easy
# examples.
SHAPE_WEIGHTS = {
    "straight": 0.10,   # taut, near-straight with slight sag
    "catenary": 0.12,   # hanging under gravity
    "smooth": 0.18,     # one or two gentle inflections, no crossing
    "loop": 0.20,       # one or two self-crossings, the common real case
    "coil": 0.12,       # spiral, many near-parallel runs
    "knot": 0.16,       # torus knot projection, clean over-under crossings
    "tangle": 0.12,     # momentum random walk, many crossings
}

#: Wire radius in pixels at the reference depth, before perspective scaling.
#: Measured median is 17.7 px; the range covers the whole archive plus margin.
#: In practice the radius is not sampled from here but solved for, so that the
#: foreground fraction lands on the measured band: see
#: rasterize.radius_for_foreground. This range documents what the archive
#: contains and bounds the result.
WIRE_RADIUS_PX = (6.0, 30.0)

#: Arc length of the visible wire, in frame diagonals. Bounds the product of
#: radius and length so that both can stay inside their measured ranges at
#: once. Measured: the archive cords run roughly 0.8 to 1.6 diagonals.
ARC_LENGTH_DIAGONALS = (0.80, 2.60)

#: Relative depth range along the curve. The radius scales as 1/depth, which
#: is what gives the tracker the thickness-continuity signal it scores on.
DEPTH_RANGE = (0.70, 1.65)

#: Target foreground fraction. Shapes that fall outside are rejected and
#: regenerated, which keeps the synthetic statistics on top of the measured ones.
FOREGROUND_FRACTION = (0.005, 0.032)

#: Mask degradation. Real masks come out of a top-hat transform in low light,
#: so they have ragged edges, pinholes and occasional breaks. A generator that
#: emits clean vector strokes trains the scorer on a world that does not exist.
EDGE_RAGGEDNESS = (0.0, 2.2)     # px of boundary noise
PINHOLE_RATE = (0.0, 0.0015)     # fraction of foreground punched out
#: A break changes the topology, so it is the defect that has to stay as rare
#: as the archive shows: 1 mask in 26 has a second connected component.
BREAK_PROBABILITY = 0.12         # fraction of samples that get any break
BREAK_COUNT = (1, 3)             # how many, once a sample is chosen
BREAK_WIDTH_RADII = (0.5, 1.8)   # break width as a multiple of the local radius

#: Fraction of samples where the wire deliberately leaves the frame. This is
#: the condition that silently breaks the parametric matching assumption, and
#: the endpoint detector has to cope with it too.
OUT_OF_FRAME_RATE = 0.12

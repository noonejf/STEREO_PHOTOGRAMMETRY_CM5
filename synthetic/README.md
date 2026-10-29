# Synthetic data for the two LINKU models

The payload plan has two learned components. Neither has enough real data to
train on, and hand-labelling enough of it is not realistic: the path dataset
has three stereo samples against a recommended thirty to a hundred, after
months of captures. This package generates both datasets instead.

```
synthetic/
  config.py          constants measured off the real archive, with the measurement
  geometry.py        3D centrelines: straight, catenary, smooth, loop, coil, knot, tangle
  rasterize.py       centreline -> mask, depth buffer, coverage, lateral position
  appearance.py      buffers -> photograph, in the lab or the orbital family
  branches.py        mask + known path -> labelled (features, chosen branch) rows
  endpoints.py       mask -> per-skeleton-pixel features for finding the two ends
  evaluate.py        trace vs true centreline: recall, precision, F1
  checkpoint.py      resumable CPU training, shared by the three trainers
  generate.py        CLI for mass generation
  train_mask.py      the segmenter, with a held-out split
  train_path.py      the branch scorer, measured against the rule it would replace
  train_endpoints.py the endpoint finder, measured against the shipped detector
```

**The cord is always an open curve, and both ends are visible as ends.**
Two separate conditions, and only the first was enforced at first.

`geometry.MIN_END_SEPARATION` asks that the two ends are far from each other.
A ring with a small gap passes that, and so does a cord whose end comes to
rest across its own middle: neither shows a free end once painted, and an end
that is invisible in the mask cannot be found from the mask by anything.
`geometry.ends_are_free` measures the thing that decides, the clearance
between each end and the rest of the cord, and `generate._open_centreline`
redraws a shape that fails it. An end outside the frame is exempt, since that
occlusion is real and the models have to cope with it. The realised rate is
recorded per sample as `ends_free` in `index.jsonl`: 98% over the shipped
1500, lowest on knots at 95%.

Two shape generators needed fixing for this, not just a filter on top:

- `_loop` turned 1.55 to 1.9 times around a circle of constant radius, so
  the second revolution retraced the first and painted a solid ring with
  both ends buried in it. It now drifts the centre as it turns, and takes
  1.15 to 1.45 turns.
- `_knot` cut the closed torus knot at a random index. A torus knot runs
  close to itself nearly everywhere, so both ends landed against a
  neighbouring wrap at about 4 px clearance where 15 px is needed. The cut
  point and the trim length are now both chosen where the curve is locally
  farthest from the rest of itself, which lifts the median clearance to
  9.7 px.

## Finding the two ends

Tracing a mask is useless without knowing where to begin and where to stop,
so this is half of the path capability rather than a side quest.

The shipped detector takes skeleton tips and picks the geodesically farthest
pair. It cannot find an end that leaves no tip, and when the free end of the
cord rests across another part of the cord the skeleton merges straight
through it and no tip is produced there.

`endpoints.py` scores **every** skeleton pixel instead, then takes the best
pixel plus the best one geodesically far from it. Twelve features; the one
that carries by far the most weight is one-sidedness (0.36), which measures
whether the nearby skeleton lies to one side, and that still fires where no
tip exists.

Results, 1500 masks, 200 trees, 79 s on CPU, 40 held-out masks:

| | median | p75 | within 25 px |
|---|---|---|---|
| learned | 1.2 px | 2.0 px | 85% |
| shipped | 1.3 px | 25.5 px | 75% |

| shape | learned median | within 25 px |
|---|---|---|
| smooth | 0 px | 100% |
| coil, loop, straight, tangle | 1 px | 100 / 92 / 100 / 71% |
| catenary | 6 px | 100% |
| knot | 8 px | 62% |

On the simple shapes a tensioned cable actually is: 1 px median, 100% within
25 px. Retrained on 4000 samples with joint top-K pair decoding: 90% within
25 px, 23 MB, 223 ms per mask.

**And none of that survived the end-to-end test.** Measured by
`tools/benchmark_endpoint_model.py` over 60 fresh scenes, with the trace
scored against the true centreline: the learned finder's seeds produce a
WORSE final trace, F1 83.7 against the classical detector's 88.1, 7 wins to
12 losses. The mechanism is the failure mode, not the failure rate. A
classical miss lands on a skeleton tip, which is a safe place to start a
trace even when it is far from the true end; a learned miss lands mid-cord
on a crossing and the whole trace starts lost. It misses less often and its
misses cost far more.

The number that closes the case: seeding the tracker with the TRUE endpoints
gives F1 90.9, so everything endpoint accuracy could ever buy over the
classical detector was 2.8 points. After the thickness fix, stage 2 is not
the bottleneck. The remaining losses are **wrong turns at self-crossings**,
which no endpoint finder and no branch scorer can recover.

That sentence used to say mask breaks, and that was wrong. Measured over
the 60 benchmark scenes: 1 mask in 60 has a break the centreline spans, 42
in 60 contain a self-crossing. **The generator is why.** Its masks come out
in one piece 59 times in 60, with 94.1% of the centreline inside the
largest component, while the masks the real segmenters produce on the 20
real pairs come out in one piece between 10 and 19 times in 20. So the
synthetic benchmark cannot see break-bridging at all: there is nothing to
bridge in it. Adding realistic fragmentation to `rasterize.py`, matched to
what `tools/compare_mask_models.py` reports for the shipped segmenter, is
what would let that question be asked. Until then, do not quote a
break-bridging number from this benchmark.

**One alternative tracer does close it, and by a lot.**
`processing/graph_tracer.py` resolves every crossing at once by pairing
branches at each skeleton node, then searches the resulting graph for the
path that reaches the far endpoint covering the most cable. 96.4 against
the DFS's 88.1 over 60 scenes, 96.4 against 80.4 on knots, in 0.14 s
against 1.76 s, and it passes the 90.9 that the DFS reaches with perfect
endpoints. `synthetic/pairings.py` harvests the labelled pairings and
`synthetic/train_pairings.py` fits the model that decides them, which is
the first learned component in this repo to win the end-to-end
measurement and therefore the first to ship on by default.

On real frames it is a tie rather than a win, because real masks come in
pieces and a graph in pieces cannot be walked end to end. See CLAUDE.md.

**The geodesic alternatives do not close it.** An oracle
that picked, per scene, the best of `SmartWireTracker` and five geodesic
variants scores 87.4 against the tracker's own 87.3 over 40 scenes: the
geodesic is best on 3 scenes and by a hair. So there is no headroom for a
path-level selector over this candidate set, which is the single-curve
version of Turetken's path classifier. Wherever the tracker fails, every
alternative tried fails worse. `tools/benchmark_geodesic_tracer.py`.

`LINKU_ENDPOINT_MODEL` therefore stays **off** by default, same standard as
the branch scorer: the only number that switches a learned component on is
the end-to-end one.

### What an earlier version of this file claimed, and why it was wrong

Until the generator was fixed, this section reported that the shipped
detector was structurally blind to a third of all endpoints: 47 of 138 with
no skeleton tip within two wire radii, 83% of loop ends, 51.5 px median error
against the learned finder's. That measurement was real but it was measuring
the generator, not the detector. The path set was painting cords three times
too thick, which fused neighbouring strands into one blob and buried the free
ends inside it. With the cords at the thickness the archive actually shows,
95% of ends leave a skeleton tip rather than 66%, and the shipped detector
goes from 51.5 px median to 1.3 px.

The structural argument still holds for the ends that stay buried, and the
learned finder still wins, but it wins by 10 points of tail coverage rather
than by two orders of magnitude. A synthetic benchmark measures the generator
until proven otherwise.

## Why synthetic data works here, and where it does not

The two models sit in completely different positions with respect to the
domain gap, and that is the single most important thing to understand before
trusting any of this.

**The branch scorer never sees a photograph.** `SmartWireTracker.__init__`
takes `(mask, start, end)` and nothing else, and every feature its scoring
formula uses comes from `cv2.distanceTransform` of the binary mask plus the
geometry of the path already walked. There is no colour, no texture, no
sensor noise anywhere in it. A synthetic mask and a real mask are therefore
the same kind of object, and there is no appearance gap to cross. What still
has to match is the *statistics* of the mask, which is what `config.py` is
for.

**The segmenter does see pixels**, so it has a real domain gap, and
`train_mask.py` is built around measuring it: real samples are evaluated but
not trained on by default, and the number that matters is the one printed for
real images from a model fitted only on synthetic ones. Treat the synthetic
held-out score as a sanity check and the real score as the result.

Measured, the synthetic data helps the segmenter only when the forest is
allowed to be huge. Unbounded (430 MB) it beats the GUI-trained model
clearly, IoU 0.538 against 0.470 on all 20 real pairs; capped to what a CM5
can load it ties at best (82 MB, 0.613 against 0.620 F1) and loses when
compact (27 MB). With a per-pixel RandomForest on 9 features the capacity
is the bottleneck, not the data, so the GUI model stays. `--min-leaf`
(default 150) exists so nobody produces a 430 MB pickle by accident. If
this is picked up again, the levers are richer features or more REAL
samples, not more trees.

## What was measured, and from what

Every constant in `config.py` came from the 26 image and mask pairs already
in `data/ai_dataset/`:

| quantity | archive | mask set | path set |
|---|---|---|---|
| foreground fraction | median 1.66%, p05 0.32, p95 2.08 | median 1.58% | median 1.80% |
| wire radius, max of the distance transform | median 17.7 px at 1920x1440 | median 15.2 px | median 6.4 px at 960x720 |
| single connected component | 25 of 26 masks, 96% | 83% | 94% |
| wire minus background | median 111 grey levels | matched per family | --- |

The mask set sits below the archive on the last row on purpose: 12% of its
samples get a break and 13% leave the frame, both of which split the mask,
and the segmenter has to cope with both. The path set is gentler, since a
severed path has no traversable ground truth to label against.

The path set is generated at 960x720, so its radii are half the archive's by
construction, and lower again because its shapes are long: the foreground
budget is shared between radius and arc length, so a knot that wanders for
two frame diagonals comes out at the 3 px floor. That is the regime the real
tether is in anyway. At the 8 mm lens, a 2 mm cord projects 10 px across at
1 m and 0.26 px at 40 m.

**This was wrong until it was measured.** The path set used to sample its
radius flat over 8 to 24 px at 960x720 and ignore the foreground target
entirely, on the argument that only topology matters for the tracker. It came
out at 5.3% foreground against the archive's 1.4%, three times too fat, and
the argument was backwards: a fat cord fuses neighbouring strands into one
blob, which erases the crossings the tracker exists to resolve and buries the
ends the endpoint model is supposed to find. Thickness is not cosmetic here,
it sets the topology of the mask.

Two lighting families are reproduced because the archive contains two. The
`lab` family is the grey table with a hard side light, a strong gradient,
dust specks and a cast shadow, with a pale braided cord at 166 to 227 grey.
The `orbital` family is the render condition: near-black at 16 to 19 grey,
no fill, no shadow, a thin bright cord.

Radius and arc length cannot both be sampled freely, because their product is
the painted area and the area has to match the measured foreground fraction.
The generator therefore sets the shape, measures its arc length, and solves
for the radius. A long, dense shape consequently comes out thin. That is not
a defect: it is what the constraint implies, and the realised value is
recorded per sample in `index.jsonl`.

## Running it

```bash
# both datasets, defaults are 1920x1440 for masks and 960x720 for paths
python -m synthetic.generate both --count 2000 --workers 16

# just one of them
python -m synthetic.generate mask --count 4000
python -m synthetic.generate path --count 2000 --stride 3

# training, all three resume from their checkpoint after a Ctrl-C
python -m synthetic.train_mask --mix-real
python -m synthetic.train_path --trees 60 --max-depth 10 --min-leaf 200
python -m synthetic.train_endpoints --harvest   # harvest only, resumable
python -m synthetic.train_endpoints             # train, resumable
python -m synthetic.train_endpoints --fresh     # ignore the checkpoint

# what actually decides whether either learned component ships: the trace
# against the true centreline, on fresh scenes the trainers never saw
python tools/benchmark_branch_scorer.py --count 40
python tools/benchmark_endpoint_model.py --count 60
```

**Checkpoints.** There is no GPU here and there will not be one on the
flight computer, so training is CPU-bound and long, and a run that has to
start over is the real obstacle to using a large dataset.
`checkpoint.py` adds trees in batches with `warm_start`, writing the whole
forest to `<model>.ckpt` after each batch through a temporary file, so an
interrupt cannot leave a half-written model that a later run would trust.
Re-running the same command continues from the tree count it reached.

Output goes to `data/synthetic/`, which is git-ignored. It is regenerated
exactly from the seed, so the generator is the thing worth versioning, not
its output.

```
data/synthetic/
  mask/  images/000000.jpg  masks/000000.png  index.jsonl
  path/  masks/000000.png   paths/000000.json  features/shard_000.npz  index.jsonl
```

**Disk, measured on a 1500 + 1500 run:**

| dataset | per sample | 1 500 | 10 000 |
|---|---|---|---|
| mask, 1920x1440, JPEG q88 | 520 KB | 780 MB | 5.2 GB |
| path, 960x720, PNG + JSON + features | 34 KB | 51 MB | 340 MB |

The mask set is the expensive one because it stores photographs. If the
other machine is tight, generate it at `--size half` (960x720), which costs
about a quarter: Model 1 trains at 256x192, so nothing downstream ever sees
the larger frame. The path set is cheap at any size and can be grown freely.

Nothing in `data/synthetic/` is committed. It regenerates byte for byte from
`--seed`, so if the other machine needs the data it should run the generator
rather than copy the files.

## The harvester

`branches.py` is the tool the camera system report lists as a blocker for the
second model: it converts a verified path into labelled
`(candidate-features, chosen-branch)` examples at every branch point. With
real data it needs a human-verified path, which is why the path dataset has
three samples. With synthetic data the path is known by construction, so the
labelling is exact and free.

It works by driving the real `SmartWireTracker` along the ground-truth path
and asking it, at each step, what candidates it sees. The features are
therefore identical by construction to what the tracker computes at inference
time. Re-implementing them would let the two drift apart, and a scorer served
features that differ from the ones it trained on fails silently and produces
plausible-looking wrong paths.

Thirteen features per candidate, listed in `branches.FEATURE_NAMES`. The
order is written into the model file and checked when the shards are loaded,
so a stale dataset cannot be trained against new code without an error.

## The comparison that decides whether Model 2 ships

`train_path.py` reports top-1 accuracy per decision for the learned scorer
and, on the same held-out decisions, for the hand-tuned formula it would
replace:

```
direction continuity x1200 + thickness continuity x600 + centeredness x300
```

A learned scorer that does not beat that rule is not worth the dependency,
and without the side-by-side number there is no way to know. The split is by
sample, never by row and never by decision: candidates within a decision are
mutually exclusive and decisions within one image share a wire, so anything
finer leaks.

**And that number is still not enough.** Closed twice. The model trained on
the fat dataset won offline 0.692 to 0.456 and then tied on end-to-end
coverage. Retrained on the corrected thin dataset it won offline again,
0.838 to 0.714 over 33529 held-out decisions, and on 40 fresh scenes scored
by true-path F1 it went 1 win, 3 losses, 36 ties, 89.1 against the
formula's 90.0, at 4.5x the runtime. The hand-tuned formula already traces
with 100% precision and a median F1 of 100 when the endpoints are right:
there is nothing left for a per-decision scorer to win. The scorer stays
off unless `LINKU_BRANCH_SCORER=1`, and it is not worth picking up again
while the formula sits at the ceiling.

## Known limits

- **Masks are single-wire.** Nothing here generates two separate tethers, a
  tether plus a structural cable, or a tether crossing a hard edge of the
  LINKU structure. Real captures in the dark room will contain the structure.
- **No stereo pairs.** Neither model needs them: the segmenter is per-pixel
  and the scorer works on one mask at a time. Stereo matters only to the
  geometric stage, which is not learned.
- **No motion blur or rolling-shutter shear.** Both are real and both are
  being characterised in a separate experiment, so adding an unvalidated
  model of them here would bake in a guess.
- **The lab family reproduces the table the archive was shot on**, not the
  TV2 studio, which has not been photographed yet. Regenerate the constants
  from the first real captures once they exist.

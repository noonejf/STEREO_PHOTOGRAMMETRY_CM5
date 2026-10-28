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
  checkpoint.py      resumable CPU training, shared by the three trainers
  generate.py        CLI for mass generation
  train_mask.py      the segmenter, with a held-out split
  train_path.py      the branch scorer, measured against the rule it would replace
  train_endpoints.py the endpoint finder, measured against the shipped detector
```

**The cord is always an open curve.** It has two free ends, and the whole
path capability depends on that: a closed loop has no start and no stop.
`geometry.MIN_END_SEPARATION` enforces it, and a shape whose ends come too
close is rejected and drawn again rather than merely hoped to be rare.

## Finding the two ends

Tracing a mask is useless without knowing where to begin and where to stop,
so this is half of the path capability rather than a side quest.

The shipped detector takes skeleton tips and picks the geodesically farthest
pair. Measured over 80 synthetic masks, that cannot work on a third of the
cases: 47 of 138 true endpoints have no skeleton tip within two wire radii,
and 44 of those sit squarely on the mask. They concentrate in 83% of loop
ends and 71% of knot ends, for one structural reason. When the free end lies
across another part of the cord the skeleton merges straight through it and
leaves no tip, and no tuning recovers an end that leaves no tip.

`endpoints.py` scores **every** skeleton pixel instead, which lifts the
ceiling on those same masks from 66% to 100%, then takes the best pixel plus
the best one geodesically far from it. Twelve features; the one that carries
the most weight is one-sidedness, which measures whether the nearby skeleton
lies to one side, and that still fires where no tip exists.

Results, 1500 masks, 200 trees, 102 s on CPU, against the shipped detector:

| shape | learned | shipped | within 25 px |
|---|---|---|---|
| straight | 3 px | 5 px | 100% |
| smooth | 3 px | 6 px | 92% |
| catenary | 6 px | 11 px | 100% |
| coil | 11 px | 59 px | 55% |
| loop | 106 px | 156 px | 22% |
| knot | 109 px | 113 px | 9% |
| tangle | 111 px | 137 px | 0% |

It wins in every family. **Read the per-shape rows, not the aggregate.** The
aggregate is 51.5 px against 118.5, and it misleads, because this dataset is
40% knot and tangle on purpose, which is right for the branch scorer and
badly unrepresentative of the real tether. On the simple shapes, which is
what a tensioned cable is, the learned finder gives 3 px median and 94%
within 25 px. Heavy tangles stay hard and partly unrecoverable from a binary
mask alone.

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

## What was measured, and from what

Every constant in `config.py` came from the 26 image and mask pairs already
in `data/ai_dataset/`:

| quantity | archive | generator |
|---|---|---|
| foreground fraction | median 1.66%, range 0.03 to 2.30% | median 1.2%, p05 0.4, p95 2.5 |
| wire radius, max of the distance transform | median 17.7 px, range 8 to 30 | median 16.5 px |
| single connected component | 25 of 26 masks | 91% of samples |
| wire minus background | median 111 grey levels | matched per family |

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

# what actually decides whether the branch scorer ships
python tools/benchmark_branch_scorer.py --count 30
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

**And that number is still not enough.** The first model trained here scored
0.692 against the formula's 0.456 over 25317 held-out decisions, then went
11 wins, 12 losses, 7 ties on end-to-end coverage over 30 masks, at 3.8
times the runtime. Per-step accuracy is not what determines where the
tracker ends up. Always finish with
`python3 tools/benchmark_branch_scorer.py --count 30`, and treat coverage as
the only verdict. The scorer stays off unless `LINKU_BRANCH_SCORER=1`.

If Model 2 is picked up again, the lever is the training objective, not more
data: it has to be optimised against the whole traced path rather than
against the isolated decision.

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

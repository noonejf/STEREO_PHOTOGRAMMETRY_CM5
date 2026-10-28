# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this project actually is

Project **LINKU** (PUCP / APSCO): a stereo vision system that **measures a thin
cable (tether) strung between two satellites**, in 3D, in the dark.

Hardware: **Raspberry Pi CM5** with two **Arducam HQ 477 (IMX477, 12 MP)**
cameras, currently fitted with the **Arducam C1508ZM04 8 mm f/1.6-f/16** lens.

The headline output is **not a dense point cloud**. It is a set of metric
scalars about the cable: arc length in metres, straightness, depth range,
diameter and curvature. A sparse point cloud of the cable is a by-product.

> Why this matters when reading the code: dense SGBM **fails** on a thin,
> textureless object, because there is nothing to correlate along the wire.
> The whole geometric pipeline exists to work around that. Treat "stereo
> photogrammetry" in old names and docstrings as a historical label.

## Running it

```bash
python3 main.py          # the application
python3 quick_start.py   # first-time setup guide
python3 generate_charuco.py   # regenerate charuco_board_5x7.png for printing
```

`main.py` does not require cameras. If `libcamera` or the sensors are missing it
starts in **"Processing Only Mode"**: you can process archived captures but not
take new ones. This is the normal path on a Windows dev machine.

```bash
# Camera checks (on the Pi)
libcamera-hello --list-cameras
libcamera-hello --camera 0 -t 2000

# Offline calibration diagnostics (no camera, no GUI, writes nothing)
python3 tools/analyze_calibration_sessions.py
python3 tools/replay_guided_session.py calibration_20260216_160735

# Logs
tail -f logs/stereo_photogrammetry.log
```

## Application structure

One PyQt5 window, a collapsible icon rail (56 px closed, 188 px open), a
`QStackedWidget` ([gui/main_window.py](gui/main_window.py)):

| # | Page | Class | File |
|---|------|-------|------|
| 0 | Dashboard | built inline | `gui/main_window.py` |
| 1 | Calibration | `CalibrationPage` | `gui/calibration_dialog.py` |
| 2 | Processing | `ProcessingPage` | `gui/processing_dialog.py` |
| 3 | AI | `AIPage` | `gui/ai_page.py` |
| 4 | Optics | `OpticsPage` | `gui/optics_page.py` |

The Optics page embeds `calculate_cam/camera_dof_visualizer.py` by reparenting
that window's central widget, so the optics maths has one implementation.

**UI conventions.** Icons are SVG paths in `gui/icons.py`, never Unicode
glyphs: several of the glyphs this app used have no coverage in the fonts
shipped with Raspberry Pi OS and rendered as empty boxes on the target machine.
`gui/theme.py` holds the palette and a stylesheet applied to the QApplication in
`main.py` before any dialog can appear. The interface is in English.

## The cable measurement pipeline (the main path)

Processing page, mode **`Geometric (Wire Tracking)`**, which is the **default**
(`gui/processing_dialog.py:1061`). `Dense SGBM (Traditional)` is the fallback.

| # | Step | Entry point |
|---|------|-------------|
| 1 | Segment the cable into binary masks (L+R) | `open_cable_detection_tuner_with_switch()`, `edge_detection_tuner.py:1426` |
| 2 | Find the two endpoints (skeletonize, prune, geodesic-farthest pair) | `detect_wire_endpoints()`, `processing/endpoint_detector.py:771` |
| 3 | Trace the path: automatic **or** hand-drawn | `WireMethodChoiceDialog`, `gui/wire_method_choice.py:85` |
| 3a | Auto: DFS over the mask with backtracking and momentum | `SmartWireTracker.track_wire()`, `processing/smart_wire_tracker.py:88` |
| 3b | Manual: user clicks points along the wire | `WirePathDrawerDialog`, `gui/wire_path_drawer.py:176` |
| 4 | Rectify both images | `StereoProcessor.rectify_images()`, `processing/stereo_processor.py:403` |
| 5 | Match left to right | `compute_disparity_from_wire_paths()`, `processing/stereo_processor.py:852` |
| 6 | Sparse 3D cloud of the cable | `generate_point_cloud_from_matches()`, `processing/stereo_processor.py:1441` |
| 7 | Metric scalars | `compute_wire_metrics()`, `processing/wire_metrics.py:56` |
| 8 | Export PLY/XYZ/PCD/OBJ | `PointCloudExporter.export_point_cloud()` |

### The one assumption to keep in mind

Step 5 matches **parametrically, not epipolarly**: the point at i% along the
left path is paired with the point at i% along the right path. This only holds
if both traced paths start and end at the **same physical points** on the cable
and traverse it at the same rate. When an endpoint is occluded or a path leaves
the frame, the error is systematic and silent. There is no epipolar check to
catch it.

Triangulation is written out by hand (`processing/wire_metrics.py:95`), not via
`cv2.triangulatePoints` or `cv2.reprojectImageTo3D`, neither of which is used
anywhere in the repo.

`compute_wire_metrics` drops points with `disp <= 0` or `Z` outside 0.05 to
50.0 m **before** computing arc length, so `total_length_m` under-reports if a
mid-wire segment gets filtered.

## The AI page

Real trained model, but **classical ML, not deep learning**. There is no torch,
tensorflow, onnx or tflite anywhere in the repo.

- `RandomForestClassifier` from scikit-learn, per-pixel binary cable/background
  segmentation (`gui/ai_page.py:91`).
- 9 hand-crafted per-pixel features: B, G, R, H, S, V, 3x3 blur, 9x9 blur,
  local contrast (`gui/ai_page.py:70`).
- Trains at 256x192, augments with flips and brightness, balances 1:4.
- Pickled to `data/models/mask_model.pkl`.
- Consumed as an **optional alternative segmenter at pipeline step 1**, in
  `_apply_ai_mask` (`edge_detection_tuner.py:1345`).

**How the two segmentation modes interact.** The tuner holds a `_ai_mode` flag.
Pressing "Aplicar modelo IA" turns it on; touching any classical parameter turns
it off (`_schedule_update`). Everything that needs the final mask must call
**`refresh_mask()`**, which dispatches on that flag. Calling `update_detection()`
directly forces the classical method and silently discards the AI mask, which was
a real bug: both exit paths did exactly that, so the trained model was a preview
only and never reached the pipeline. If you add a new exit path, use
`refresh_mask()`.

Saving to the dataset while in AI mode now asks for confirmation first, because
training the model on its own unverified output reinforces its errors.

Two caveats worth repeating to the user before they trust it:

1. **The reported F1/precision/recall are training-set scores**
   (`gui/ai_page.py:187` predicts on `X_tr`, the same array passed to `fit`
   five lines earlier). There is no held-out split, so
   the numbers are optimistic by construction.
2. **The second model does not exist.** `PATH_MODEL_PATH` is never written,
   `_train_path_model()` is a "Próximamente" placeholder, and the matching
   "Opción 3 - IA Wire Tracker" button is permanently disabled
   (`gui/wire_method_choice.py:212`).

## Datasets

`utils/dataset_manager.py` manages two independent on-disk sample stores with
the same class, with perceptual dedup (64x64 gray MD5):

```
data/ai_dataset/mask_dataset/   # images + masks, for the RandomForest
data/ai_dataset/path_dataset/   # images + masks + paths JSON, for the model that does not exist yet
  images/0001.jpg, 0001_right.jpg
  masks/0001.png,  0001_right.png
  paths/0001.json  {"left": [[x,y],...], "right": [[x,y],...]}
```

Browse either with `DatasetViewerDialog` (`gui/dataset_viewer.py:135`).

### Synthetic data (`synthetic/`)

Neither model has enough real data, so `synthetic/` generates both datasets.
See `synthetic/README.md`. Three things to know before using it:

- **The branch scorer has no domain gap.** `SmartWireTracker.__init__` takes
  `(mask, start, end)` and every feature comes from the distance transform of
  that mask, so a synthetic mask and a real one are the same kind of object.
  The segmenter *does* see pixels, so `train_mask.py` evaluates on real
  samples it never trained on and prints that number separately.
- **`synthetic/branches.py` is the harvester** the D5 report lists as the
  blocker for Model 2. It drives the real tracker along a known path, so the
  features are identical by construction to what the tracker computes at run
  time. Changing `FEATURE_NAMES` invalidates every stored shard, and the
  loader checks for it.
- **Constants in `config.py` were measured**, by
  `tools/measure_real_samples.py`, off the 26 real pairs. Re-run it with
  `--compare` after adding real samples.

Output lands in `data/synthetic/`, which **is** gitignored, unlike
`data/captures/`.

`processing/branch_scorer.py` lets a trained Model 2 replace the hand-tuned
branch formula. It is off unless a model exists **and** that model recorded
that it beat the formula on held-out decisions. `LINKU_BRANCH_SCORER=0`
forces the formula back on for an A/B run.

## Calibration

### How it works today

`CalibrationPage`: you press Start, a **countdown** runs, one pair is shot, it
waits, shoots again, and so on. All images are processed **at the end**. There
is no live feedback and no way to reject a bad frame as it happens.

Board: **ChArUco 5x7, 37 mm squares, 29.6 mm markers, DICT_6X6_250**
(`config/camera_config.py:56`). Print `charuco_board_5x7.png`.

Calibration captures at **full resolution (4056x3040) with an explicit
`--mode`** (`config/camera_config.py`, `get_libcamera_cmd`). This matters:
`fx = f/pixel_size`, so calibrating at one resolution and capturing at another
invalidates the result, and two IMX477 modes **crop** as well as bin, so you
cannot simply rescale. This was fixed after the archived sessions were taken.

### State of the current calibration

`data/calibration/calibration_data.json` is flagged **`is_good_quality: False`**
by the system itself: error 1.53 px, shot at 1920x1440, and `cx = 694.8` on a
1920-wide image where it should sit near 960. That 265 px offset is the
signature of the `[tx,ty]` vs `[cx,cy]` degeneracy.

`calibration_data_blender_sim.json` has error 0.0 and `images_used: 0`. It is
**not a fit**, it is the ground truth of the Blender simulation written out
directly. Correct for simulation work, meaningless for hardware.

### Diagnosis of the 23 failed sessions

Measured over 424 archived frames: median board tilt **4.4°**, only 39% above
5°, and **not one frame above 45°**. With the board near-frontal the focal
length is mathematically unrecoverable, because a longer focal at a greater
distance produces an identical image. More frames of the same pose would never
have fixed it.

Reprojection RMS is **not** a quality metric. It is the training residual the
optimizer just minimised. Use the parameter covariance instead. OpenCV's
`stdDeviationsIntrinsics` gives only its diagonal, so
`calibration_guidance.intrinsics_covariance` rebuilds the full matrix from the
`projectPoints` Jacobian with the per-view poses marginalised out by a Schur
complement, and takes the scale from OpenCV.

### The guided flow, which is now the primary one

| File | What it holds |
|------|---------------|
| `camera/calibration_guidance.py` | Per-frame gates, degeneracy and novelty tests, parameter uncertainty, convergence, and Max ERE from the full covariance |
| `camera/guided_session.py` | The capture loop. A rejected frame does **not** consume a slot, so asking for 25 views yields 25 that passed every gate |
| `camera/pose_guidance.py` | Generates the pose to ask for next and projects it into both cameras |
| `gui/guided_calibration.py` | The worker thread and the status panel |
| `tools/analyze_calibration_sessions.py` | Retrospective diagnosis over the archive |
| `tools/replay_guided_session.py` | Replays archived sessions frame by frame, no hardware |

The three `camera/` modules import neither a camera nor PyQt, by design, so all
of them can be exercised offline.

**How the loop decides.** Detection and the refit run in a worker thread on a
960 px copy of the preview, never on the UI thread; the worker drops stale
frames rather than queueing them. A frame is kept only when it is sharp over
the board region, momentarily still, visible to **both** cameras, and **on the
pose currently being asked for**. That last gate is what keeps the drawn
overlay and the capture the same thing: without it the session kept whatever it
found useful while the outline sat untouched on screen.

Accepted poses trigger a full-resolution still pair; the preview is only ever
used for guidance. The session refuses to report itself complete until the
accepted views cover four tilt bins (0-10°, 10-30°, 30-45°, 45-70°) with at
least 3 each, and `Finish with the views collected` is the deliberate way out
when a pose cannot be reached. **The bins must stay contiguous.** They were
(0-10, 15-30, ...) and a board at 12° fell in no bin at all, so the session
rejected it saying the tilt was outside the useful range, which it is not. A
hand-held board sweeps through every angle, so a gap discards good views.

The legacy countdown flow is still present behind `Legacy flow (countdown)`.

## Things that will trip you up

**`edge_detection_tuner.py` looks like a dev tool but is load-bearing.** It sits
at the repo root and has its own `main()`, yet
`gui/processing_dialog.py:1526` imports `open_cable_detection_tuner_with_switch`
from it. It is the **only** way the app produces cable masks. Do not move or
delete it. It also imports back into `utils/` and `gui/`, so running it
standalone needs the repo root on `sys.path`.

**Deliberately unused code, kept on purpose.** Do not "clean" these away:

- `processing/wire_matcher.py`: epipolar NCC matcher. Its only consumer is
  `StereoProcessor.compute_disparity_wire_guided()`, which the GUI never calls.
  Kept because it does **not** rely on the parametric assumption described
  above, and is the obvious fix if that assumption starts failing. Not yet
  validated on real data.
- `StereoProcessor.process_wire_masks()`: headless version of GUI steps 2-3,
  useful for batch scripts.

Both carry a `[SIN USO EN EL FLUJO ACTUAL]` banner in their docstring. If you
add more dead-but-intentional code, mark it the same way.

**`data/captures/` and `data/calibration/` are versioned** (177 and 1073 files).
`.gitignore` tries to exclude `data/captures/`, but the rule was added after the
files were committed, so it has no effect on them. Decide deliberately before
adding more.

## Critical configuration

### Camera setup (on the Pi)

`/boot/firmware/config.txt`:
```
camera_auto_detect=0
dtoverlay=imx477,cam0
dtoverlay=imx477,cam1
gpu_mem=128
```
Reboot after changing.

### Resolution (`config/camera_config.py`)

```python
max_resolution     = (4056, 3040)   # full sensor
capture_resolution = (4056, 3040)   # photos AND calibration
preview_resolution = (1920, 1440)   # live view only
sensor_mode_bits   = 12
framerate          = 15
```

### Optical discipline

The focus and aperture rings must be **set and locked before calibrating** and
not touched afterwards. Moving focus changes the focal length, and `fx` is the
focal length in pixels: 1% of drift is 1% of scale error on every reconstructed
distance. Calibrate on the **integrated support** that will be used for the
experiment, never on a different mount.

Full derivation, with the illumination requirements, in
`Documentation/LINKU_Deliverable_DarkRoom_Illumination/`.

## Data layout

```
config/camera_settings.json               camera settings
data/calibration/calibration_data.json    active calibration (see caveat above)
data/calibration/calibration_YYYYMMDD_HHMMSS/   sessions
data/captures/stereo_YYYYMMDD_HHMMSS/     stereo pairs
data/ai_dataset/{mask,path}_dataset/      training samples
data/models/mask_model.pkl                the RandomForest
data/results/                             exported PLY/XYZ/PCD/OBJ
logs/stereo_photogrammetry.log            rotating, 10 MB
```

## Documentation

LaTeX deliverables under `Documentation/`, compiled with the repo-root script:

```powershell
.\compilar.ps1 "Documentation\LINKU_Deliverable_Calibration_Method"
```

Cited sources go in each deliverable's `Sources/` folder and into its
`bibs/sample.bib`. Papers still being read live in
`Documentation/Investigacion/`.

**`LINKU_Project_APSCO_Deliverable_D5_Report__submitted___v2_` was submitted to
APSCO and is not edited.** The one worked on is the near-identical
`LINKU_Project_SubDeliverable_D5_CameraSystem_Report__v2_`. Check for
`submitted` in the folder name before touching anything under `Documentation/`.

`LINKU_Experiment_TV2` is the operating record of the dark-studio experiment
(TV2 is a studio of the PUCP Faculty of Communications). Its chapter 2
registers the acceptance criteria **in advance**; they are not to be
re-derived at analysis time, and amending them means a dated revision of that
chapter. Its results chapter is deliberately empty until the session is run.

Two markdown documents sit beside the LaTeX ones:

- `LINKU_CameraPayload_Paper_Dossier.md` is the current consolidated source
  document, written for co-authors of a joint paper. Every claim carries a
  status tag (MEASURED, DERIVED, ASSUMED, PLANNED, DEFECT), and section 11
  lists the contradictions between our own deliverables.
- `INFORME_TECNICO_PROYECTO_LINKU.md` is a snapshot dated 16 February 2026,
  kept as a record of how the work evolved. Its header lists the claims later
  measurement contradicted. Do not cite it as current state.

## Technology stack

Python 3.9+, PyQt5 (install via apt on the Pi, not pip), OpenCV 4.5+, numpy,
scipy, scikit-image, scikit-learn, libcamera-apps, colorlog.

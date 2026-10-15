# LINKU Camera Payload: Technical Dossier for the Joint Paper

**Author of the payload and of this dossier:** Jose Sifuentes, Pontificia Universidad Católica del Perú
**Project:** LINKU, APSCO, Work Package WP-2200
**Date of this compilation:** 15 October 2026
**Status of the payload:** laboratory prototype, pre-PDR. Not flight qualified.

---

## 0. How to use this document

This is a source document, not a draft paper. It collects everything the camera payload has produced so that the three of us can decide together what belongs in the joint paper and what stays out.

It is written for the two of you working on the other payloads (star tracker, microscopy) and for anyone who ends up doing the integration writing. It assumes you know computer vision but nothing about this payload.

**Every claim carries a status tag.** Please respect these when lifting text:

| Tag | Meaning |
|---|---|
| **MEASURED** | A number produced by running something, with the data still on disk |
| **DERIVED** | Computed from a datasheet or a primary standard, reproducible from the stated constants |
| **ASSUMED** | A value adopted by project decision, or carried across devices without a datasheet to back it |
| **PLANNED** | Designed and specified, not yet executed |
| **DEFECT** | A bug or inconsistency found in our own code or documents, verified |

The last category is unusual in a source document. I am including it deliberately: several of these defects contradict statements that already appear in our submitted deliverables, and if they reach the paper unflagged they are the kind of thing a reviewer finds. Section 11 collects them.

**Section 12 is written specifically for you two.** It isolates the parts of this payload's methodology that are not tether-specific and that your payloads very probably need as well: calibration validity, sensor characterisation, illumination control, and shutter behaviour. I have not invented anything about your payloads there; it is a list of questions and shared machinery, not claims.

---

## 1. Mission context

### 1.1 What LINKU is

LINKU is a multi-satellite tether experiment with three bodies.

| Body | Role | Geometry | Reference mass |
|---|---|---|---|
| SAT-A | Carrier. Houses, protects and releases the coupled SAT-BC assembly | 12U CubeSat compatible (EnduroSat 12U reference) | n/a |
| SAT-B | Main tether-experiment satellite. Tether storage, separation interface, experiment electronics, comms | Dodecahedral approximation of a sphere, equivalent diameter ≈ 20 cm | 5 kg |
| SAT-C | Second tether end body. No dedicated active ADCS; post-separation motion governed by tether interaction | Dodecahedral, equivalent diameter ≈ 10 cm, internal volume ≈ 1U | 0.5 kg |

Configuration sequence: **SAT-ABC** (integrated) → **SAT-BC** (released from A) → **SAT-B / SAT-C tethered system** (after internal separation). SAT-A then continues independently.

**Technical objectives of the mission:** validate a safe tether-deployment platform for nanosatellites; study the behaviour of a **non-conductive** tether in orbit against ground experiments and pre-flight simulation; evaluate passive gravity-gradient stabilisation for low-cost small-satellite systems.

### 1.2 Operational numbers that constrain the camera

| Quantity | Value | Status |
|---|---|---|
| Nominal tether length | 100 m | Requirement MR-002, SYS-DEP-007 |
| Maximum optical observation range | up to ≈ 100 m | Design |
| Tether diameter, analytic worst case | 0.8 mm | Design |
| Tether diameter, experimental proxy and radiometric calculation | 1 mm | Design |
| Nominal relative separation velocity SAT-B / SAT-C | 0.5 to 1 m/s | From Deliverable D4 |
| Conservative sizing separation velocity | 1.5 m/s | SYS-DEP-006 |
| Required terminal relative velocity near full extension | ≤ 0.1 m/s | SYS-DEP-008 |
| Orbit | 700 km circular, e = 0, inclinations 30° and 94°, period ≈ 96 min | Design |
| ADCS angular rate before separation commands | ‖ω‖ < 1 deg/s | SYS-ADCS-001, SYS-ADCS-004 |

That last row matters more than it looks. The 1 deg/s figure in the ADCS requirement and the 1.05 deg/s figure the camera payload derives independently from rolling-shutter shear (Section 8) are **not the same number arrived at twice**. They coincide numerically by accident. Section 8 explains why ours is a software artefact rather than a sensor limit.

### 1.3 Why the payload exists

Three other sensors already fly on this mission and none of them can answer the question the cameras answer:

- **GNSS** gives the relative separation vector `r_BC(t) = r_C(t) − r_B(t)`. It says how far apart the two bodies are. It says nothing about the **shape** of the tether between them.
- **Tether-tension load cells** give a scalar force at the two attachment points. A scalar cannot distinguish straight from curved from oscillating from entangled.
- **Inertial sensors** give spacecraft attitude and rotational dynamics, not tether spatial geometry.

The camera payload's mission objectives, as stated in the D5 reports:

1. Verify nominal tether deployment and identify anomalies during the SAT-B / SAT-C separation process.
2. Characterise the three-dimensional spatial geometry of the tether during post-deployment operations.
3. Support analysis of tether oscillations, curvature and deformation.
4. Provide visual geometric information complementary to GNSS, inertial and tension measurements.

Anomalies to be detected in stage 1: tether entanglement, asymmetric deployment, rebounds, unexpected oscillatory behaviour, partial deployment, sudden changes in tether geometry.

**Two operational stages with opposite optical priorities.** During deployment the cameras are body-fixed, attitude transients drag the target across the field, and full ADCS stabilisation may not be available, so the priority is **wide-field situational awareness**. After deployment the system settles toward gravity-gradient alignment and the priority becomes **geometric reconstruction accuracy**. A single optical configuration cannot optimise both. This tension is unresolved at design level and is the origin of the "hybrid optical approach" proposal.

---

## 2. Hardware

### 2.1 The laboratory rig, as built

This is the hardware that produced every measurement in this dossier.

| Item | Specification |
|---|---|
| Sensors | Two Raspberry Pi High Quality Cameras, Sony IMX477 |
| Native resolution | 4056 × 3040 px (12.3 MP) |
| Pixel pitch | 1.55 µm |
| Active area | 6.287 × 4.712 mm |
| Lens | Arducam C1508ZM04, C-mount, 8 mm, manual aperture f/1.6 to f/16, MOD 0.15 m |
| Field of view | 42.9° H × 32.8° V |
| Stereo baseline | 100 mm, fixed, set by the satellite mounting envelope |
| Support | FDM additive manufacturing, parallel optical alignment. Integrated cameras + CM5 rigid support assembled and verified 13 Oct 2026 |
| Processing unit | Raspberry Pi Compute Module 5, quad-core Arm Cortex-A76 at 2.4 GHz, up to 16 GB LPDDR4X, dual MIPI CSI-2 |
| Synchronisation | Software, via libcamera. No hardware trigger exposed on the CM5 |

**Field of view, and a correction we have already published.** The lens manufacturer quotes 58.4° H × 44.6° V. Those figures are for the lens's own 2/3″ optical format, which is **larger** than the IMX477. Using the correct active width in

$$\mathrm{FOV} = 2\arctan\left(\frac{W}{2f}\right)$$

gives 42.9° H × 32.8° V, which agrees with Arducam's own separately published 44° H figure for this lens on a 1/2.3″ IMX477. An earlier revision of our D5 report quoted the 2/3″ numbers and **overstated the horizontal field of view by about 36 %**. The correction is in the current revision. If any of you reuse an older copy, check this first. (**DEFECT**, found and fixed.)

**Software synchronisation validity.** The sequential libcamera trigger is valid for the quasi-static laboratory dynamics we work with, meaning relative velocities below about **5 cm/s**. Flight separation velocities are 0.5 to 1.5 m/s, one to two orders of magnitude higher. Neither D5 document addresses that gap. It is a real open item, not a presentational one. (**DEFECT**, unresolved.)

The one real synchronisation figure we have measured: the reference stereo pair `stereo_20260213_140535` records a **10.4 ms** inter-camera time difference, logged as "EXCELENTE" by our own metadata.

### 2.2 The flight sensor decision, and the contradiction you need to know about

**The recorded flight-sensor decision is the Raspberry Pi Camera Module 3 class sensor, Sony IMX708, fixed-focus variant, SKU B0308.** Not the IMX477. The IMX477 is laboratory hardware.

Chosen intrinsics as recorded:

| Parameter | Value |
|---|---|
| Sensor | Sony IMX708 |
| Sensor size | 6.45 × 3.63 mm |
| Max resolution | 4608 × 2592 px (11.9 MP) |
| Pixel size | 1.4 µm |
| Lens focal length | 4.74 mm |
| Aperture | f/1.8, fixed |
| Field of view | 66° H / 75° D / 41° V |
| Focus | Fixed, manufacturer-stated 1.5 m to infinity |

Selection reasoning: at every tested distance the B0308 matched the IMX477 baseline's tether pixel resolution within a few percent; the wider IMX708 variants (102° and 120° H) lost resolvable pixels on the thread noticeably earlier, around 2 m; the 64 MP Hawk-eye resolved furthest but its data volume is irreconcilable with the downlink budget and it is not covered by the mechanical mounting CAD; and the **fixed-focus** B0308 was preferred over its autofocus siblings B0306 and B0312 because a fixed lens has no moving focus mechanism to survive launch vibration or vacuum operation.

**Now the problem.** Three things do not line up, and all three are live:

1. **The two D5 documents name different sensors.** The sub-deliverable says "the IMX477-based architecture remains a suitable baseline"; the APSCO deliverable names only the IMX708 and never mentions the IMX477 or the OV64A40. Both are "12 MP class", but **every optical number we have published (circle of confusion, hyperfocal distance, depth of field, geometric limit, projected width) is computed for the IMX477 and does not transfer to the IMX708.** (**DEFECT**.)

2. **The camera count does not close.** The sub-deliverable validates a **stereo pair** on a 100 mm baseline and states that both cameras used for geometric reconstruction must share calibrated intrinsics and extrinsics. The APSCO deliverable requires **three cameras, two on SAT-B and one on SAT-C** (SYS-MEAS-002). The SAT-C camera has no stereo partner, so the reconstruction pipeline described in Sections 5 and 6 **cannot run on SAT-C imagery at all**. Neither document reconciles this. (**DEFECT**.)

3. **The sunshade is sized for a different optic.** The APSCO structural chapter builds the sunshade geometry around an "approximate 80° field of view". No configuration we have characterised has an 80° field. The B0308 is 66° H, the fitted IMX477 is 42.9° H. (**DEFECT**.)

For the paper, my recommendation is that we either resolve these before writing or state the laboratory configuration explicitly as the validated one and present the flight configuration as a forward decision with its optical analysis pending. I would not paper over it.

**The B0308 has not been purchased.** Procurement is realistically January 2027. All laboratory work proceeds on the IMX477.

### 2.3 Optical comparison of candidate configurations

Computed for a 1 mm thread with the project's own tool, `calculate_cam/camera_dof_visualizer.py`. "1 px limit" is the distance at which the thread collapses to exactly one pixel, the practical geometric detection limit.

| Sensor | Lens | MP | FOV H | px @ 0.5 m | @ 2 m | @ 10 m | @ 100 m | 1 px limit |
|---|---|---|---|---|---|---|---|---|
| **IMX477 (fitted today)** | **8.0 mm** | 12.3 | 42.9° | 10.49 | 2.59 | 0.52 | 0.0516 | **5.17 m** |
| IMX477 | 6.0 mm | 12.3 | 55.3° | 7.84 | 1.94 | 0.39 | 0.0387 | 3.88 m |
| Hawk-eye OV64A40 | 5.1 mm | 63.6 | 71.9° | 12.75 | 3.16 | 0.63 | 0.0631 | 6.31 m |
| IMX708 Wide (B0310) | 2.87 mm | 11.9 | 96.7° | 4.12 | 1.03 | 0.21 | 0.0205 | 2.05 m |
| IMX708 Wide 102° | 2.75 mm | 11.9 | 99.1° | 3.95 | 0.98 | 0.20 | 0.0196 | 1.97 m |
| **IMX708 Standard (B0308, chosen)** | **4.74 mm** | 11.9 | 68.5° | 6.84 | 1.70 | 0.34 | 0.0339 | **3.39 m** |
| *IMX296 global shutter* | *16.0 mm* | *1.6* | *17.7°* | *9.69* | *2.36* | *0.47* | *0.0469* | *4.70 m* |
| *IMX296 global shutter* | *8.0 mm* | *1.6* | *34.5°* | *4.76* | *1.18* | *0.23* | *0.0234* | *2.35 m* |
| *IMX296 global shutter* | *6.0 mm* | *1.6* | *45.0°* | *3.56* | *0.88* | *0.18* | *0.0176* | *1.76 m* |

**(DERIVED.)** Italic rows are a global-shutter candidate under evaluation, not a flight-sensor decision.

**The single most important line in this table: at 100 m, not one of the nine configurations keeps the 1 mm thread above 1 pixel.** The values span 0.018 to 0.063 px, roughly two orders of magnitude below the geometric detection limit. At that range detection is not a geometric problem at all; it depends on the sub-pixel radiometric regime, specular reflection against a dark background, treated in Section 7.

### 2.4 Why megapixels are the wrong figure of merit

This is a result worth putting in the paper, because it is counter-intuitive and it generalises.

Thin-lens magnification, with `f` the focal length, `u` the object distance:

$$m(u) = \frac{f}{u-f}$$

Object-space pixel density, with `R_h` the horizontal resolution and `W` the sensor width:

$$\rho_{obj}(u) = \frac{R_h}{W}\cdot m(u) = \frac{R_h}{W}\cdot\frac{f}{u-f}$$

Pixels across a thread of diameter `d`:

$$N_{px}(u) = \frac{R_h\,f\,d}{W\,(u-f)}$$

In the far field (`u >> f`, true for every distance of interest here):

$$N_{px} \approx \frac{R_h}{W}\cdot\frac{f\,d}{u}$$

**Total resolution does not appear.** Only `R_h/W`, which is the reciprocal of the pixel pitch, multiplied by the focal length. A sensor with far fewer total pixels wins if its pixels are proportionally larger or its lens is longer.

Worked case, at `u = 100 m`, `d = 1 mm`:

- **IMX296, 1.6 MP, 6 mm:** `R_h = 1456`, `W = 4.97 mm` → `ρ = 293.0 px/mm` (pitch 3.41 µm), `m = 6.000e-5`, `N_px = 0.0176 px`
- **IMX708 B0308, 11.9 MP, 4.74 mm:** `R_h = 4608`, `W = 6.45 mm` → `ρ = 714.4 px/mm` (pitch 1.40 µm), `m = 4.740e-5`, `N_px = 0.0339 px`

Ratio: `(293.0/714.4) × (6.0/4.74) = 0.410 × 1.266 = 0.519`, matching `0.0176/0.0339` exactly.

**A 7.4× gap in total pixel count produces a 1.9× difference in thread pixels.** The IMX296's pixels are 2.44× larger, so despite having 3.16× fewer horizontal pixels it loses only a factor 0.410 in sensor-side density, and the longer lens recovers 1.266× of that.

Independent small-angle cross-check, no lens formula: a thread of diameter `d` at distance `u` subtends `θ ≈ d/u`; a sensor with `R_h` pixels across `FOV_H` puts `N_px ≈ R_h θ / FOV_H` on it. The governing quantity is **pixels per degree**. IMX296 + 6 mm: `1456/45 ≈ 32 px/°`. B0308: `4608/68.5 ≈ 67 px/°`. Ratio 0.48, within 8 % of the 0.52 from the full equation, the gap being the small-angle approximation. The two methods agree to within about 10 % for all fields in the table.

---

## 3. The measurement problem

This section is the scientific core of the payload and, I think, the part most worth generalising in a joint paper.

### 3.1 Conventional photogrammetry fails, and we measured how

Three experiments, all run on the calibrated rig inside the dark enclosure, processed with Agisoft Metashape as the external reference platform. **(MEASURED.)**

| Experiment | Target | Result |
|---|---|---|
| Dense stereo | Volumetric reference object (a bottle) | Disparity map correctly identifies the target, but **non-physical disparity responses appear across empty background regions**, producing phantom geometric structures. Raw cloud carries numerous outliers and phantom surfaces. Extensive manual filtering required, so not autonomous. |
| Structure from Motion | 1 mm tether proxy, **with** environmental texture (floor patterns, object edges, surrounding structures) | Pipeline detects features, establishes correspondences, aligns cameras, produces a valid reconstruction. But **most recovered geometry originates from the surroundings, not the tether.** |
| Structure from Motion | 1 mm tether proxy, **background removed by segmentation** | **Complete failure. "Zero Resolution" error.** No camera alignment, no sparse cloud, no model. |

The third row is the key result and we stated the conclusion carefully: *"the primary limitation is not background interference but insufficient visual information within the tether itself"*, and therefore *"the reconstruction challenge is not merely a segmentation problem but a structural limitation of feature-based approaches."*

Put plainly: the standard pipeline breaks at its very first stage. A target occupying 1 to 3 pixels does not contain enough distinctive keypoints for reliable detection, and no amount of improvement downstream repairs that.

### 3.2 What replaced it

A geometry-driven pipeline that uses no keypoints at all:

```
intensity extraction and segmentation
  → skeleton and endpoint detection
  → curve tracking
  → stereo correspondence along the extracted trajectories
  → triangulation
```

*"None of these stages require keypoints: radiometric contrast and geometric continuity are sufficient on their own."*

The target is treated as a **continuous one-dimensional structure**, not as a cloud of independent feature points. That single modelling decision is what makes the problem tractable, and it is the transferable idea.

### 3.3 The four detectability regimes

Our D5 analysis identifies four independent drivers of whether the tether is visible at all:

1. **Geometric sampling.** Three regimes relating apparent width `w_p` to pixel pitch `p`: well sampled, critically sampled, sub-pixel.
2. **Radiometric contrast.** High, medium, low regimes against the background.
3. **Directional illumination.** Near-specular versus off-specular geometry. Apparent brightness depends on solar incidence angle, observation angle, surface material and the local tether orientation relative to the line of sight.
4. **Temporal visibility.** Visible, marginally visible and invisible states alternating **with no change in the tether's physical properties**, purely from changing reflection geometry.

**Blooming** is treated explicitly and carefully. Saturated charge spreading into neighbouring pixels artificially enlarges the apparent width of thin structures. We treat this as a possible **aid to initial detectability** and state explicitly that it is **not** a geometric measurement: *"this apparent width does not represent the true physical diameter of the tether."* Anyone measuring width from a saturated image is measuring the sensor, not the object.

---

## 4. Software architecture

One PyQt5 desktop application. Entry point `main.py`. It does not require cameras: if libcamera or the sensors are absent it starts in "Processing Only Mode" and processes archived captures, which is how all offline analysis is done.

Four pages behind a sidebar: Dashboard (live preview and capture), Calibration, Processing, AI.

The Processing page offers two modes. The **default** is `Geometric (Wire Tracking)`, the pipeline of Section 5. `Dense SGBM (Traditional)` is retained as the fallback and is what runs automatically when no cable mask has been configured. It is the same `process_stereo_pair` routine that produced the phantom-geometry result of Section 3.1.

Hardware interface: `libcamera-jpeg` subprocess calls with an explicit sensor mode string, `--mode 4056:3040:12:P`. The explicit mode matters and Section 6.2 explains why.

---

## 5. The reconstruction pipeline, stage by stage

Everything in this section was read directly from the source. Parameters are the shipped defaults.

Pipeline order:

```
segmentation → endpoint detection → path tracing → rectification
  → parametric stereo matching → triangulation → metrics → export
```

### 5.1 Segmentation

Five classical methods are implemented. The production default is **morphological top-hat**, not Canny.

Processing order for every method: pick working image → grayscale → method → post-processing → connected-component cleanup → upscale to full resolution.

**Preview downscaling, which affects everything downstream.** Before any method runs, the image is reduced so its longest side is at most **1280 px** (`INTER_AREA`). All adaptive thresholds are therefore computed on the **downscaled histogram**.

> **DEFECT.** The segmentation is not scale invariant. A 4056 × 3040 capture does not segment identically to its preview. The code acknowledges this in a comment but does not correct for it.

**The default method, top-hat:**

```python
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))   # k = 25
tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
threshold = np.mean(tophat) + (thresh/10.0)*np.std(tophat)      # thresh = 40
edges = (tophat > threshold).astype(np.uint8) * 255
```

The white top-hat is `gray − open(gray, kernel)`, which isolates bright structures **thinner than the structuring element**. For a thread on a dark background this is well matched to the physics, and it is a better choice than Canny for this target.

All four non-Canny methods use the same adaptive rule:

$$\tau = \mu + \frac{k}{10}\sigma$$

| Method | Operator | Parameters (default) |
|---|---|---|
| Canny | `Canny(GaussianBlur(gray,(3,3)), low, high, L2gradient=True)` | low 10, high 30, aperture 3 |
| Sobel | `sqrt(Sx²+Sy²)`, threshold `μ+kσ/10` | ksize 3, k 20 |
| Laplacian | `|Laplacian(blur)|`, threshold `μ+kσ/10` | ksize 3, k 20 |
| Morphological gradient | `MORPH_GRADIENT`, ellipse, threshold `μ+kσ/10` | ksize 5, k 20 |
| **Top-hat (default)** | `MORPH_TOPHAT`, ellipse, threshold `μ+kσ/10` | **ksize 25, k 40** |

**Post-processing**, identical for all five, strict order dilate → erode → close, always a 3×3 ellipse regardless of method or resolution. Defaults: dilate 3, erode 0, close 0.

**Connected-component cleanup.** `connectedComponentsWithStats`, 8-connectivity. Keep every component whose area is at least **10 % of the largest component's area**. The only criterion is relative pixel area: no absolute floor, no length, aspect-ratio, solidity or elongation test, and `findContours` is never called. The documented rationale is that a broken cable yields several large components and all should survive.

**Guarantees on the output mask:** single-channel uint8, strictly two-valued {0, 255}, same dimensions as the input. **Not** guaranteed: connectivity, a single component, non-emptiness (a bad threshold returns an all-zero mask and nothing checks), or thinness.

**Left and right.** The production entry point presents one dialog with a switch button, so a single parameter set governs both images. But the adaptive threshold is recomputed per image, so the **parameters** are shared while the **effective absolute thresholds** differ between left and right. Worth stating precisely if this goes in the paper.

### 5.2 The AI segmenter, and why it does not currently count

A trained model exists. It is a **scikit-learn Random Forest**, not deep learning. There is no torch, tensorflow, onnx or tflite anywhere in the repository.

**Features**, nine per pixel:

```python
hsv  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
b3   = cv2.GaussianBlur(gray, (3, 3), 0)
b9   = cv2.GaussianBlur(gray, (9, 9), 0)
lc   = (gray - b9).clip(-127, 127) + 127          # local contrast
features = np.stack([B,G,R,H,S,V,b3,b9,lc], axis=1).astype("float32") / 255.0
```

Purely per-pixel colour plus two blur scales. No spatial or positional feature, no texture bank, no multi-scale beyond 3×3 and 9×9.

**Training.** 6 annotated stereo pairs. Each contributes two images (left and right), then ×5 augmentation: identity, horizontal flip, vertical flip, brightness +35 DN, brightness −35 DN. Resize to 256 × 192, so 49 152 pixel rows per image. Balance to at most 40 000 positives at a 1:4 positive:negative ratio, seed 42.

```python
RandomForestClassifier(n_estimators=100, max_depth=12, min_samples_leaf=3,
                       n_jobs=-1, random_state=42, class_weight="balanced")
```

Reported: **F1 = 0.97, precision 0.94, recall 0.99**.

> **DEFECT, and this one has already propagated into three of our documents.** The evaluation predicts on `X_tr`, the same array passed to `fit`, five lines earlier. There is no train/test split, no cross-validation, no held-out set anywhere. **These are training scores and are optimistic by construction.** Our own work plan already flags it and prescribes the fix: split **by capture session, not by augmented image**, otherwise augmented copies of the same photograph leak between train and validation.

> **DEFECT, more serious, verified end to end.** The AI mask **never reaches the downstream pipeline.** The production entry point does this:
>
> ```python
> tuner.original_img = left_img
> tuner._prepare_preview()
> tuner.update_detection()        # recomputes the CLASSICAL mask
> mask_left = tuner.get_current_mask()
> ```
>
> and `update_detection()` unconditionally reassigns `self.mask_result` with the classical result. The same happens in `apply_and_close()`, which calls `update_detection()` on its first line. So if an operator clicks "apply AI model" and sees the Random Forest mask on screen, that mask is discarded on exit. What endpoint detection receives is always the top-hat mask.
>
> The model is trained and can be previewed. It is **not** integrated into the path that produces results. Our documents currently describe it as *"Implemented & trained... Integrated as a selectable inference mode in the segmentation tuner."* The first half is true. The second half is not, in the shipped code path. The fix is a few lines; until it is made, the claim should not appear in the paper.

A second consequence worth noting: in the one workflow where the AI mask does survive (single-image mode, click AI then save to dataset without triggering a recompute), the AI output can be fed back in as a training label with no human verification step. That is a self-training loop and it should be closed deliberately.

**Dataset on disk.** Two independent stores managed by the same class:

```
data/ai_dataset/mask_dataset/     # images + masks, for the Random Forest
data/ai_dataset/path_dataset/     # images + masks + path JSON, for the model that does not exist
  images/0001.jpg, 0001_right.jpg     (JPEG, quality 95)
  masks/0001.png,  0001_right.png     (PNG, lossless)
  paths/0001.json  {"left": [[x,y],...], "right": [[x,y],...]}
  metadata.json
```

Deduplication is MD5 over a 64 × 64 grayscale downsample. The docstring calls this "perceptual" but **MD5 is an exact hash**: a one-DN change anywhere flips the digest, so it catches only byte-identical downsamples.

Current contents: mask dataset **6 labelled stereo samples** (of 65 available capture sessions); path dataset **1 labelled sample**, against an estimated minimum of 30 to 100 for training the second model.

> **DEFECT.** `delete_sample()` removes `NNNN.jpg`, `NNNN.png` and `NNNN.json` but never `NNNN_right.jpg` or `NNNN_right.png`, orphaning right-camera files whose id can later be reissued, producing a mismatched pair.

### 5.3 Endpoint detection

Input mask binarised at `> 127`.

**Skeletonisation:** `cv2.ximgproc.thinning` with `THINNING_ZHANGSUEN`. Fallback on ImportError is an iterative morphological skeleton with a 3×3 cross. The skeleton is deliberately **not** dilated, because dilation created false endpoints at distance-transform borders.

**Candidates** are degree-1 skeleton pixels, found by 3×3 convolution with the centre zeroed:

$$N(p)=\sum_{q\in\mathcal{N}_8(p)} S(q), \qquad \text{candidate} \iff S(p)=1 \wedge N(p)=1$$

**Clustering.** Greedy first-wins cover by 80 px balls in (y,x) space, keeping a real skeleton pixel (not a centroid) as each representative. This is not transitive-closure clustering.

**Farthest-pair search.** Exhaustive over all pairs, maximising geodesic distance along the 8-connected skeleton graph, with step weights 1.0 axial and 1.414 diagonal.

A design decision worth recording because it came from a real bug: **all clustered candidates compete before any border or thickness filtering**. The reasoning is that a spurious candidate mid-wire can never have the longest geodesic against the two true extremes, so letting everyone compete rejects spurious points by construction. Filtering by border *first* was the original defect: a legitimate tip leaving the frame got discarded and the spurious point won by default.

**Canonical orientation.** After detection the pair is swapped so `start` is the upper point:

$$(\mathrm{start},\mathrm{end}) \leftarrow (\mathrm{end},\mathrm{start}) \iff y_s > y_e \ \lor\ (y_s = y_e \land x_s > x_e)$$

This guarantees a consistent top-to-bottom direction in both cameras, which the matcher in 5.5 depends on absolutely.

**Failure cascade** when no connected pair exists (fully looped or fragmented skeleton): apply border and thinness filters and retry → dilate the skeleton by one iteration to bridge gaps and retry → retry with Euclidean distance → fall back to the contour method. A pure closed loop produces zero degree-1 candidates and drops straight to the contour method; there is no explicit loop detection.

> **DEFECT, methodological.** `_compute_geodesic_distance` is a FIFO BFS with **non-uniform edge weights** (1 and 1.414) and `visited` marked at enqueue time. That is not Dijkstra: it returns the cost of the fewest-hops path, not the minimum-weight path. For a farthest-pair argmax on a 1-px skeleton this is practically harmless, but it should be described honestly and not called a geodesic shortest path.

> **DEFECT, dead code.** `_prune_short_branches(min_length=40)` exists and is never called anywhere. Clustering replaced pruning because a fixed prune length proved fragile. Do not describe pruning as part of the method.

| Parameter | Default | Nature |
|---|---|---|
| mask binarisation | > 127 | magic |
| cluster radius | 80 px | **magic, resolution independent** |
| border margin | 50 px | **magic, resolution independent** |
| DT thin threshold | 2.0 px | magic |
| crossing radius | `max(15, DT+8)` | magic |
| crossing count reject | ≥ 4 | topological |
| circle samples | 360 | n/a |
| diagonal step weight | 1.414 | hardcoded √2 |

### 5.4 Path tracking (SmartWireTracker)

A depth-first search over the mask with backtracking and momentum.

**Auto-scaling preamble.** If the maximum distance transform of the mask exceeds 22.5 px, the whole mask is downscaled so that `max(DT) = 15.0`, and every length downstream is in scaled pixels. Outputs are converted back at the end. This makes the tracker thickness-adaptive but means `dt_profile` is a rescaled estimate, not the true full-resolution distance transform.

**Base parameters:** `step_size = 5`, `search_radius = 20`, `wire_radius = max(9, max(DT))`, `max_coverage_radius = search_radius − step_size = 15`. The documented invariant is `max_coverage_radius < search_radius`, otherwise the tracker goes blind on the next step because its whole search disc is already marked visited.

**Candidate neighbourhood**, adaptive on local thickness `dt`:

| `dt` | search radius | min distance | allow 1-px gaps |
|---|---|---|---|
| < 3 (very thin) | 6 | 1.0 | yes |
| 3 ≤ dt < 6 | 12 | 2.0 | yes |
| ≥ 6 | 20 | 2.5 | no |

A pixel is a candidate if it falls in the annulus and the straight segment to it stays on the mask, sampled at 2 samples per pixel.

**The scoring function.** This is the heart of the tracker and the thing a learned model would replace:

$$S_{\text{geo}} = \hat d \cdot \hat m, \qquad
S_{\text{thick}} = \exp\!\left(-\frac{|DT_{\mathrm{cur}} - DT_{\mathrm{opt}}|}{5}\right), \qquad
S_{\text{center}} = \frac{DT_{\mathrm{opt}}}{\max(r_{\text{wire}},1)}$$

$$\boxed{S_{\text{total}} = 1200\,S_{\text{geo}} + 600\,S_{\text{thick}} + 300\,S_{\text{center}} + P_{\text{lat}}}$$

with `P_lat = −800` when more than one flow group exists and the option's lateral offset exceeds `1.1 × wire_radius`.

**Momentum** is the normalised 5-point secant, zero until the path has 5 points:

$$\hat m = \frac{p_{-1}-p_{-5}}{\lVert p_{-1}-p_{-5}\rVert}$$

so direction continuity has an effective memory of about 25 scaled pixels.

A `dist_to_end` attraction term was **deliberately removed**: at a crossing, the direction toward the endpoint can point at the wrong strand. The argument is recorded in the source.

**Crossing handling.** Already-visited candidates are re-admitted only if the unit direction to them satisfies `d̂ · m̂ > 0.85` (a 31.8° cone) and fewer than three unvisited candidates exist. This is what allows the path to legitimately cross its own marked region at a true crossing.

**Parallel-line detection.** Options are projected onto the perpendicular to momentum, sorted by lateral offset, and split into groups wherever consecutive offsets differ by at least one full wire diameter. When more than one group exists, laterally displaced options take the −800 penalty. With the momentum term weighted 1200, a penalised option needs `ΔS_geo > 0.667` to still win, so it is a **soft** penalty, not a veto.

**Backtracking.** Triggered when no candidate survives. Pop the decision-point stack to the most recent one with alternatives remaining, unmark the visited pixels of the abandoned segment (this is what frees a crossing for the alternative branch), truncate the path, and take the next-best option. No explicit backtrack limit; bounded only by `max_iterations` and stack exhaustion.

**Stopping.** Three conditions: within 15 px of the endpoint; coverage ≥ 95 % **and** within 40 px of the endpoint; or no path with an exhausted decision stack. Plus a stagnation abort at iteration 600 if coverage < 3 % and no decision point has been created, diagnosed as "the endpoints are wrong".

Coverage:

$$\mathrm{cov} = \frac{|\{p : \mathrm{mask}(p)>0 \wedge \mathrm{visited}(p)>0\}|}{|\{p:\mathrm{mask}(p)>0\}|}$$

> **DEFECT.** `_unmark_visited` uses a larger radius than `_mark_visited` (`+4` versus `+2`, no upper cap from the local search radius, and it skips the thin-wire special case). Backtracking therefore un-marks a strictly larger disc than was marked. Undocumented asymmetry.

> **DEFECT.** `track_wire` returns `'success': True` unconditionally, even after an abort or dead end, which makes the caller's success check vacuous.

**Manual alternative.** The operator can instead draw the path by clicking points. The drawn path substitutes exactly for the tracker output and is also stored as a ground-truth label for the model that does not exist yet. Manually drawn paths carry `coverage: 1.0` and `dt_profile: None`, so the **diameter profile is unavailable** for them and falls back to zeros.

### 5.5 Stereo matching: the parametric correspondence

**Rectification first.** `cv2.stereoRectify` with `CALIB_ZERO_DISPARITY` and `alpha = 0.0`, then `initUndistortRectifyMap` to `CV_16SC2` fixed-point maps, then bilinear `remap`.

Two details that carry the whole metric scale of the project:

1. **Intrinsics are rescaled to the processed resolution** before rectifying. If the calibration was taken at a different size, `fx, fy, cx, cy` are multiplied by `sx = W/W_calib` and `sy = H/H_calib`. Distortion coefficients and R, T are untouched (normalised and purely extrinsic respectively). A warning is logged if `|sx − sy| > 0.01`.

2. **The translation vector is stored in millimetres and divided by 1000 at exactly one line**, so that `stereoRectify` yields a Q producing depth directly in metres. Every metre in this project traces back to that single division.

The docstring explicitly forbids reading `calibration_data['disparity_to_depth_matrix']` directly, because that Q is valid only at the calibration resolution. The GUI respects this.

**The matcher itself.** Both paths trace the same physical cable, so the point at `i %` of the arc length of the left path corresponds to the point at `i %` of the right path. Y is deliberately **not** used, so the method also works on unrectified images.

Procedure:

1. **Canonical direction**: reverse either path whose first point is below its last, so both run top to bottom.
2. **Cross-check**: warn (not fail) if the start-point Y disagreement exceeds 40 % of the mean path height, diagnosed as a possible U-shaped cable.
3. **Conditional border trimming**: if an endpoint sits within 2 % of an image edge, the path is trimmed so both views cover the same physical span. The decision table distinguishes six cases, the important one being that two endpoints on **left or right** edges with a Y difference under 15 px are **not** trimmed, because that lateral shift *is* the disparity. Cuts are sub-pixel interpolated.
4. **Arc-length parametrisation**: cumulative chord length, normalised to [0,1], with duplicate points removed so the interpolator does not see a zero-length segment.
5. **Resample** both paths on a common grid of `n = max(⌊min(L_L, L_R)⌋, 1000)` samples using four independent linear interpolators.
6. **Disparity**: `d_i = x_L(t_i) − x_R(t_i)`, sub-pixel float.

**There is no disparity filter, no smoothing, no outlier rejection and no RANSAC in this function.** The only rejection is image bounds. Negative and zero disparities are retained in the match list. The source comment states the omission deliberately.

**The assumption, stated plainly because it is the method's main weakness.** Parametric matching assumes both traced paths start and end at the **same physical points** on the cable and traverse it at the same rate. When that breaks (an occluded tip, a path leaving the frame, a tracker that took a different branch at a crossing) the error is **systematic and silent**. There is no epipolar check to catch it. Border trimming mitigates the frame-edge case only.

### 5.6 Triangulation

From the resolution-rescaled Q:

$$f = Q_{23}, \qquad B = \left|1/Q_{32}\right|, \qquad c_x = -Q_{03}, \qquad c_y = -Q_{13}$$

$$Z = \frac{B f}{d}, \qquad X = \frac{(x_L - c_x)Z}{f}, \qquad Y = \frac{(y_L - c_y)Z}{f}$$

Coordinates are in the **rectified left-camera frame, in metres**: X right, Y **down** (OpenCV image convention, no flip is applied anywhere), Z forward.

Note this is the scalar pinhole shortcut, not the full homogeneous `Q @ [x,y,d,1]ᵀ`. The two agree exactly when `CALIB_ZERO_DISPARITY` holds and pixels are square, which is our case, but the scalar form silently ignores any residual `cx ≠ cx'`.

`cv2.triangulatePoints` and `cv2.reprojectImageTo3D` are **not used anywhere in the repository**.

### 5.7 Metrics

The payload's actual output.

**Arc length**, as a chord sum with no smoothing:

$$L = \sum_{i=1}^{N-1}\lVert \mathbf{P}_i - \mathbf{P}_{i-1}\rVert_2 \quad [\mathrm{m}]$$

> Depth noise inflates `L`. Chord-sum arc length on a noisy 3D polyline is a known positively biased estimator, and we apply no smoothing before summing. State this if the number goes in the paper.

**Straightness**, end-to-end distance over arc length, 1 for straight:

$$\mathcal{S} = \mathrm{clip}\left(\frac{\lVert \mathbf{P}_{N-1} - \mathbf{P}_0\rVert_2}{L},\,0,\,1\right)$$

**Curvature**, Menger curvature of consecutive triples on a copy decimated to at most 500 points (the decimation is the only noise suppression):

$$\kappa_i = \frac{2\left\lVert (b-a)\times(c-b)\right\rVert}{\lVert b-a\rVert\,\lVert c-b\rVert\,\lVert c-a\rVert} \quad [\mathrm{rad/m}]$$

which is the reciprocal of the circumradius of the triangle. Endpoints are replicated and the profile is interpolated back to N samples. Reported as mean and 95th percentile.

**Diameter**, back-projecting the pixel radius from the distance transform at the local depth:

$$\varnothing_i = \frac{2\,r^{\mathrm{px}}_i\,Z_i}{f} \quad [\mathrm{m}]$$

Three caveats, all real: the DT profile is resampled onto the surviving 3D points by linear interpolation although the two sequences are not parametrised over exactly the same physical span; `dt_profile` comes from the **downscaled** mask multiplied back up; and `2·DT` is the diameter only on the medial axis, while the tracker path is only approximately centred.

### 5.8 Export

Formats: PLY, XYZ, PCD, OBJ. In production only PLY is written, as `point_cloud.ply`.

**PLY is ASCII only.** There is no binary path despite an unused `import struct`. Written with a per-point Python loop, `%.6f` coordinates, integer RGB.

**No downsampling, no normals, no outlier filtering are applied in production.** `PointCloudProcessor` implements voxel-grid downsampling (hash-grid centroid averaging, default 1 cm), PCA normals (k = 20 neighbours, oriented to `n_z ≥ 0`) and statistical and radius outlier filters, but **none of them is called by the GUI pipeline**. The exported cloud is raw.

**No format records the unit.** The `metadata` mechanism is the only place a unit could be written and the GUI never populates it.

> **DEFECT, verified numerically.** The exporter assumes colours in [0, 1] and does `(colors * 255).astype(np.uint8)`. The production cloud from `generate_point_cloud_from_matches` returns colours already as **uint8 in 0 to 255**. On a uint8 array `colors * 255` wraps modulo 256. Reproduced: an RGB of (120, 200, 30) is written to the PLY as **(136, 56, 226)**. Geometry is unaffected; **every colour in every exported geometric-path cloud is wrong.** The dense SGBM branch divides by 255 and is consistent with the exporter, so it does not have this bug.

> **DEFECT, verified numerically.** In the dense branch, `np.where(valid_mask)[0]` on a 2D boolean mask takes the **row indices**, not flattened linear indices, and they are then decoded as linear indices with `// img_width` and `% img_width`. Reproduced on a toy mask: `np.where` returns `(array([2,3]), array([3,5]))` while the true linear indices are `[15, 23]`. Colours and confidences in the dense cloud are therefore sampled from essentially row 0. Production is unaffected because it uses the geometric branch.

> **DEFECT.** The PCD writer packs RGB as `(R<<16)+(G<<8)+B` written as a decimal integer, while the header declares that field as `TYPE F` (float). Many PCD readers will mis-parse it.

### 5.9 Five different depth gates

Worth a table, because it affects what the reported metrics describe:

| Stage | Depth window |
|---|---|
| `wire_metrics.compute_wire_metrics` | 0.05 to 50.0 m |
| `generate_point_cloud_from_matches` | 0.1 to 10.0 m |
| `disparity_to_depth` | 0.2 to 5.0 m |
| `generate_point_cloud` (dense) | 0.3 to 5.0 m |
| `wire_matcher.triangulate_3d_points` | 0.2 to 5.0 m |

> **DEFECT.** The metrics are computed on the **widest** gate, so the reported length, straightness and curvature describe a **superset** of the exported point cloud. Also, `disparity_to_depth`'s comment says "3 m máximo" while the code sets 5.0 m.

### 5.10 The alternative matcher, kept deliberately

`processing/wire_matcher.py` implements epipolar NCC matching: Zhang-Suen skeleton, 9 × 9 patches, horizontal scanline search over up to 256 px of disparity, normalised cross-correlation with a 0.65 acceptance threshold, and an aggressive global MAD outlier filter (`τ = min(2·MAD, 20 px)`, with a rollback guard if fewer than 50 points survive).

It is **not in the production path** and is retained on purpose: it does not depend on the parametric assumption of 5.5, so it is the natural replacement if that assumption starts failing. It is unvalidated on real data, has no sub-pixel refinement (integer disparities only), and its `cross_check` flag is stored but never implemented.

---

## 6. Calibration

This section contains the payload's most clear-cut original result, and it is a negative one.

### 6.1 What a stereo calibration estimates

A common misconception is that intrinsics and extrinsics come from different photographs. They do not: both are recovered from the **same** images in a single joint optimisation.

| Group | Parameters | Scope |
|---|---|---|
| Intrinsics | `fx, fy, cx, cy, k1, k2, k3, p1, p2` | One set per camera, shared by every image that camera took |
| Stereo extrinsics | `R, T` | One transform for the whole rig |
| Board poses | `R_j, T_j` | One per image, discarded after the fit (nuisance parameters) |

Tilting the board does not serve the extrinsics. **It is what makes the intrinsics observable at all.**

### 6.2 Resolution and sensor mode must match

The intrinsics are in pixels, so with `p` the pixel pitch:

$$f_x = \frac{f}{p_x}, \qquad f_y = \frac{f}{p_y}$$

Any change in effective pixel pitch changes `fx` and `fy` directly. Distortion coefficients are defined on normalised coordinates and are to first order resolution independent; the four pinhole parameters are not.

The tempting assumption is that a calibration can always be rescaled by the resolution ratio. That holds **only** for a pure scaling of the same field. Sensor modes mix two operations:

- **Binning or downscaling** keeps the field and enlarges the effective pixel. All four parameters divide by the same factor. Rescalable exactly.
- **Cropping** keeps the pitch and discards part of the field. `fx, fy` are unchanged while `cx, cy` shift by the crop offset. A naive rescale is simply wrong.

Applied to the IMX477 modes:

| Mode | `s_x` | `s_y` | Interpretation |
|---|---|---|---|
| 4056 × 3040 | 1.000 | 1.000 | Full readout, the reference |
| 2028 × 1520 | 2.000 | 2.000 | Pure 2×2 binning. Rescalable exactly |
| 2028 × 1080 | 2.000 | 2.815 | Binned **and** cropped, about 29 % of the vertical field discarded. **Not rescalable** |
| 1332 × 990 | 3.045 | 3.071 | Scaled and slightly cropped. **Not rescalable** |
| 1920 × 1440 | 2.1125 | 2.1111 | The project's preview resolution. Close to a pure rescale, but a 0.066 % aspect mismatch reveals a residual crop |

This is why every calibration capture passes an explicit `--mode`: without it libcamera may silently choose a mode and then scale or crop.

### 6.3 Focus breaks the calibration; aperture is milder

**Focus.** On a manual C-mount lens, focusing physically displaces the optical group, changing the effective focal length and therefore `fx` and `fy` in direct proportion. A relative error `ε` in focal length propagates to a relative error `ε` in triangulated depth, so **1 % of focus drift becomes a 10 mm bias at 1 m**. It is a systematic bias, not noise: averaging more frames does not remove it. If the focus ring moves after calibration, the calibration is invalid. This matters here because the experiment deliberately moves the rig by hand.

**Aperture.** Focal length is nominally unchanged, so `fx, fy` are preserved. The principal point can shift slightly because stopping down changes which ray cone reaches each pixel and real irises are not perfectly centred. Measured distortion changes slightly for the same reason. Depth of field, diffraction and aberrations change substantially, but those are image-quality effects, not geometric ones. Standard practice follows: calibrate at the working aperture, do not touch the ring.

### 6.4 The degeneracy

Writing the projection for a board parallel to the image plane, distortion set aside:

$$p = \begin{bmatrix} f_x (X + t_x)/(Z + t_z) + c_x \\ f_y (Y + t_y)/(Z + t_z) + c_y \end{bmatrix}$$

exposes two exact ambiguities:

1. Between focal length `f` and board distance `t_z`. **A larger focal length at a greater distance produces an identical image.**
2. Between in-plane board translation `[tx, ty]` and principal point `[cx, cy]`.

Both are resolved only by **tilting**, which forces a single translation to explain all pattern points simultaneously. If the board is parallel to the sensor in every view, the focal length is not merely poorly estimated, **it is unrecoverable**. Triggs found an angular spread above roughly 5° necessary; Sturm and Maybank catalogued the singular configurations.

The distortion coefficients behave differently: they have no comparable ambiguity because the mapping is non-linear. What they need is **measurement where distortion is strong**, meaning the board must reach the frame edges and corners. Two parameter groups, two opposite capture strategies.

### 6.5 What actually went wrong: the measured diagnosis

**MEASURED**, over the full archive, by `tools/analyze_calibration_sessions.py`.

An earlier draft of our calibration deliverable hypothesised **defocus** as the cause of 23 failed calibration attempts. That hypothesis was tested and **refuted**.

Archive coverage: 27 directories under `data/calibration/`, 25 containing images, **424 frames**. The board is detected in **218**, which is 51 %. The failures are not uniform: the seven November 2025 sessions yield **zero** ChArUco detections across 174 images, consistent with predating the switch from a plain chessboard. The five February 2026 sessions detect at 96 to 100 %. Only those five say anything about the current setup.

Board tilt distribution over the 214 frames where a pose could be recovered:

| Board tilt | Frames | Share |
|---|---|---|
| > 2° | 198 | 92.5 % |
| > 5° | 84 | 39.3 % |
| > 10° | 52 | 24.3 % |
| > 15° | 46 | 21.5 % |
| > 20° | 43 | 20.1 % |
| > 30° | 18 | 8.4 % |
| **> 45°** | **0** | **0 %** |

Median 4.4°, mean 9.3°, maximum 43.9°.

**The board was held nearly flat against the sensor plane.** The median is below the threshold Triggs identified, only 39 % of frames exceed it at all, and **not one frame in the entire archive reaches 45°**, while the published pose generator of Rojtberg and Kuijper spans ±70°. Applying the admissibility rules, **199 of 218 detected frames, that is 91 %, are degenerate for the pinhole parameters.**

This is the textbook degeneracy above. The focal length was never recoverable from these sets, and no number of additional images of the same kind would have changed that.

**Defocus was not the problem.** Sharpness measured over the detected board region has a median Tenengrad of 5908 with the 5th percentile at 2001, and detection succeeded in essentially every February 2026 frame. No evidence of widespread focus failure.

The measurement did confirm a separate defect: the same measure computed over the **whole frame**, which is what the existing quality check does, has a median of 1902, roughly a third of the value over the board. In a dark room the empty background dominates and dilutes the signal, so the existing check is measuring mostly empty space.

**No session used full sensor resolution.** Every archived pair records 1920 × 1440, never 4056 × 3040.

### 6.6 Reprojection error is not a quality metric, demonstrated on our own data

The quantity the optimiser minimises:

$$\varepsilon_{\mathrm{res}} = \sum_{i}^{N}\sum_{j}^{M} \left\lVert p_{ij} - \pi(P_i; R_j, t_j, C) \right\rVert^2$$

Reporting it afterwards as quality is reporting the **training residual of the fit**. A degenerate set can be fitted with a very low residual, because the optimiser is free to trade focal length against board distance to match the observations.

On the best-spread archived session, 20 usable views, from `calibrateCameraCharucoExtended`:

| Parameter | Value | σ | Index of dispersion |
|---|---|---|---|
| `fx` | 2651.79 | 22.42 | 0.190 |
| `fy` | 2673.03 | 22.97 | 0.197 |
| `cx` | 926.49 | 21.11 | 0.481 |
| `cy` | 701.30 | 15.67 | 0.350 |
| `k1` | −0.182 | 0.043 | 0.010 |
| `k2` | −0.321 | 0.721 | 1.619 |
| `p1` | −0.0019 | 0.0014 | 0.001 |
| `p2` | −0.0020 | 0.0015 | 0.001 |
| **`k3`** | **3.129** | **3.714** | **4.408** |

RMS reprojection error: **1.50 px**, which our existing code would classify merely as high rather than catastrophic.

Two readings. The focal length carries **0.85 % relative uncertainty**, which by Section 6.3 is a 0.85 % scale error on every reconstructed distance, or 8.5 mm at one metre. And the higher-order distortion terms are not estimated at all: **`k3` has a standard deviation larger than its own value**, and `k2` nearly so. They are fitting noise.

An RMS of 1.50 px reveals none of this. **This is the cleanest demonstration we have, on our own data, that the industry-standard quality metric is structurally incapable of detecting the failure mode that actually occurred.** I think it belongs in the paper.

### 6.7 The currently loaded calibration

**MEASURED**, read from `data/calibration/calibration_data.json`:

- `calibration_error`: 1.5301 px
- `is_good_quality`: **false**, flagged by our own code
- `image_shape`: 1920 × 1440, not full resolution
- `images_used`: 25
- `baseline_meters`: 0.1019
- `fx, fy`: 2685.2, 2706.5
- **`cx, cy`: 694.8, 688.0**

On a 1920-wide image the principal point should sit near 960. It is at 694.8, displaced by 265 px. That is the signature of the `[tx,ty]` versus `[cx,cy]` ambiguity of Section 6.4.

A second file, `calibration_data_blender_sim.json`, reports error 0.0 with `images_used: 0`. It is **not a fit**: it is the ground truth of the Blender scene written out directly. Correct for simulation work, meaningless for hardware. Do not let these two be confused in the paper.

> **Open question we have not resolved.** The fitted `fx` of 2652 px is about **8.5 % above** the 2443 px predicted by scaling an exactly 8.00 mm lens to this resolution. Two explanations are consistent: the lens may not be exactly 8.00 mm (nominal focal lengths commonly deviate by several percent), or the 1920 × 1440 mode may crop more than the pure rescale assumed in 6.2. Resolving it requires one calibration at full resolution.

### 6.8 The guided procedure: built, validated offline, not yet wired

Four published guided-calibration systems were reviewed:

| System | Year | How it picks the next pose | What we took |
|---|---|---|---|
| AprilCal | 2013 | Suggests a target position from a library, verifying user-specified accuracy requirements | **Max ERE**, a sampling-based estimate of testing error in pixels, usable as a stopping criterion |
| Rojtberg & Kuijper | 2018 | Generates poses analytically from rules avoiding the known singularities, in milliseconds | **The complete algorithm**: parameter split, pose rules, index of dispersion, convergence test. Open-source reference implementation |
| Calibration Wizard | 2019 | Global optimisation for the pose maximally reducing expected parameter uncertainty | Confirmation that the uncertainty-driven criterion is right, plus the treatment of corner uncertainty |
| Tan et al. | 2025 | Minimises the trace of the covariance jointly over relative and absolute extrinsics | **The stereo extension** |

**The parameter split.** `C = [fx, fy, cx, cy, k1, k2, k3, p1, p2]` divides into two groups needing opposite things:

$$C_K = [f_x, f_y, c_x, c_y] \ \text{(needs angular spread)}, \qquad C_\delta = [k_1, k_2, k_3, p_1, p_2] \ \text{(needs edge coverage)}$$

**Uncertainty.** From the Jacobian `J` already computed inside the Levenberg-Marquardt step, and the image-point covariance `Σ_p`:

$$\Sigma_v = \left( J^{\top} \Sigma_p^{-1} J \right)^{+}$$

In the absence of prior knowledge the authors assume one pixel standard deviation per coordinate, `Σ_p = I`. Parameters are compared through the index of dispersion, and convergence is declared per parameter by a ratio test on successive variances:

$$\mathrm{IOD}_i = \frac{\sigma_i^2}{C_i}, \qquad r = \frac{\sigma^2_{i,n+1}}{\sigma^2_{i,n}}$$

Crucially, the parameter covariance **correlates with testing error**, which is what makes it a legitimate progress indicator, unlike an image count.

**What we built.** Four modules, none depending on a camera or on PyQt, so all can be exercised offline:

| File | Contents |
|---|---|
| `camera/calibration_guidance.py` | Per-frame quality gate, degeneracy and novelty tests, parameter uncertainty, index of dispersion, convergence ratio test, approximate Max ERE |
| `camera/guided_session.py` | The continuous-capture loop. **A rejected frame does not consume a slot**, so asking for 25 views yields 25 that passed both gates |
| `tools/analyze_calibration_sessions.py` | The retrospective diagnosis of 6.5 |
| `tools/replay_guided_session.py` | Replays an archived session frame by frame, no hardware |

The session refuses to report itself complete until the accepted views cover four tilt bins with at least three each:

| Bin | Tilt | Serves |
|---|---|---|
| frontal | 0 to 10° | distortion terms, with the board at the image edges |
| slightly tilted | 15 to 30° | pinhole parameters |
| clearly tilted | 30 to 45° | pinhole parameters |
| strongly tilted | 45 to 70° | pinhole parameters |

**Validation by replay. MEASURED.**

| Session | Offered | Kept | Tilt spread | Verdict |
|---|---|---|---|---|
| `...152124` | 25 | 3 | 1.1° | Only the frontal bin filled; 18 frames refused as duplicate poses |
| `...155926` | 25 | 12 | 41.0° | Three bins filled, 45 to 70° empty |
| `...160735` | 20 | 9 | 29.4° | Three bins filled, 45 to 70° empty |

All three are refused completion, for the same reason: no archived session contains a single view above 45° of tilt. The first row is the clearest demonstration of the contract: 25 frames offered, 3 kept, because the other 22 carried no information the first 3 had not already supplied. **A procedure that counts photographs would have recorded that session as complete.**

**Status: the logic works and is validated offline. It is not yet wired into the calibration dialog, which still runs the countdown flow.** Do not describe it as deployed.

### 6.9 Proposed acceptance criteria

| # | Criterion | Rationale |
|---|---|---|
| C1 | All parameters converged by the ratio test | The session has stopped learning |
| C2 | Max ERE below the accuracy budget | Predicted testing error at the worst point in the image |
| C3 | Bias ratio low | The residual is noise, not unmodelled structure |
| C4 | A known object measured to within tolerance after rectification | The only end-to-end check |

RMS reprojection error appears nowhere. It should still be logged, because an unexpectedly large value signals gross failure, but it should not decide the outcome.

> **Open.** The numeric thresholds for C2, C3 and the tolerance and object for C4 follow from a mission accuracy budget for tether reconstruction **which is not stated anywhere in the project documentation**. Until it is fixed, the tool can report the metrics but cannot declare success automatically. If the paper quotes an accuracy figure, this is the gap it will be measured against.

---

## 7. Illumination

The experiment runs in a dark room, which means the lighting is an instrument and has to be specified like one.

### 7.1 The photometric chain

| Equation | Expression | Symbols |
|---|---|---|
| Luminous flux | $\Phi_v = K_m \int \Phi_{e,\lambda}(\lambda) V(\lambda)\, d\lambda$ | `K_m = 683 lm/W`, `V(λ)` CIE photopic efficiency |
| Luminous efficacy | $K = \Phi_v / \Phi_e$ | a property of the source's spectrum |
| Luminous intensity | $I_v = d\Phi_v / d\Omega$ | candela |
| Illuminance | $E_v = d\Phi_v / dA$ | lux. **The quantity we specify and measure** |
| Inverse-square cosine | $E_v = I_v \cos\theta / d^2$ | the most consequential relation here |
| Luminance | $L_v = d^2\Phi_v / (dA\cos\theta\, d\Omega)$ | cd/m², **the unit sensor datasheets use** |
| Lambertian reflector | $L_v = \rho E_v / \pi$ | the bridge between lux and the datasheet |
| Photometric exposure | $H_v = E_v t$ | lx·s |
| Stops | $\Delta\mathrm{EV} = \log_2(E_1/E_2)$ | |

The `π`, not `2π`, in the Lambertian relation follows from integrating cosine-weighted radiance over the hemisphere.

### 7.2 The reference Sun

**DERIVED** from primary data: ASTM E490-00a AM0 spectral irradiance integrated against CIE 018:2019 V(λ) by trapezoidal rule, with IAU 2015 Resolution B3 nominal constants.

| Quantity | Value |
|---|---|
| E490 integrated irradiance | 1366.1 W/m² |
| E490 integrated illuminance | 133 320 lx |
| **Luminous efficacy of AM0 light** | **97.59 lm/W** |
| **Illuminance at the IAU nominal constant 1361 W/m²** | **132 800 lx** |
| **Solar angular diameter** | **0.533°** |
| **Penumbra per metre** | **9.3 mm/m** |
| Solar effective temperature | 5772 K |

The 0.37 % discrepancy between E490's integral and the IAU nominal constant arises because the two were established at different times against different radiometric scales. `K` is a property of the spectral **shape** and is insensitive to that normalisation, so the nominal constant is used.

Angular diameter:

$$\alpha_\odot = 2\arctan\left(\frac{695\,700}{149\,597\,870.7}\right) = 0.533°$$

Fraction of AM0 irradiance by band, which matters because both our cameras carry IR-cut filters:

| Band | Share | Relevance |
|---|---|---|
| 400 to 700 nm | 38.6 % | Visible. Both cameras' IR filter reduces sensitivity outside it |
| 400 to 1100 nm | 66.4 % | Restricted range of the IEC 60904-9 spectral match classification |
| 300 to 1200 nm | 77.2 % | Extended range introduced in the 2020 edition, required for class A+ |

### 7.3 Penumbra as a ruler test

$$w = L \tan\alpha$$

The two rays grazing an occluding edge come from opposite edges of the source and diverge by the source's angular size. The practical value of this is that **it converts an angular specification, which needs optical instruments to verify, into a length measurable with a ruler.**

| Angular size | Reference | `w/L` |
|---|---|---|
| 0.53° | the real Sun at 1 au | 9.3 mm/m |
| 1.00° | n/a | 17.5 mm/m |
| 1.90° | ESA Large Space Simulator collimation angle | 33.2 mm/m |
| **2.00°** | **limit adopted for LINKU** | **34.9 mm/m** |
| 5.00° | a typical uncollimated spotlight | 87.5 mm/m |

### 7.4 Uniformity

IEC 60904-9 spatial non-uniformity:

$$NU = \frac{E_{max} - E_{min}}{E_{max} + E_{min}} \times 100\%$$

In photographic terms:

| IEC class | `NU` | `E_max/E_min` | Spread in stops |
|---|---|---|---|
| A+ | ≤ 1 % | 1.020 | 0.029 EV |
| A | ≤ 2 % | 1.041 | 0.058 EV |
| **B** | **≤ 5 %** | **1.105** | **0.144 EV** |
| C | ≤ 10 % | 1.222 | 0.290 EV |

For an uncollimated source, the depth of the working volume alone sets the achievable uniformity through inverse-square falloff:

$$NU = \frac{1-r}{1+r}, \quad r = \left(\frac{D}{D+\Delta z}\right)^{2}, \qquad D_{\min} = \Delta z \cdot \frac{\sqrt{r}}{1-\sqrt{r}}$$

| Target | Class | Required throw |
|---|---|---|
| NU ≤ 2 % | A | 49.5 × Δz |
| NU ≤ 5 % | B | 19.5 × Δz |
| NU ≤ 10 % | C | 9.5 × Δz |

**Holding class B uniformity with an uncollimated lamp requires a throw of about twenty times the depth of the object.** For a structure 0.5 m deep that means roughly 10 m of clear space; for 1 m depth, roughly 20 m. This is the independent second reason for requiring a collimated beam: without it, R4 is unreachable at any throw a dark room can provide.

### 7.5 The light budget, anchored to the sensor datasheet

The chain from exposure limit to lamp specification.

**Sampling geometry**, at the 3.5 m working distance with a 1 mm tether:

$$\mathrm{IFOV} = \frac{p}{f}, \qquad \mathrm{GSD} = \frac{pD}{f}, \qquad n_{px} = \frac{d}{\mathrm{GSD}}$$

| Configuration | W [mm] | IFOV [°] | FOV_H | GSD [mm] | n_px |
|---|---|---|---|---|---|
| **IMX477 + 8 mm f/1.6 (fitted)** | 6.287 | 0.0111 | 42.9° | 0.678 | **1.47** |
| IMX477 + 6 mm f/1.2 | 6.287 | 0.0148 | 55.3° | 0.904 | 1.11 |
| IMX296 + 16 mm f/1.4 | 5.023 | 0.0124 | 17.8° | 0.755 | 1.33 |
| IMX296 + 8 mm f/1.6 | 5.023 | 0.0247 | 34.9° | 1.509 | 0.66 |
| IMX296 + 6 mm f/1.2 | 5.023 | 0.0329 | 45.4° | 2.013 | 0.50 |
| Hawk-eye + 5.1 mm f/1.8 | 7.322 | 0.0090 | 71.3° | 0.549 | 1.82 |

The derived 55.3° and 45.4° reproduce Raspberry Pi's published 55° and 45° for the 6 mm lens on those two cameras, and 42.9° agrees with Arducam's published 44° H. The FOV derivation is validated against three independent vendor figures.

**Exposure ceiling from motion blur:**

$$b = \frac{\omega t}{\mathrm{IFOV}}, \qquad t_{\max} = \frac{b_{\max}\,\mathrm{IFOV}}{\omega} = \frac{b_{\max}\,p}{f\,\omega}$$

with `b_max = 1 px`. We use a stricter budget than the rolling-shutter deliverable's 3 px deliberately, so that blur does not consume the entire error allowance by itself.

**Saturation from the Sony IMX477 datasheet**, standard imaging condition I: `L_ref = 706 cd/m²` at 3200 K, `N_ref = f/2.8`, `t_ref = 1/120 s`, `S = 250 LSB`, `V_sat = 1023 LSB`, `V_OB = 64 LSB`.

$$(Lt)_{sat}(N_{\mathrm{ref}}) = \frac{V_{sat}-V_{OB}}{S}\,L_{\mathrm{ref}}\,t_{\mathrm{ref}} = \frac{1023-64}{250}\times 706 \times \frac{1}{120} = 22.57 \ \mathrm{cd\,s/m^2}$$

Scaling by aperture and converting to a white card of reflectance ρ:

$$(Lt)_{sat}(N) = (Lt)_{sat}(N_{\mathrm{ref}})\left(\frac{N}{N_{\mathrm{ref}}}\right)^{2}, \qquad H_{sat} = \frac{\pi (Lt)_{sat}(N)}{\rho}, \qquad E_{\min} = \frac{H_{sat}}{t_{\max}}$$

| Configuration | H_sat [lx·s] | t_max @1°/s | t_max @2.76°/s | E_min @1°/s | E_min @2.76°/s | Basis |
|---|---|---|---|---|---|---|
| **IMX477 + 8 mm f/1.6** | 25.72 | 11.1 ms | 4.0 ms | **2317 lx** | **6396 lx** | datasheet |
| IMX477 + 6 mm f/1.2 | 14.47 | 14.8 ms | 5.4 ms | 978 lx | 2698 lx | datasheet |
| IMX296 + 16 mm f/1.4 | 19.69 | 12.4 ms | 4.5 ms | 1594 lx | 4400 lx | **rescaled, assumption** |
| IMX296 + 8 mm f/1.6 | 25.72 | 24.7 ms | 9.0 ms | 1041 lx | 2873 lx | **rescaled, assumption** |
| IMX296 + 6 mm f/1.2 | 14.47 | 32.9 ms | 11.9 ms | 439 lx | 1212 lx | **rescaled, assumption** |
| Hawk-eye + 5.1 mm f/1.8 | 32.55 | 9.0 ms | 3.3 ms | **3622 lx** | **9998 lx** | **rescaled, assumption** |

Only the two IMX477 rows are datasheet-anchored. The IMX296 flyer gives sensitivity and saturation in millivolts **but does not state the test luminance**, so the equation cannot be evaluated for it; those rows are rescaled from the IMX477 by aperture alone, justified by the argument that full-well capacity and collected flux both scale with pixel area so their ratio is roughly area independent. That remains an assumption about devices of different generations, not backed by any datasheet.

**Four assumptions, all pushing the real requirement upward:** the datasheet condition is 3200 K while the spec calls for 5600 to 6000 K; the gain scale is treated as consistent between `S` and `V_sat − V_OB`; lens transmittance is taken as `T = 1` on-axis with no `cos⁴` vignetting; and the result is for a white card filling many pixels while the tether is thinner than one pixel on two configurations and may be much darker than ρ = 0.9. **E_min is a floor, not a target.**

Even the highest requirement, 10 000 lx, is **3.7 stops below the orbital Sun**.

### 7.6 Flicker

A lamp on an AC supply has luminous output rising and falling **twice per electrical cycle**:

$$T_{\mathrm{flicker}} = \frac{1}{2f}$$

That is **10 ms at 50 Hz**, 8.3 ms at 60 Hz. Those periods are the same order of magnitude as every exposure ceiling in the table above, which is precisely the regime where flicker becomes visible.

On a rolling-shutter sensor, row `k` integrates the lamp waveform over a window displaced by `k` row periods, so a **temporal** fluctuation becomes a **spatial** pattern across the frame.

Banding contrast, modelled with `L(t) = sin²(2πft)`, 50 Hz supply, 25 ms full-frame readout over 3040 rows (row period 8.22 µs), evaluating the IEC non-uniformity definition on the row signals:

| Exposure | Source | Banding contrast |
|---|---|---|
| 3.3 ms | Hawk-eye ceiling at 2.76°/s | **83.0 %** |
| **4.0 ms** | **fitted IMX477 ceiling at 2.76°/s** | **75.7 %** |
| 4.5 ms | IMX296 + 16 mm at 2.76°/s | 68.5 % |
| 5.4 ms | IMX477 + 6 mm at 2.76°/s | 58.5 % |
| 9.0 ms | Hawk-eye at 1°/s | 10.9 % |
| *10.0 ms* | *exactly one flicker period* | *0.0 %* |
| **11.1 ms** | **fitted IMX477 ceiling at 1°/s** | **9.7 %** |
| 14.8 ms | IMX477 + 6 mm at 1°/s | 21.5 % |
| *20.0 ms* | *exactly two flicker periods* | *0.0 %* |
| 32.9 ms | IMX296 + 6 mm at 1°/s | 7.6 % |

The zero-contrast rows validate the model: when the exposure equals an exact multiple of the flicker period every row integrates the same light and banding vanishes, the condition Sheinin et al. describe as emulating DC illumination. At 4.0 ms, 75.7 % means the darkest band carries about one seventh the signal of the brightest.

**We cannot exploit that coincidence**, because the exposure time is not free: it is fixed by the rotation rate under test. **The fixture itself must not flicker.**

Concretely, for HMI: an electronic ballast in a flicker-free mode, preferably **high speed (about 1000 Hz, period 1.00 ms)**. ARRI's own manual for the EB 12/18 kW states that its 50/60 Hz low-noise mode is **"NOT flicker free any more"**, and its 75 Hz flicker-free mode has a 13.33 ms period that exceeds most of our ceilings. For LED fixtures no equivalent statement was found in any reviewed source, so dimming method and PWM frequency must be requested from the manufacturer and verified on site.

**Global shutter is not immune.** The IMX296 exposes every pixel at once and shows no banding, but its frame brightness still depends on where the exposure window falls in the flicker cycle: two windows of equal duration can collect 100 % and 14 % of maximum. That becomes **frame-to-frame brightness variation instead of within-frame banding**, which is equally destructive for a stereo pair that must be radiometrically consistent.

### 7.7 The specification

| # | Requirement | Value | Basis |
|---|---|---|---|
| R1 | One light direction, no fill | 1 direction, no bounce, no ambient | **Physics** |
| R2 | Daylight colour | 5600 to 6000 K, CRI ≥ 90, TLCI reported | Project |
| R3 | Parallel beam | penumbra ≤ 35 mm at 1 m (α ≤ 2°) | Project; physics reference 9.3 mm |
| R4 | Uniformity | NU ≤ 5 %, i.e. ≤ 0.14 EV | Project, IEC class B |
| R5 | Illuminance at the tether | ≥ 3600 lx at 1°/s; ≥ 10 000 lx at 2.76°/s | Datasheet derivation |
| R6 | Stability and flicker | ≤ 2 % over the session, flicker-free fixture | Project, IEC class B STI |
| R7 | Black environment | black velvet or molton, lamp out of frame | Project |
| R8 | Recorded data | the record sheet | Feeds the Blender replica |

"Physics" marks a value fixed by the Sun itself; "project" marks a threshold adopted for LINKU and open to revision. Precedents: the DLR EPOS sun simulator is a 6000 K HMI with CRI 90; the ESA Large Space Simulator achieves 1.9° collimation and ±4 % in-plane uniformity; black velvet scored best among background materials tested with the same Raspberry Pi HQ camera at the SnT Zero-G Lab.

**Multi-lamp rule.** R1 requires one light **direction**, not one fixture. Several identical fixtures aimed parallel at equal distance and incidence are acceptable. Three configurations are excluded: converging beams (each direction produces its own highlight line on a specular cylindrical tether, and two highlight lines on a target one pixel wide can present as a doubled thread, a failure mode the stereo matcher is not designed to handle); mixed fixtures or colour temperatures along the row; and a fixture at one end shining along the tether, where incidence becomes grazing and inverse-square applies along the tether's own length.

**Protocol ordering rationale**, worth stating because it is not obvious: the geometric requirements are settled before the photometric ones, because **moving a fixture to fix uniformity changes the illuminance, while dimming it does not change the uniformity.**

**Status: PLANNED.** The specification is complete; no measurement has been taken. Two external dependencies: the LINKU structure is being built by a teammate, and the dark-room date depends on the teaching staff.

---

## 8. Rotation and rolling shutter

### 8.1 The question and why it is sharper here than in ordinary photography

A rolling-shutter sensor exposes rows sequentially, so if the camera rotates during readout each row records the scene from a slightly different orientation, producing a **geometric shear**, not a uniform blur. This is distinct from motion blur, which arises during a **single row's** exposure and occurs with any shutter type. A rolling-shutter sensor can exhibit both at once.

The amplifier specific to this mission, and the reason it matters: **the tether occupies only one to three pixels of width.** A shear of two or three pixels, which would be a barely noticeable artefact in an ordinary photograph, **is comparable in magnitude to the entire object being measured.**

This was identified as a gap: the original camera configuration analysis did not account for spacecraft rotation at all.

### 8.2 The first-pass estimate

With the 8 mm lens at the software's configured 1920 × 1440:

$$\mathrm{IFOV} \approx 0.023°\ \mathrm{per\ pixel}$$

$$\omega_{\max} = \frac{N_{\text{shear}}\cdot \mathrm{IFOV}}{T_{\text{readout}}}, \qquad N_{\text{shear}} = 3\ \mathrm{px}$$

The 3 px threshold is justified, not assumed silently: the tether is itself 1 to 3 px wide, so any larger shear would be comparable to the target.

| Readout basis | `T_readout` | `ω_max` |
|---|---|---|
| Software setting, 15 fps | ≈ 67 ms | **≈ 1.05 °/s** |
| IMX477 datasheet, 12-bit Normal, 40 fps | ≈ 25 ms | **≈ 2.76 °/s** |
| IMX477 datasheet, 10-bit Normal, 60 fps | ≈ 16.7 ms | n/a |

**The finding worth reporting:** the widely used guidance of keeping rotation at or below about 1 deg/s **reflects our software's current conservative 15 fps configuration, not a hard sensor limitation.** Reconfiguring the capture pipeline to a faster readout mode buys 2 to 4× margin.

> **Central quantitative limitation.** These are **upper bounds**. The frame period includes an unknown amount of blanking in addition to the actual row-scan time. The exact row-scan-only readout time requires the IMX477 Software Reference Manual, which is not publicly available, or a bench measurement. The true readout is expected to be **shorter**, which makes both figures **conservative**.

> **A numeric inconsistency between our own deliverables, which you should not let through.** The illumination deliverable computes IFOV ≈ 0.0111 °/px for the 8 mm lens; the rolling-shutter deliverable uses ≈ 0.023 °/px for the same lens. The factor of 2.1 is exactly 4056/1920: one reasons on the native sensor row, the other on the scaled 1920-wide output. **Both are internally correct but as written they appear to contradict each other.** If both documents feed the paper, this has to be reconciled explicitly.

### 8.3 Power, which falls out of the same datasheet

**DERIVED** from the IMX477 datasheet at full resolution, 30 fps:

| Supply | Voltage | Typical | Maximum |
|---|---|---|---|
| Analog | 2.8 V | 25.1 mA | 34.2 mA |
| Digital | 1.05 V | 185.0 mA | 267.5 mA |
| Interface | 1.8 V | 2.4 mA | 2.8 mA |
| **Total per camera** | | **≈ 269 mW** | **≈ 382 mW** |

Stereo pair, sensors alone: **≈ 540 to 760 mW**.

Two caveats. The figures are specified at 30 fps, **not** at the 40 to 60 fps modes discussed above, so the power draw of the faster readout is expected to be **higher**. And **the CM5's own processing-side power draw is not characterised at all**: no bench measurement or datasheet figure exists in any project document.

> **Legal caveat you need to know before submission.** The datasheet pages covering Section 8-2 onward, including the current-consumption table quoted here, are **watermarked CONFIDENTIAL by Sony Semiconductor Solutions**, even though the file was obtained from a public Arducam documentation URL. The decision to cite these figures internally was made explicitly and knowingly. **Verify redistribution terms before including these figures in any external submission.**

### 8.4 Correction approach and plan

**Adopted:** geometric correction using a known angular rate, after Karpenko et al., who demonstrated that rolling-shutter shear and camera motion can be jointly modelled and corrected from synchronised gyroscope measurements **without machine learning or training data**: the row-dependent warp is computed directly from the angular velocity at each row's capture time, then geometrically inverted. Chosen because ADCS will supply exactly the rate telemetry the method requires, and because it needs no dataset that does not exist.

**Considered, not adopted:** learning-based IMU-assisted correction (Mo et al.), which requires matched rolling-shutter / global-shutter image pairs we do not have.

**Two-phase plan, both PLANNED:**

- **Phase 1, synthetic**, no hardware. Take a static laboratory photograph as ground truth, apply synthetic shear computed from a chosen angular rate, apply the correction using that same known rate, compare back. Ground truth, applied distortion and angular velocity are all exactly known by construction, so any residual is attributable to the algorithm.
- **Phase 2, physical.** A rotation rig at controlled, logged angular velocity, standing in for ADCS telemetry. Adds what Phase 1 cannot capture: illumination changes during rotation, rig vibration, and timing mismatch between commanded velocity and the actual exposure window.

Sweep: {0, 0.25, 0.5, 1.0, 2.0, 5.0} °/s, chosen to bracket both estimates. Metrics reuse the existing pipeline (tracker coverage, endpoint position error, path length error, 3D curvature and straightness error), reported **for both corrected and uncorrected images at each rate**, so the correction's benefit is explicit rather than only the corrected result in isolation.

**No angular rate has been experimentally tested.** All values are derived estimates or planned sweep points.

A methodological commitment we made in both experimental deliverables and that I would like to keep in the paper: **the acceptance threshold is to be fixed before running the experiment, not after seeing the results, to avoid post-hoc rationalisation.**

---

## 9. Simulation

### 9.1 The epistemic problem

The condition of real interest, the tether photographed in orbit, **cannot be photographed for real**. There is no ground-truth image for that condition, so realism cannot be validated directly where it matters most.

Our answer is a two-tier strategy. First, build a Blender scene replicating the laboratory dark enclosure, render it, and compare the render against a real photograph of the same physical configuration, **using the project's own reconstruction pipeline as the comparison instrument** rather than visual inspection. Only after laboratory-scale agreement is demonstrated, reconfigure for orbital illumination and treat the output as an evidence-supported extrapolation rather than an unverified assumption.

The justification for comparing at the pipeline's output rather than at pixel level or by human judgement: **the pipeline, not a human viewer, is the actual downstream consumer of these images.** This is also why we reviewed and did not adopt Kluge and Staadt's two-alternative forced-choice photorealism user study as the primary method.

Precedent: SISPO established its own credibility by comparing renders directly against real Hayabusa/AMICA imagery of asteroid Itokawa. A common pattern across SISPO, CORTO and BlenderProc is Cycles physically based rendering plus a validation step against something real. **An important negative finding: no reviewed tool publishes an exact numeric Sun-strength or camera-exposure value that could be copied directly.** Each defines its own scene-specific calibration, which is consistent with deriving values from first principles as we do.

### 9.2 Scene configuration

- Replica of the LINKU deployment structure, not just a dark box.
- Two stereo cameras at a fixed **100 mm** baseline, 3.5 m from the enclosure back wall.
- Equirectangular background image rather than a flat colour.
- `SunLight.energy` is documented by Blender as W/m², unbounded, so the irradiance value is **directly settable with no unit conversion**. Orbital render: 1361 W/m², blackbody 5772 K.
- `SunLight.angle` default is 0.00918043 rad ≈ 0.526°, which matches the real solar angular diameter to three significant figures.
- View Transform kept at **AgX** (Blender default, ≈16.5 stops), which desaturates overexposed colours rather than clipping them, the way a real sensor rolls off. Output = rendered value × 2^exposure.

A caution worth repeating: ground-level direct sunlight is ≈1050 W/m², the figure in most Blender outdoor tutorials, and **must not** be used for an orbital render.

### 9.3 The one executed experiment

**MEASURED.** This is the only quantitative result in the simulation work and it is **synthetic-to-synthetic**, not real-versus-render.

| Configuration | Setup | Reconstructed depth | Spread |
|---|---|---|---|
| A | Tether at ≈ uniform 40 cm from the cameras | 0.39 to 0.40 m | n/a |
| B | One endpoint displaced ≈ 10 cm farther | 0.40 to 0.51 m | **11 cm** |

**Reconstructed depth spread of 11 cm against a known applied displacement of 10 cm, agreeing to within 1 cm.**

What it validates: the reconstruction pipeline and the Blender-derived calibration together, on ground truth that is exact by construction. What it does **not** validate: whether a Blender render resembles a photograph. It is a single preliminary case, not a systematic accuracy characterisation across poses and distances.

### 9.4 A debugging result worth one line in the paper

**MEASURED.** For a long time the tether curve rendered dark regardless of light power, tested from 50 W to 1000 W. Root cause: the curve object had `scale.z = 0`, an intentional flattening to fit it inside the box. **A scale with a zero component is a singular transformation and breaks normal computation**, so the material never responded to light at any wattage. Fix: apply (bake) the scale into the curve points so `object.scale` returns to (1,1,1) with the same final shape. Verified on both cameras, pixel values up to 200/255 on the thread instead of pure black.

Note the LaTeX chapters still record this bug as open; the dated work plan records it as resolved. The work plan is the newer snapshot.

### 9.5 Status

| Item | Status |
|---|---|
| Literature review | Complete |
| Methodology definition | Complete |
| Scene construction | Built, tether rendering bug resolved |
| Synthetic self-consistency check | **Done, 11 cm vs 10 cm** |
| Laboratory light characterisation | **Pending** (this is what Section 7 specifies) |
| Matched real-versus-render comparison | **Pending. No agreement or disagreement is reported** |
| Orbital-condition render | Pending, conditional on the above |

Reference real pair selected: `data/captures/stereo_20260213_140535`, 1920 × 1440, 100 mm baseline, 10.4 ms sync. **It was captured before the current calibration was invalidated, so it is usable as a 2D reference for mask, endpoint and path comparison but not for 3D comparison.**

A minimum of **3 to 5 matched pairs** covering different tether poses is recommended before drawing conclusions.

---

## 10. Results obtained, honestly summarised

Everything this payload has actually produced, with nothing upgraded.

| # | Result | Status |
|---|---|---|
| 1 | Conventional SfM fails completely on a segmented tether ("Zero Resolution"), and the cause is insufficient information in the target, not background interference | **MEASURED** |
| 2 | Dense stereo produces phantom geometry from empty background regions and needs manual filtering, so it is not autonomous | **MEASURED** |
| 3 | A geometry-driven pipeline reconstructs the tether in both a planar and an out-of-plane looped configuration, producing stable and physically plausible reconstructions | **MEASURED, qualitative** |
| 4 | In Blender, with exact ground truth, reconstructed depth spread 11 cm against an applied 10 cm | **MEASURED** |
| 5 | 23 calibration attempts failed because 91 % of archived poses are geometrically degenerate: median tilt 4.4°, zero frames above 45° | **MEASURED** |
| 6 | RMS reprojection error of 1.50 px conceals `fx` uncertainty of 0.85 % and a `k3` whose sigma exceeds its own value | **MEASURED** |
| 7 | A guided capture loop that keeps 3, 12 and 9 views from 25, 25 and 20 offered, and correctly refuses completion on all three archived sessions | **MEASURED** |
| 8 | Orbital solar illuminance 132 800 lx, angular diameter 0.533°, penumbra 9.3 mm/m, from primary data | **DERIVED** |
| 9 | Minimum dark-room illuminance of 2317 lx for the fitted configuration, 3622 lx if the Hawk-eye is used | **DERIVED**, with four stated assumptions all pushing upward |
| 10 | Flicker banding contrast 75.7 % at the fitted configuration's 4.0 ms ceiling on a 50 Hz supply | **DERIVED**, model validated by zero-contrast at exact flicker multiples |
| 11 | Rotation tolerance 1.05 °/s at the current software setting, 2.76 °/s at the sensor's datasheet capability, both conservative upper bounds | **DERIVED** |
| 12 | Sensor power 269 to 382 mW per camera at 30 fps, 540 to 760 mW for the pair | **DERIVED** |
| 13 | A thread 1 mm wide is sub-pixel at 100 m for all nine configurations examined, by about two orders of magnitude | **DERIVED** |
| 14 | Megapixel count is nearly irrelevant to thin-target resolution; pixel pitch times focal length governs | **DERIVED**, cross-checked two ways |
| 15 | Random Forest pixel segmentation, F1 0.97 | **MEASURED but on the training set, and not in the production path** |

**What has not been measured at all:** any real-versus-render comparison; any experimental angular rate; any dark-room illumination value; CM5 power; JPEG file size and therefore images per pass; any end-to-end accuracy figure against a known physical object.

That last one deserves emphasis. **We do not yet have a metric accuracy figure for the payload.** The 11 cm versus 10 cm result is the closest thing, and it is synthetic. If the paper needs an accuracy claim, this is the experiment that has to run first.

---

## 11. Defects and inconsistencies

Collected so nothing here reaches the paper by accident. Every item was verified against the source.

### 11.1 Contradictions between our own documents

| # | Topic | Conflict |
|---|---|---|
| 1 | **Flight sensor** | Sub-deliverable: IMX477 baseline. APSCO: IMX708 reference. All published optical numbers are IMX477-specific and do not transfer |
| 2 | **Camera count** | Sub-deliverable validates a stereo pair. APSCO requires three cameras, one on SAT-C with no stereo partner, where the pipeline cannot run |
| 3 | **Field of view** | Validated configuration 42.9° H. APSCO sunshade geometry built around "approximately 80°" |
| 4 | **IFOV** | 0.0111 °/px (illumination deliverable) versus 0.023 °/px (rolling-shutter deliverable) for the same lens. Factor 2.1 = 4056/1920, native versus scaled |
| 5 | **SAT-C camera location** | APSCO payload chapter says upper section; APSCO structural chapter says lower module |
| 6 | **Config 2 described as 12 MP** | Sub-deliverable text says "two representative 12 MP configurations"; the table lists 9152 × 6944 = 63.5 MP |
| 7 | **Config 2 module name** | Table pairs "Raspberry Pi Camera Module 3" with "Omnivision OV64A40". Module 3 carries IMX708; the OV64A40 is the Arducam Hawkeye. The numbers match the Hawkeye, so the module name is wrong |
| 8 | **Blender bug status** | LaTeX chapters record the dark-tether bug as open; the work plan records it resolved (`scale.z = 0`) |
| 9 | **Symbol reuse** | `μ` defined as the gravitational parameter, then reused as object distance two equations later |
| 10 | **Calibration conclusion text** | The confidence table says the degeneracy is "Measured", but the paragraph below it still says "a well-supported hypothesis, not a finding" and that the document "should not be read as having diagnosed the problem". Left over from before the measurement was run |

### 11.2 Software defects, verified

| # | Defect | Impact |
|---|---|---|
| 1 | **AI mask never reaches the pipeline.** `update_detection()` recomputes the classical mask and overwrites it on both exit paths | The trained model is a preview only. Three documents describe it as integrated |
| 2 | **PLY colours wrap modulo 256.** The exporter assumes [0,1] and multiplies by 255; the production cloud is already uint8 0 to 255. Reproduced: (120,200,30) → (136,56,226) | Every colour in every exported geometric-path cloud is wrong. Geometry is unaffected |
| 3 | **Dense-branch colour indexing.** `np.where(mask2d)[0]` returns row indices, then decoded as linear indices | Colours and confidences sampled from essentially row 0. Production unaffected |
| 4 | **F1 computed on the training set.** `predict(X_tr)` after `fit(X_tr)`, no split anywhere | The 0.97 is optimistic by construction and appears in three documents |
| 5 | **Five different depth gates** across the pipeline, and metrics use the widest | Reported length, straightness and curvature describe a superset of the exported cloud |
| 6 | **Segmentation is not scale invariant.** Adaptive thresholds computed on a 1280 px downscale | A full-resolution capture does not segment like its preview |
| 7 | **Geodesic distance is weighted BFS, not Dijkstra** | Returns the fewest-hops path cost, not minimum weight. Harmless for argmax, but should not be called a geodesic shortest path |
| 8 | **`_unmark_visited` radius exceeds `_mark_visited`** | Backtracking frees a larger region than was marked. Undocumented |
| 9 | **`track_wire` always returns `success: True`** | Caller's success check is vacuous |
| 10 | **PCD writes packed RGB as a decimal integer under a `TYPE F` header** | Many readers mis-parse it |
| 11 | **`delete_sample` orphans `_right` files** | Reissued ids can produce mismatched pairs |
| 12 | **MD5 dedup described as "perceptual"** | It is exact; a one-DN change defeats it |
| 13 | **Comment/code mismatch** in `disparity_to_depth`: comment says 3 m, code sets 5.0 m | |
| 14 | **`mod_mm: 0.2` in the optical comparator** means 0.2 m but is commented "0.2 mm", disabling the near-distance clamp. Traced to a typo on Arducam's own B0240 page | Affects the tool's output at short distances |
| 15 | **Hawk-eye labelled OV64A40 with 1.4 µm** in the comparator; the documented pitch is 0.80 µm | Label only; computations derive pitch from width/resolution |
| 16 | **Software sync validated only below 5 cm/s**, against flight separation of 0.5 to 1.5 m/s | Unaddressed gap |

### 11.3 Dead code, not to be described as active

`EndpointDetector._prune_short_branches` (never called; clustering replaced it). The `end_dir` argument of `_analyze_flow_options` (never read). `arc_sample` in the matcher (computed, never used). `_get_macro_trend` results in trimming case 2b (logged, not used). `WireMatcher.cross_check` (stored, never implemented). The gradient NCC mode (force-disabled with a comment explaining why). `PointCloudProcessor` entirely: voxel downsampling, normals and outlier filters are never invoked. `edge_detection_config.txt` and its writer (no caller, no reader; the real persistence is JSON presets).

### 11.4 Citations requiring care before external submission

| Source | Issue |
|---|---|
| Sony IMX477 datasheet | Sections 8-2 onward **watermarked CONFIDENTIAL**, including the power table. Verify redistribution terms |
| `starsensor2023rollingshutter` | IEEE paywalled, **author list unverified** (3 of a reported 7, and even those uncertain). Do not treat as reliable |
| CORTO (Pugliatti et al.) | Full text not read; MDPI bot-blocked. Details from search snippets. Verify before deeper use |
| INVERITAS, GRALS | Secondary source only; both originals refused automated download |
| IEC 60904-9:2020 | Only the free official preview (clauses 1 to 5.2, including all three cited tables) was read. Measurement procedures are behind the paywall |
| `singla2026lunarsim` | Preprint, not peer reviewed, cited only to point to CORTO |

---

## 12. What transfers to the star tracker and the microscopy payloads

Written for you two. I am not making claims about your payloads; these are shared pieces of machinery and the questions I would want answered if I were writing your sections.

### 12.1 All three payloads are camera payloads with the same calibration problem

Anything that measures geometry from images depends on intrinsics, and the degeneracy of Section 6.4 is not tether-specific. It is a property of planar-target calibration. If either of you calibrates with the board held roughly parallel to the sensor, **your focal length is unrecoverable too**, and your reprojection error will not tell you.

The machinery in `camera/calibration_guidance.py` and `camera/guided_session.py` has **no camera and no GUI dependency by design**, so you can run it on your own archived sessions today. `tools/analyze_calibration_sessions.py` will give you the tilt distribution and the per-parameter uncertainty of any ChArUco session.

Specific relevance per payload, as questions rather than claims:

- **Star tracker.** Attitude accuracy is directly limited by intrinsic accuracy, and a star tracker's targets are at effective infinity, which makes the `f ↔ t_z` ambiguity worse, not better, because you cannot vary target distance at all. How is the camera calibrated, and against what? If it is calibrated on a planar target at finite distance and then used at infinity, the validity of that transfer is worth a paragraph.
- **Microscopy.** At high magnification the thin-lens assumptions behind the standard pinhole model degrade, and depth of field becomes extremely shallow. Section 6.3's focus-drift argument is much sharper for you: if the focus mechanism moves at all between calibration and use, the scale is wrong. Is the model used a pinhole-plus-radial, and has it been checked against a bias ratio?

A shared methodological point worth one joint paragraph: **all three payloads should report parameter uncertainty rather than reprojection error.** Section 6.6 gives a worked demonstration on real data that the latter hides the former. That is a claim the paper can make once and apply three times.

### 12.2 Sensor characterisation is shared

The light-budget chain in Section 7.5 is sensor-generic. Given a datasheet that states sensitivity, saturation and the luminance of its test condition, the chain

$$(Lt)_{sat} \to H_{sat} \to E_{\min}$$

gives you the minimum illuminance for any target reflectance and exposure ceiling. The IMX477 is the only one of the three sensors we examined whose datasheet contains everything needed. If your sensors are better documented, those rows can replace our assumption-based ones.

The pixel-pitch-times-focal-length result of Section 2.4 applies to **any** thin or small target, which plausibly includes a star (a point source, so the relevant question becomes the PSF rather than geometric sampling) and a microscopy feature. The general statement, that total pixel count is the wrong figure of merit for small-target detection, is one the paper can make once.

### 12.3 Shutter behaviour is shared and is often overlooked

Section 8 is written for a rotating spacecraft imaging a thin target, but the mechanism is general:

- **Rolling shutter under platform rotation** produces geometric shear, which is a systematic error, not noise. If your payload images during any attitude motion, the shear is there whether or not anyone has looked for it.
- **A star tracker is the textbook case.** We found literature on rolling-shutter correction specifically for star sensors, where distortion from vehicle rotation degrades attitude determination, though the requirements there (arc-second accuracy) are far stricter than ours. We could not obtain that paper and our citation is unverified, so if either of you has IEEE access it is worth retrieving.
- **Flicker affects anyone imaging under artificial light.** Section 7.6 is about a dark room, but the 10 ms period at 50 Hz applies to any laboratory. If microscopy illumination is LED with PWM dimming, the banding mechanism is identical and the contrast table transfers directly. The conclusion also transfers: you cannot tune the exposure around it, because the exposure is set by other constraints; the fixture must not flicker.

### 12.4 The shared mission constraints

These bind all three payloads jointly and no single payload can resolve them:

| Constraint | Value | Note |
|---|---|---|
| Downlink | S-band 200 kbps, ≈15 MB per 10-minute pass | "The data budget is expected to be dominated by the camera system" |
| Power, SAT-BC configuration | 2.9 to 5.9 W peak electrical | The most constrained configuration |
| Power, SAT-C after separation | 2.3 to 2.6 W | |
| ADCS rate before separation commands | ‖ω‖ < 1 deg/s | |
| Time correlation | SYS-MEAS-007 requires camera, GNSS, tension and housekeeping data to be time correlated | Applies to all payload data |

**Attitude control, power and imaging cadence are jointly constrained by the same imaging windows.** If all three payloads want simultaneous operation, somebody has to write the combined duty cycle, and no one has. That might be a useful joint contribution in its own right.

### 12.5 A suggested framing for the joint paper

The three payloads share more than a spacecraft. All three extract geometric measurements from images under conditions that defeat standard computer vision, and all three are built on low-cost COTS sensors on a constrained embedded platform.

If there is a unifying argument, I would propose: **when the target violates the assumptions of feature-based vision (too thin, too small, too textureless, too bright, too dark), the solution is not a better general-purpose algorithm but a target-specific geometric model, and the main engineering risk shifts from the algorithm to the calibration and the illumination.** Our Section 3.1 result is direct evidence for the first half and Sections 6 and 7 for the second. I suspect your payloads have analogous evidence, and if so the paper has a thesis rather than three parallel reports.

I am not attached to that framing. It is a proposal.

---

## 13. Bibliography

Organised by topic. Every entry has an archived copy in the relevant deliverable's `Sources/` folder unless noted.

### 13.1 Calibration

1. **Zhang, Z.** "A Flexible New Technique for Camera Calibration." *IEEE TPAMI* 22, 1330-1334, 2000. doi:10.1109/34.888718
2. **Richardson, A.; Strom, J.; Olson, E.** "AprilCal: Assisted and repeatable camera calibration." *IEEE/RSJ IROS*, 1814-1821, 2013.
3. **Rojtberg, P.; Kuijper, A.** "Efficient Pose Selection for Interactive Camera Calibration." *IEEE ISMAR*, 31-36, 2018. doi:10.1109/ISMAR.2018.00026. Code: github.com/paroj/pose_calib
4. **Rojtberg, P.** "User Guidance for Interactive Camera Calibration." *HCII*, 2019. arXiv:1907.04104
5. **Peng, S.; Sturm, P.** "Calibration Wizard: A Guidance System for Camera Calibration Based on Modelling Geometric and Corner Uncertainty." *IEEE/CVF ICCV*, 2019 (oral). arXiv:1811.03264
6. **Hagemann, A.; Knorr, M.; Janssen, H.; Stiller, C.** "Inferring bias and uncertainty in camera calibration." *IJCV*, 2021. doi:10.1007/s11263-021-01528-x
7. **Tan, D.; Liang, S.; Li, B.; et al.** "Optimal Pose Guidance for Stereo Calibration in 3D Deformation Measurement." *Experimental Mechanics*, 2025. doi:10.1007/s11340-025-01255-1
8. **Garrido-Jurado, S.; Muñoz-Salinas, R.; Madrid-Cuevas, F. J.; Marín-Jiménez, M. J.** "Automatic generation and detection of highly reliable fiducial markers under occlusion." *Pattern Recognition* 47, 2280-2292, 2014. doi:10.1016/j.patcog.2014.01.005
9. **Strobl, K. H.; Hirzinger, G.** "More Accurate Pinhole Camera Calibration with Imperfect Planar Target." *IEEE ICCV Workshops*, 2011. DLR.
10. **Ruppel, D.; Kutlu, H.; Neumann, K. A.; et al.** "Beyond Reprojection Error: Camera Calibration with 3D Targets." arXiv:2608.05066, 2026. *Preprint, not peer reviewed.*
11. **Huai, J.; Zhuang, Y.; Shao, Y.; et al.** "Geometric Wide-Angle Camera Calibration: A Review and Comparative Study." *IEEE Sensors Journal*, 2023. arXiv:2306.09014
12. **OpenCV.** "Camera Calibration and 3D Reconstruction." docs.opencv.org/4.x/d9/d0c/group__calib3d.html

### 13.2 Thin-structure reconstruction

13. **Kniaz, V. A.; Knyaz, V. V.; Remondino, F.; Zheltov, S. Yu.; Gruen, A.** "Wire Structure Image-Based 3D Reconstruction Aided by Deep Learning." *ISPRS Archives* XLIII-B2-2020, 435-441, 2020. doi:10.5194/isprs-archives-XLIII-B2-2020-435-2020
14. **Yu, N.; Li, H.; Xu, Q.; Sie, O.; Firdaous, E.** "3D Reconstruction and Defect Pattern Recognition of Bonding Wire Based on Stereo Vision." *CAAI Transactions on Intelligence Technology* 9(2), 348-364, 2024. doi:10.1049/cit2.12240
15. **Steger, C.** "Subpixel-Precise Extraction of Lines and Edges." *International Archives of Photogrammetry and Remote Sensing* XXXIII, Part B3, 141-156, 2000.

### 13.3 Photometry, solar simulation, illumination

16. **International Electrotechnical Commission.** *IEC 60904-9:2020, Photovoltaic devices, Part 9: Classification of solar simulator characteristics, Edition 3.0*, 2020. *Only the free official preview (clauses 1 to 5.2) was read.*
17. **Prša, A.; Harmanec, P.; Torres, G.; et al.** "Nominal values for selected solar and planetary quantities: IAU 2015 Resolution B3." *The Astronomical Journal* 152:41, 2016. arXiv:1605.09788
18. **ASTM International.** "ASTM E490-00a Standard Extraterrestrial (AM0) Solar Spectral Irradiance." Data file `e490_00a.dat`, mirrored in github.com/pytroll/pyspectral.
19. **CIE.** "CIE spectral luminous efficiency for photopic vision, V(λ)." CIE 018:2019 Table 1. doi:10.25039/CIE.DS.dktna2s3
20. **Meftah, M.; Damé, L.; Bolsée, D.; et al.** "SOLAR-ISS: A new reference spectrum based on SOLAR/SOLSPEC observations." *A&A* 611, A1, 2018. doi:10.1051/0004-6361/201731316
21. **Kopp, G.; Lean, J. L.** "A new, lower value of total solar irradiance: Evidence and climate significance." *GRL* 38(1), 2011. doi:10.1029/2010GL045777
22. **European Broadcasting Union.** "Method for the Assessment of the Colorimetric Properties of Luminaires: TLCI-2012 and TLMF-2013." EBU Tech 3355, 2017.
23. **ARRI.** "Operating Instructions, Electronic Ballast EB 12/18 kW High Speed, L2.76296KH."
24. **Sun, C.; Jin, Z.; Song, Y.; et al.** "LED-based solar simulator for terrestrial solar spectra and orientations." *Solar Energy* 233, 96-110, 2022. doi:10.1016/j.solener.2022.01.001
25. **Sheinin, M.; Schechner, Y. Y.; Kutulakos, K. N.** "Rolling Shutter Imaging on the Electric Grid." *IEEE ICCP*, 2018. doi:10.1109/ICCPHOT.2018.8368472

### 13.4 Space vision laboratories and simulation

26. **Benninghoff, H.; Rems, F.; Risse, E.-A.; Mietner, C.** "European Proximity Operations Simulator 2.0 (EPOS)." *Journal of Large-Scale Research Facilities* 3, A107, 2017. DLR.
27. **German Aerospace Center (DLR).** "Space Operations and Astronaut Training Portfolio: EPOS," 2025. Section 2.2, Sun Simulator.
28. **European Space Agency.** "Large Space Simulator." ESTEC Test Centre. technology.esa.int/page/large-space-simulator
29. **Park, T. H.; Bosse, J.; D'Amico, S.** "Robotic Testbed for Rendezvous and Optical Navigation (TRON)." *AAS/AIAA Astrodynamics Specialist Conference*, AAS 21-654, 2021. Stanford SLAB.
30. **Pauly, L.; Jamrozik, M. L.; Ortiz del Castillo, M.; et al.** "Lessons from a Space Lab: An Image Acquisition Perspective." arXiv:2208.08865v2, 2022. Published 2023, *International Journal of Aerospace Engineering*, doi:10.1155/2023/9944614
31. **Mahendrakar, T.; Ekblad, A.; Fischer, N.; et al.** "Performance Study of YOLOv5 and Faster R-CNN for Autonomous Navigation around Non-Cooperative Targets." *IEEE Aerospace Conference*, 2022. arXiv:2301.09056
32. **Pajusalu, M.; Iakubivskyi, I.; Schwarzkopf, G. J.; et al.** "SISPO: Space imaging simulator for proximity operations." *PLOS ONE* 17(3), e0263882, 2022. doi:10.1371/journal.pone.0263882
33. **Pugliatti, M.; Buonagura, C.; Topputo, F.** "CORTO: The Celestial Object Rendering TOol at DART Lab." *Sensors* 23(23), 9595, 2023. doi:10.3390/s23239595. *Full text not read.*
34. **Denninger, M.; Sundermeyer, M.; Winkelbauer, D.; et al.** "BlenderProc." arXiv:1911.01911, DLR, 2019.
35. **Kluge, S.; Staadt, O.** "Assessing Photorealism of Rendered Objects in Real-World Images." arXiv:2407.01767, 2024.
36. **Paul, J.; Dettmann, A.; Girault, B.; et al.** "INVERITAS: A facility for hardware-in-the-loop long distance movement simulation." *Acta Astronautica* 116, 1-24, 2015. *Secondary source only.*
37. **Pasqualetto Cassinis, L.; Menicucci, A.; Gill, E.; et al.** "On-ground validation of a CNN-based monocular pose estimation system for uncooperative spacecraft." *Acta Astronautica* 196, 123-138, 2022. doi:10.1016/j.actaastro.2022.04.002. *Secondary source only.*

### 13.5 Rolling shutter

38. **Karpenko, A.; Jacobs, D.; Baek, J.; Levoy, M.** "Digital Video Stabilization and Rolling Shutter Correction using Gyroscopes." Stanford University, Technical Report CTSR 2011-03, 2011.
39. **Mo, J.; Islam, M. J.; Sattar, J.** "IMU-Assisted Learning of Single-View Rolling Shutter Correction." arXiv:2011.03106, 2021.
40. **Zhu, L.; Zhou, Z.; Liu, X.; et al.** "RIFLE: Removal of Image Flicker-Banding via Latent Diffusion Enhancement." arXiv:2509.24644v4, 2025.
41. *"Rolling Shutter Distortion Modeling and Corrective Algorithm for Agility Improvement of Star Sensors." IEEE Sensors Letters, 2023.* **Authors unverified, paywalled. Do not cite without retrieving.**

### 13.6 Sensors, optics, hardware

42. **Sony Semiconductor Solutions.** "IMX477-AACK-C, Type 1/2.3 12.3 Mega-Pixel CMOS Image Sensor." Document E17203. **Sections 8-2 onward watermarked CONFIDENTIAL.**
43. **Sony Semiconductor Solutions.** "IMX296LQR product flyer Ver.1.0," 2018. *Gives sensitivity and saturation in mV but not the test luminance.*
44. **Arducam.** "C1508ZM04 / LN043: C-Mount Lens, 8 mm, Manual Focus, Adjustable Aperture." Optical format 2/3″, f/1.6-F16, MOD 0.15 m, FOV 58.4°×44.6° on 2/3″, 44° H on 1/2.3″.
45. **Arducam.** "64MP Hawkeye Wiki." docs.arducam.com/Raspberry-Pi-Camera/Native-camera/64MP-Hawkeye/
46. **Raspberry Pi Ltd.** "Raspberry Pi Documentation: Camera." raspberrypi.com/documentation/accessories/camera.html
47. **Blender Foundation.** "SunLight(Light), Blender Python API Reference" and "Color Management, Blender Manual."
48. **Chao, C.; Chou, K.-Y.; Liu, C.; et al.** "Blooming and Antiblooming in 1.1 µm-Pixel CIS." *International Image Sensor Workshop*, 2013.
49. **Ailuri, P. R.; Skorka, O.; Li, N.; et al.** "Correlation of Photo-Response Blooming Metrics with Image Quality in CMOS Image Sensors." *IS&T Electronic Imaging*, 2016. doi:10.2352/ISSN.2470-1173.2016.13.IQSP-203

### 13.7 Tethered systems

50. **Glaese, J. R.** "Tethered Satellite System (TSS) Dynamics Assessments and Analyses: TSS-1R Post Flight Data Evaluation." NASA Marshall Space Flight Center, 1996.
51. **Nohmi, M.** "Initial Orbital Performance Result of Nano-Satellite STARS-II." *i-SAIRAS*, 2014.
52. **Yamagiwa, Y.; Nohmi, M.; Aoki, Y.; et al.** "Space Experiments on Basic Technologies for a Space Elevator Using Microsatellites." *Acta Astronautica* 138, 570-578, 2017. doi:10.1016/j.actaastro.2016.12.022

### 13.8 Internal LINKU deliverables

- **D5 Sub-Report:** *LINKU Stereo Vision System Report*, WP-2200-D5, Issue 2 Rev 2.
- **D5 APSCO:** *LINKU Mission Requirements and General Configuration*, WP-2200-D5, Issue 1 Rev 1.
- *Dark-Room Solar Illumination Specification for Tether Imaging*, Issue 1 Rev 0.
- *A Guided, Self-Evaluating Stereo Calibration Procedure*, Issue 1 Rev 0.
- *Blender Simulation Realism Validation for Tether Imaging*, Issue 1 Rev 0. **Working draft.**
- *Rotation and Rolling-Shutter Correction Experiment*, Issue 1 Rev 0. **Working draft.**
- *Master Work Plan: Camera System and Tether Reconstruction*, Issue 1 Rev 0.
- Deliverables **D2** (tether modelling), **D3** (tether materials and environment), **D4** (tethered-system dynamic analysis), referenced but outside this payload.

---

## 14. Status ledger

### 14.1 Done

Flight-sensor decision recorded (B0308, with the caveats of 2.2). Software parametrised for a sensor swap (`sensor_type` and `sensor_mode_bits`). Blender dark-tether bug resolved (`scale.z = 0`). Hardware inventory, shopping list and mounting proposal. IMX296 global-shutter evaluation. LINKU structure replicated in Blender with quantitative validation (11 cm vs 10 cm). **Integrated cameras + CM5 rigid support designed, printed, assembled and verified, 13 October 2026.** Calibration failure diagnosed over the full archive. Guided calibration logic built and validated offline. Illumination specification and measurement protocol complete.

### 14.2 The one physical blocker, now cleared

For most of the project the recurring blocker was "mount the finalised camera sensor". The integrated support closed on 13 October. This unblocks full-resolution recalibration, the rotation rig, end-to-end prototype validation and the 3D Blender comparison.

> **Open decision, recorded 13 October and still unresolved.** The calibration session was originally planned against the old mounting. Now that the integrated support exists, calibrating the old mounting and then moving the cameras would **invalidate the calibration**, because the stereo geometry changes. The coherent choice is to calibrate directly on the integrated support, which is the geometry the experiment will run with. **Confirm before capturing the board.**

### 14.3 Pending, nearest first

| Item | Blocker |
|---|---|
| Full-resolution calibration session at 4056 × 3040, covering the four tilt bins | None, pending the decision above |
| Instrument mounted on the teammate's LINKU structure | **External**: teammate's structure |
| Dark-room date | **External**: teaching staff |
| Black-box moving-thread experiment | The two above |
| Dark-room light characterisation (Section 7 protocol) | Dark room |
| Mine the remaining 59 of 65 capture sessions into the datasets | None |
| Validate the Random Forest on unseen data, split **by session** | Dataset mining |
| Grow the path dataset to 30, prioritising crossings and knots | Dataset mining |
| CM5 power bench measurement at four stages | None |
| JPEG file size and images per pass | None |
| Rolling shutter Phase 1, synthetic | None. The easiest item to pull forward |
| Laboratory render and 2D comparison against the reference pair | Light characterisation |
| Wire the guided calibration loop into the GUI | None, about 4 hours |
| Fix the AI mask so it reaches the pipeline | None, a few lines |
| Fix the PLY colour overflow | None, one line |

### 14.4 Deferred to 2027

B0308 purchase and migration (new calibration at 4608 × 2592). Model 2, the learned branch scorer. Physical rotation rig, flagged as the most uncertain effort estimate in the plan. Orbital-condition renders, conditional on laboratory agreement. On-board quality pre-filter. Concept of operations document.

### 14.5 Hard deadline

**Instrument integrated into the LINKU structure, inside the dark room, with the black-box experiment run, by end of November 2026.**

---

*Compiled 15 October 2026. Every number here is traceable to a source file, a datasheet, a primary standard or a measurement still on disk. Where it is not, it is labelled ASSUMED or PLANNED. If you need the underlying data for anything, the paths are in the text.*

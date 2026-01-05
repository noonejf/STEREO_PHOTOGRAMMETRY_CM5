# Wire/Cable Matching Strategy - Technical Documentation

## Problem Statement

Stereo matching for **uniformly white cables** on dark backgrounds fails with standard algorithms:

### Why SGBM Fails
- SGBM (Semi-Global Block Matching) relies on **texture** (pixel intensity variation)
- A uniformly white cable has **identical pixel values** everywhere (255, 255, 255)
- Every patch looks the same → **ambiguous matches**
- Result: Incorrect disparities with high variation (Std: 72px)

### Initial Attempts
1. **Intensity-based NCC matching**: Failed - white patches too similar
2. **Skeleton extraction + matching**: Failed - lost shape or got random disparities
3. **Edge pixels + intensity matching**: Failed - borders detected but matches ambiguous

## Solution: Gradient-Based Matching

### Core Concept

Instead of matching pixel **intensities**, match pixel **gradients** (edge information).

```
White Cable Interior:  [255, 255, 255] → Gradient ≈ 0 (no change)
Cable Border:          [255, 200, 100, 0] → Gradient >> 0 (sharp transition)
```

### Implementation

#### Step 1: Calculate Gradients
```python
# Sobel operators compute gradients in X and Y directions
left_grad_x = cv2.Sobel(left_img, cv2.CV_32F, 1, 0, ksize=3)
left_grad_y = cv2.Sobel(left_img, cv2.CV_32F, 0, 1, ksize=3)

# Gradient magnitude = sqrt(gx² + gy²)
gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
```

#### Step 2: Extract Edge Points from Mask
```python
# Use edge-detected mask directly (no skeleton thinning)
# Mask already contains white=edges, black=background
skeleton_points = np.column_stack(np.where(mask > 0))  # All edge pixels
sampled_points = skeleton_points[::sample_step]  # Sample every N pixels
```

#### Step 3: Gradient-Based NCC Matching
```python
for each edge_point in left_image:
    # Extract gradient patch (7x7)
    patch_left_mag = gradient_magnitude[edge_point]

    # Skip if gradient too low (not a real edge)
    if mean(patch_left_mag) < 10:
        continue

    # Search along epipolar line in right image
    for x_right in search_range:
        patch_right_mag = gradient_magnitude_right[x_right]

        # Correlate gradient patterns
        ncc_score = correlate(patch_left_mag, patch_right_mag)

        if ncc_score > best_score:
            best_match = x_right
```

### Why This Works

| Feature | Intensity Matching | Gradient Matching |
|---------|-------------------|-------------------|
| Cable interior | All pixels = 255 (identical) | Gradient ≈ 0 (rejected) |
| Cable borders | White pixels (ambiguous) | Strong gradients (unique) |
| Background | Black pixels (uniform) | Low gradients (rejected) |
| Edge transitions | Ignored in uniform areas | **Captured distinctly** |

## Parameters

```python
patch_size = 7         # Small patches for localized gradients
sample_step = 3        # Dense sampling (every 3 pixels)
ncc_threshold = 0.60   # More permissive (gradients less correlated than intensity)
max_disparity = 256    # Standard range
gradient_threshold = 10  # Minimum gradient magnitude to consider
```

## Pipeline Flow

```
1. Load stereo images (left, right)
2. Load user-generated edge masks (from GUI tuner)
3. Rectify images
4. Calculate Sobel gradients (gx, gy) for both images
5. Extract border pixels from mask (use_thinning=False)
6. For each border pixel:
   a. Extract gradient magnitude patch
   b. Check if gradient > threshold
   c. Search epipolar line in right image
   d. Find best match via NCC on gradients
   e. Calculate disparity
7. Filter outliers (global median-based)
8. Convert to 3D point cloud
```

## Expected Results

- **Match rate**: 30-50% (vs 5% with intensity)
- **Disparity std**: <30px (vs 72px with intensity)
- **Valid points**: 5,000-10,000 (from 28,431 candidates)
- **Processing time**: ~10 minutes (28,431 points × 256 search range)

## Code Locations

- **WireMatcher class**: `processing/wire_matcher.py`
  - `find_correspondence_epipolar()`: Gradient matching logic (line 132-232)
  - `compute_disparity_sparse()`: Main processing loop (line 234-337)

- **StereoProcessor integration**: `processing/stereo_processor.py`
  - `compute_disparity_wire_guided()`: Entry point (search for method)

- **Test script**: `test_wire_guided_matching.py`

## Future Optimizations

1. **Parallel processing**: Process points in batches using multiprocessing
2. **Adaptive sampling**: Higher density where curvature is high
3. **Gradient orientation**: Use both magnitude AND direction for matching
4. **Multi-scale**: Compute gradients at multiple scales
5. **GPU acceleration**: Use CUDA for gradient computation

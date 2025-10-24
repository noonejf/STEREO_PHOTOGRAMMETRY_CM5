# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stereo photogrammetry system for **Raspberry Pi CM5** with **Arducam HQ 477 (IMX477 12MP)** dual cameras. Provides PyQt5-based GUI for camera calibration, synchronized stereo capture, and 3D model reconstruction. Designed for space applications and industrial inspection requiring robust computer vision.

## Key Commands

### Running the Application

```bash
# Main application
python3 main.py

# First-time setup guide
python3 quick_start.py

# System diagnostics
python3 demo_system_check.py

# Test calibration module
python3 test_calibration_module.py
```

### Installation

```bash
# Automated installation (Raspberry Pi OS Bookworm)
python3 install_setup.py

# Manual dependency installation
pip3 install -r requirements.txt

# System packages (prefer apt over pip on Raspberry Pi)
sudo apt install python3-pyqt5 python3-opencv libcamera-apps
```

### Camera Verification

```bash
# List available cameras
libcamera-hello --list-cameras

# Test individual cameras
libcamera-hello --camera 0 -t 2000
libcamera-hello --camera 1 -t 2000
```

### Development Utilities

```bash
# Clean temporary files
python3 -c "from utils.file_manager import FileManager; fm = FileManager(); print(fm.cleanup_temp_files())"

# Check storage usage
python3 -c "from utils.file_manager import FileManager; fm = FileManager(); print(fm.get_storage_usage())"

# View logs
tail -f logs/stereo_photogrammetry.log
```

## Architecture Overview

### Core Data Flow

```
GUI Layer (PyQt5)
    ↓
Configuration Layer (camera_config.py)
    ↓
Hardware Layer (stereo_camera.py) → libcamera interface
    ↓
Processing Layer (stereo_processor.py) → OpenCV algorithms
    ↓
Export Layer (point_cloud_generator.py) → PLY/XYZ/PCD/OBJ
```

### Key Components

**Configuration Management** (`config/camera_config.py`)
- Manages camera settings (resolution, FPS, exposure, gain)
- Stores calibration matrices in JSON format
- Auto-loads existing calibration on startup
- Methods: `get_capture_settings()`, `is_calibrated()`, `get_calibration_info()`

**Stereo Camera System** (`camera/stereo_camera.py`)
- Abstracts dual Arducam HQ 477 operations via libcamera-jpeg calls
- Verifies camera availability on initialization
- Creates timestamped capture sessions
- Methods: `verify_cameras()`, `capture_calibration_pair()`, `capture_stereo_pair()`

**Calibration Engine** (`camera/camera_calibration.py`)
- Detects chessboard corners (9x6 internal squares, 24mm size)
- Computes intrinsic/extrinsic parameters, rectification maps
- Validates calibration quality (target: <0.5 pixel error)
- Methods: `calibrate_from_session()`, `detect_chessboard_corners()`, `validate_calibration()`

**Stereo Processor** (`processing/stereo_processor.py`)
- Implements SGBM (Semi-Global Block Matching) - high quality, ~30-60s
- Implements BM (Block Matching) - fast, ~10-20s
- Performs rectification, disparity computation, outlier filtering
- Methods: `process_stereo_pair()`, `filter_disparity()`, `compute_point_cloud()`

**Point Cloud Generator** (`processing/point_cloud_generator.py`)
- Exports to PLY (binary/ASCII with colors), XYZ, PCD, OBJ formats
- Handles voxel downsampling and optional normal computation
- Methods: `export_point_cloud()`, `_export_ply()`, `_export_xyz()`

**GUI Components** (`gui/`)
- `MainWindow`: Main application layout with preview, controls, status
- `CameraPreviewWidget`: Real-time camera feed
- `CalibrationDialog`: Interactive calibration workflow with countdown
- `ProcessingDialog`: Algorithm selection, parameter tuning, visualization

### Threading Architecture

- **CountdownThread** (MainWindow): Non-blocking countdown timer
- **CalibrationProcessingThread** (CalibrationDialog): Background calibration
- **ProcessingWorkerThread** (ProcessingDialog): Background 3D processing

All use Qt threads to prevent UI freezing during long operations.

## Critical Configuration

### Camera Setup (Arducam HQ 477)

Edit `/boot/firmware/config.txt` (or `/boot/config.txt` on older systems):
```
camera_auto_detect=0
dtoverlay=imx477,cam0
dtoverlay=imx477,cam1
gpu_mem=128
start_x=1
```
**Reboot required after changes.**

### Resolution Settings

Configured in `config/camera_config.py`:
```python
capture_resolution = (3840, 2880)  # High quality for 3D
preview_resolution = (1920, 1440)  # Balanced for UI
```

### Calibration Requirements

- **Chessboard**: 10x7 squares (9x6 internal corners)
- **Square size**: 24mm
- **Minimum images**: 10-30 (25 typical)
- **Quality target**: <0.5 pixel reprojection error (excellent), <1.0 (good)

### Data Persistence

- **Camera settings**: `config/camera_settings.json`
- **Calibration data**: `data/calibration/calibration_data.json`
  - Contains: camera matrices, distortion coefficients, R, T, rectification matrices
  - Format: JSON with numpy arrays serialized as lists
- **Calibration sessions**: `data/calibration/calibration_YYYYMMDD_HHMMSS/`
- **Capture sessions**: `data/captures/stereo_YYYYMMDD_HHMMSS/`
- **Results**: `data/results/` (PLY, XYZ, PCD, OBJ files)

## Calibration Workflow

1. User clicks "Calibrate" → `CalibrationDialog` launched
2. Preview shows chessboard with 10-second countdown timer
3. User moves chessboard through 25 iterations capturing pairs
4. Background thread processes each pair:
   - Refines corner detection
   - Computes intrinsic/extrinsic parameters
   - Validates quality
5. Stereo calibration computes R/T between cameras
6. Saves to `data/calibration/calibration_data.json`

## 3D Reconstruction Workflow

1. User clicks "Process Latest Captures" → `ProcessingDialog`
2. Select algorithm:
   - **SGBM**: High quality, slower (~30-60s)
   - **BM**: Fast, lower quality (~10-20s)
3. Processing pipeline:
   - Load calibration matrices
   - Rectify images
   - Compute disparity map
   - Apply median + WLS filtering
   - Filter outliers
   - Convert to 3D point cloud
4. Export to selected formats (PLY/XYZ/PCD/OBJ)

## Common Development Tasks

### Adding New Export Formats

Extend `processing/point_cloud_generator.py`:
```python
def _export_new_format(self, points, colors, output_file):
    # Implementation here
    pass
```

### Modifying Algorithm Parameters

SGBM/BM parameters in `processing/stereo_processor.py`:
```python
# Adjust for performance vs quality trade-offs
numDisparities = 96  # Reduce to 64 for speed
blockSize = 5        # Increase for noise reduction
```

### Extending Camera Support

Modify `config/camera_config.py` and `camera/stereo_camera.py` to support different camera models. Key changes:
- Update libcamera command generation
- Adjust resolution constraints
- Modify calibration board parameters if needed

## Hardware Considerations

### Raspberry Pi CM5 Constraints

- **CPU**: ARM-based, limited vs desktop
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: High-speed SD card (64GB+) recommended
- **Sync timing**: <50ms between cameras (target), <100ms (acceptable)

### Performance Optimization Strategies

1. **Resolution management**: Use lower resolution for preview (1920x1440) vs capture (3840x2880)
2. **Algorithm selection**: BM for real-time feedback, SGBM for final output
3. **Calibration efficiency**: 25 images balances quality and speed
4. **Voxel downsampling**: Applied to reduce point cloud size

### Expected Performance Metrics

- **Calibration**: 25 images → 3-5 minutes
- **Capture**: ~2-3 seconds per stereo pair
- **Processing (SGBM)**: ~30-60 seconds
- **Processing (BM)**: ~10-20 seconds
- **Export**: ~5-15 seconds
- **3D accuracy**: ~1-2mm at 1 meter distance
- **Point cloud density**: 60-80% valid pixels

## Logging and Debugging

### Log System

- **Location**: `logs/stereo_photogrammetry.log`
- **Rotation**: 10MB max per file
- **Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Format**: Colored console output via colorlog

### Common Issues

**"No se detectaron cámaras"**
- Verify `/boot/firmware/config.txt` has correct dtoverlay entries
- Check `libcamera-hello --list-cameras` shows 2 cameras
- Verify CSI cable connections to CAM0/CAM1

**"Calibración falla repetidamente"**
- Ensure 10x7 chessboard (9x6 internal corners)
- Check uniform lighting without reflections
- Keep board completely flat
- Move board to different angles/distances covering full FOV

**"PyQt5 no se instala"**
- Use apt instead of pip: `sudo apt install python3-pyqt5`

**"Procesamiento 3D muy lento"**
- Reduce capture resolution: `(2560, 1920)` instead of `(3840, 2880)`
- Use BM algorithm instead of SGBM
- Reduce numDisparities to 64

## Important Design Patterns

### State Management

MainWindow tracks:
- `is_calibrated`: Boolean for valid calibration
- `preview_active`: Boolean for live preview
- `stereo_camera`: StereoCamera instance (created once)
- `camera_config`: CameraConfig instance (auto-loaded with calibration)

### Error Handling

- System checks before GUI launch (verify OpenCV, PyQt5, cameras)
- Exception handling in Qt dialogs with user-friendly messages
- Graceful degradation (preview continues if processing fails)
- Detailed error logging to rotating files

### Configuration Persistence

- Dataclasses for typed settings (`CameraSettings`, `StereoConfig`)
- JSON serialization with numpy array conversion
- Automatic loading on CameraConfig initialization
- Fallback to defaults if files missing

## Technology Stack

- **Python**: 3.9+
- **GUI**: PyQt5 (native on Raspberry Pi, avoid pip installation)
- **Computer Vision**: OpenCV 4.5+, numpy, scipy, scikit-image
- **3D Processing**: open3d-python (may need special ARM build)
- **Hardware Interface**: libcamera-apps, python3-picamera2 (optional)
- **Logging**: colorlog for colored output
- **Scientific**: matplotlib, pandas
- **Image Processing**: Pillow

## Use Cases

**Space Applications**
- Satellite component inspection
- Inter-satellite distance measurement
- Structure deployment verification

**Industrial Applications**
- 3D quality control
- Manufactured part measurement
- Automated inspection

**Research Applications**
- Motion analysis
- Precise scientific measurements
- 3D specimen documentation

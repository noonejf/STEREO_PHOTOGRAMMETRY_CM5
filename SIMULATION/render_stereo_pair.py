"""Render both cameras of a scene and write a capture folder the app can open.

    blender --background SIMULATION/TV2_Room_40x20x10.blend \
            --python SIMULATION/render_stereo_pair.py -- \
            --name tv2_axis --samples 256

It writes ``data/captures/stereo_sim_<name>_<stamp>/`` with left.jpg,
right.jpg and the same metadata.json the earlier simulated pairs use, so
the Processing page reads it exactly like a real capture.

**These are renders, not photographs, and the metadata says so.** The
cameras here are ideal pinholes carrying the *nominal* optics: 8 mm on the
IMX477's 1.55 um pixel, which is fx = 5161 px, principal point exactly
centred, no distortion. The rig's measured calibration is not that. It
reports fx = 2685 px at 1920 wide, which is 5672 px scaled to 4056, nearly
10% longer, with cx at 694.8 where the centre of a 1920-wide image is 960,
and five distortion coefficients that are far from zero. That calibration
is flagged ``is_good_quality: false`` by the system that produced it, at
1.53 px reprojection error, so matching it would mean reproducing a known
bad fit. Rendering the nominal optics is the defensible choice, and the
difference is a real one to keep in mind: a 10% error in focal length is
a 10% error in every reconstructed distance.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="tv2")
    ap.add_argument("--samples", type=int, default=0,
                    help="0 keeps whatever the .blend was saved with")
    ap.add_argument("--scale", type=int, default=100,
                    help="resolution percentage, for a quick look")
    ap.add_argument("--note", default="")
    args = ap.parse_args(argv)

    scene = bpy.context.scene
    if args.samples:
        scene.cycles.samples = args.samples
    scene.render.resolution_percentage = args.scale
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 95

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(ROOT, "data", "captures",
                           f"stereo_sim_{args.name}_{stamp}")
    os.makedirs(out_dir, exist_ok=True)

    cams = {"left": "Cam_L", "right": "Cam_R"}
    meta = {
        "capture_name": os.path.basename(out_dir),
        "source": "blender_simulation",
        "blend_file": os.path.relpath(bpy.data.filepath, ROOT).replace("\\", "/"),
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "note": args.note or ("Rendered from the scripted TV2 room. Ideal "
                              "pinhole cameras with the nominal 8 mm optics, "
                              "no lens distortion, principal point centred. "
                              "Not a real camera capture and not the rig's "
                              "measured calibration."),
        "samples": scene.cycles.samples,
        "view_transform": scene.view_settings.view_transform,
        "exposure_stops": scene.view_settings.exposure,
    }

    for side, cam_name in cams.items():
        cam = bpy.data.objects[cam_name]
        scene.camera = cam
        path = os.path.join(out_dir, f"{side}.jpg")
        scene.render.filepath = path
        print(f"[render] {side} from {cam_name} -> {path}", flush=True)
        bpy.ops.render.render(write_still=True)
        meta[f"{side}_camera"] = {
            "blender_object": cam_name,
            "file": os.path.relpath(path, ROOT).replace("\\", "/"),
            "location_m": [round(v, 4) for v in cam.location],
            "focal_mm": cam.data.lens,
            "sensor_width_mm": cam.data.sensor_width,
            "resolution": [scene.render.resolution_y, scene.render.resolution_x, 3],
        }

    lx = meta["left_camera"]["location_m"][0]
    rx = meta["right_camera"]["location_m"][0]
    meta["baseline_mm"] = round(abs(rx - lx) * 1000.0, 3)

    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=4)
    print(f"[render] wrote {out_dir}", flush=True)


main()

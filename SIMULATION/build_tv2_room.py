"""Build the 40 x 20 x 10 m dark-room scene in Blender, from a script.

Run it headless, from the repository root::

    blender --background --python SIMULATION/build_tv2_room.py -- \
            --out SIMULATION/TV2_Room_40x20x10.blend

or open Blender, paste it into the Text Editor and press Run. Every number it
sets is taken from the project's own deliverables and is listed again in the
JSON it writes next to the .blend, so a render can be traced back to the
parameters that produced it.

READ THIS BEFORE RENDERING
--------------------------
A 1 mm tether seen end-on down 40 m of room is **not observable** with the
optics on the rig. The width it projects to, with the fitted 8 mm lens on the
IMX477 and its 1.55 um pixel, is:

    5 m      1.03 px
    10 m     0.52 px
    20 m     0.26 px
    40 m     0.13 px

and the resolution limit of 1 px lands at 5.17 m.

**That last number is a width, and width is not the same as visibility.**
This paragraph used to continue "the far 35 m of the room produces nothing
for the pipeline to segment", which the first actual render disproved. A
bright object thinner than a pixel does not vanish; it deposits less energy
into that pixel, and against a near-black field what is left is still well
above the floor. Measured on the rendered pair, left camera, brightness out
of 255 against distance:

    0.6 m  157      5 px wide
    1 m    143      3 px
    2 m    116      2 px
    5 m     91      2 px
    12 m    55      2 px
    20 m    45      1 px
    30 m    41      1 px
    38 m    37      lost

So the cord stays detectable to roughly 29 m, not 5. Two cautions before
anyone quotes that: this render has a perfectly black background and no
sensor noise, so the real floor is higher and the real distance shorter;
and past about 15 m the cord covers one pixel, which is enough to find it
and not enough to measure its width or to locate its centre to the
sub-pixel precision triangulation wants. Detectable and measurable are
different questions, and this room answers the first one.

A longer lens resolves the far end but cannot hold it in focus. At 62 mm the
tether is 1.00 px at 40 m, but the depth of field at f/1.6 focused at 20 m is
19.7 to 20.3 m, half a metre, and even stopped down to f/16 it is 17.7 to
23.0 m. Resolution at 40 m wants a long lens and depth across 40 m wants a
short one, and no setting on the shelf does both.

So the room is worth building, but not for measuring 40 m of thread. It is
worth building to measure **where detection fails**: run the tether down the
axis and the image shows, in one frame, the distance at which the thread
stops being segmentable. That is a number the project does not have and
cannot get from the 3.5 m enclosure, and it bears directly on the mission,
where the tether is specified up to 100 m.

Pass --focal to try another lens and --tether-span to shorten the run.
"""
import json
import math
import os
import sys

try:
    import bpy
    from mathutils import Euler, Vector
except ImportError:  # pragma: no cover - lets the file be imported for its constants
    bpy = None


# --------------------------------------------------------------- parameters

ROOM = dict(depth_m=40.0, width_m=20.0, height_m=10.0)

#: IMX477 as fitted. The pixel pitch is what converts focal millimetres into
#: the fx the pipeline actually uses, so it is the number that matters.
SENSOR = dict(
    name="IMX477",
    width_px=4056, height_px=3040,
    pixel_um=1.55,
    width_mm=6.287, height_mm=4.712,
)

OPTICS = dict(
    focal_mm=8.0,          # Arducam C1508ZM04, the lens on the rig
    f_number=1.6,
    baseline_mm=100.0,
)

#: AM0, not the ground-level value. Most Blender tutorials and scene
#: templates assume a terrestrial, atmosphere-filtered Sun at around
#: 1050 W/m2, which is the single easiest way to get this scene wrong.
#: Where the beam comes from, in degrees. Elevation is above the horizon;
#: azimuth is measured about the vertical, and **zero puts the beam in the
#: plane that bisects the stereo baseline**, which is the only azimuth that
#: lights the cord the same for both cameras.
#:
#: That is not a preference, it is measured. The baseline runs along X, so
#: an azimuth with an X component lights the cord on one side and leaves
#: the other camera looking at the shadow, and with 2% walls there is no
#: fill to even it out. Rendering the same scene at four azimuths, peak
#: brightness and detectable pixels per camera:
#:
#:     azimuth   beam X   left   right   ratio   px left   px right
#:       -70      0.852    173      34    5.09       310          0
#:       -35      0.520    156      50    3.12       312         19
#:         0      0.000     92      93    0.99       171        179
#:        35     -0.520     48     156    0.31        20        306
#:
#: At -70, which this scene used until it was measured, the right camera
#: sees **nothing**. Stage 5 of the pipeline pairs the left path against
#: the right one, so a scene that blinds one camera cannot be used to
#: measure anything stereo at all. Zero costs peak brightness, 92 against
#: 173, and buys both cameras.
#:
#: In orbit the sun is wherever it is and this is a constraint rather than
#: a choice, which is a result worth carrying into the illumination
#: deliverable: the lamp in the TV2 studio has to sit in the plane that
#: bisects the baseline, or one camera is wasted.
#:
#: Elevation is then a second, independent trade, and it is not the one
#: intuition suggests. Measured at azimuth 0, where the two cameras are
#: equal by construction:
#:
#:     elevation   beam            perp to cord   peak   px left   px right
#:         0       (0, 0.00,-1.00)      100%       139      165        195
#:        20       (0, 0.34,-0.94)       94%       135      180        199
#:        40       (0, 0.64,-0.77)       77%       123      190        209
#:        65       (0, 0.91,-0.42)       42%        92      171        179
#:        85       (0, 1.00,-0.09)        9%        51       11         17
#:
#: Peak brightness is highest straight overhead, where the whole beam is
#: perpendicular to a cord running down +Y. **Detectable length is not**,
#: and detectable length is what this scene exists to measure. Overhead
#: light puts the bright band on top of the cylinder while the cameras
#: look at its side; tilting towards the cameras trades peak for the
#: surface they actually see, and 40 degrees collects the most cord before
#: the beam starts running along the cord instead of across it.
SUN_GEOMETRY = dict(elevation_deg=40.0, azimuth_deg=0.0)

SUN = dict(
    irradiance_w_m2=1361.0,       # IAU 2015 nominal
    blackbody_k=5772.0,           # IAU 2015 nominal effective temperature
    angular_diameter_rad=0.00918043,   # 0.526 deg, Blender's default, already correct
)

TETHER = dict(diameter_mm=1.0, span_m=38.0, sag_m=0.0, material_albedo=0.65)

#: Exposure is a stop offset applied after the render, and it is the only
#: correct place to control brightness: the light's value is a physical
#: quantity and changing it would make the scene a different scene.
#:
#: At 0.0 the first render of this room came out uniformly white. That is
#: arithmetic, not a surprise. A Lambertian surface of albedo rho under
#: irradiance E radiates E*rho/pi, so a perfect white wall under the AM0
#: 1361 W/m2 sits at 433, and even 2 percent black molton sits at 8.7,
#: while the display maps 1.0 to white. The offset below puts a notional
#: white Lambertian surface at 1.0, which leaves the black walls near 0.02
#: where they belong and the lit tether well inside range.
EXPOSURE_WHITE_REFERENCE = -math.log2(1361.0 / math.pi)   # about -8.76

RENDER = dict(view_transform="AgX", exposure=EXPOSURE_WHITE_REFERENCE,
              samples=256, engine="CYCLES")


def projected_width_px(focal_mm, distance_m, diameter_mm=1.0, pixel_um=1.55):
    """Width in pixels of a thread of given diameter at a given distance."""
    return focal_mm * diameter_mm / (distance_m * 1000.0 * (pixel_um / 1000.0))


def depth_of_field(focal_mm, f_number, focus_m, coc_mm=None, pixel_um=1.55):
    coc_mm = coc_mm if coc_mm is not None else pixel_um / 1000.0
    s = focus_m * 1000.0
    H = focal_mm * focal_mm / (f_number * coc_mm) + focal_mm
    near = s * (H - focal_mm) / (H + s - 2 * focal_mm)
    far = float("inf") if H <= s else s * (H - focal_mm) / (H - s)
    return near / 1000.0, (far / 1000.0 if far != float("inf") else float("inf"))


def horizontal_fov_deg(focal_mm, sensor_w_mm=6.287):
    return 2.0 * math.degrees(math.atan(sensor_w_mm / (2.0 * focal_mm)))


# --------------------------------------------------------------- scene build

def _clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                  bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def _matte_black(name="RoomBlack", albedo=0.02):
    """Black molton, not a perfect absorber.

    A zero-reflectance room is not what a real blacked-out studio is, and the
    difference matters: the small amount of light the walls return is what
    fills the shadow side of the tether, which is exactly what orbit does not
    do. 2 percent is representative of black velvet or molton.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (albedo, albedo, albedo, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.95
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.05
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.05
    return mat


def _cord_material(albedo=0.65):
    mat = bpy.data.materials.new("TetherCord")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (albedo, albedo * 0.97, albedo * 0.88, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.6
    return mat


def build_room(depth, width, height):
    """An inward-facing box. Origin on the floor at the camera end."""
    # size=1.0 gives a cube whose vertices sit at plus or minus 0.5, so the
    # scale is the full dimension, not half of it. Halving it, which is what
    # you write by reflex because the default cube is size=2.0, built the
    # room at half scale: 10 x 20 x 5 instead of 20 x 40 x 10, centred at
    # y=20 so that it spanned y=10 to y=30. The cameras sit at y=0.5 and
    # were therefore outside the box, with the tether running through the
    # wall. Nothing errored; the render would simply have been wrong.
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    room = bpy.context.active_object
    room.name = "Room"
    room.scale = (width, depth, height)
    room.location = (0.0, depth / 2.0, height / 2.0)
    bpy.ops.object.transform_apply(scale=True, location=True)

    # flip the normals so the shading is on the inside
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode="OBJECT")

    room.data.materials.append(_matte_black())

    # The walls do not block the lamp. A Sun in Blender is directional and
    # infinitely distant, so its rays arrive from outside the scene no
    # matter where the object sits, and a sealed box stops every one of
    # them: the first render of this scene came out uniformly black, which
    # looks like a dark room working and is actually a dark room with the
    # lights off. Turning off shadow visibility makes the box what it is
    # meant to be, a light trap that absorbs stray bounces and reads black
    # to the camera, rather than an occluder of the source.
    #
    # This encodes a choice worth knowing about. It simulates the orbital
    # case, the AM0 sun of SUN["irradiance_w_m2"] falling on the tether
    # inside an enclosure that reflects nothing. To simulate the TV2
    # studio instead, where a real lamp stands inside the room, replace
    # the Sun with an AREA or SPOT light at a position inside the box and
    # leave the walls occluding.
    room.visible_shadow = False
    return room


def build_tether(span, height, diameter_mm, sag, segments=512):
    """A curve down the long axis, with optional sag, given a round bevel."""
    curve = bpy.data.curves.new("TetherCurve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 4
    spline = curve.splines.new("POLY")
    spline.points.add(segments - 1)
    y0, y1 = 1.0, 1.0 + span
    for i in range(segments):
        t = i / (segments - 1)
        y = y0 + t * (y1 - y0)
        z = height - sag * math.sin(math.pi * t)
        spline.points[i].co = (0.0, y, z, 1.0)
    curve.bevel_depth = (diameter_mm / 1000.0) / 2.0
    curve.bevel_resolution = 4

    obj = bpy.data.objects.new("Tether", curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(_cord_material(TETHER["material_albedo"]))
    return obj


def build_stereo_pair(focal_mm, baseline_mm, sensor, z, look_along=(0, 1, 0)):
    """Two cameras at the near end, baseline across X, both looking down +Y."""
    cams = []
    half = (baseline_mm / 1000.0) / 2.0
    for name, x in (("Cam_L", -half), ("Cam_R", +half)):
        data = bpy.data.cameras.new(name)
        data.type = "PERSP"
        data.lens = focal_mm
        data.sensor_fit = "HORIZONTAL"
        data.sensor_width = sensor["width_mm"]
        data.clip_start = 0.05
        data.clip_end = 200.0
        obj = bpy.data.objects.new(name, data)
        obj.location = (x, 0.5, z)
        # default camera looks down -Z; rotate to look along +Y
        obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        bpy.context.collection.objects.link(obj)
        cams.append(obj)
    return cams


def build_sun(irradiance, blackbody_k, angle_rad, depth,
              elevation_deg=SUN_GEOMETRY["elevation_deg"],
              azimuth_deg=SUN_GEOMETRY["azimuth_deg"]):
    """A sun lamp. In Blender the strength of a Sun is W/m2 directly."""
    data = bpy.data.lights.new("Sun", type="SUN")
    data.energy = irradiance
    data.angle = angle_rad
    data.use_nodes = True
    nt = data.node_tree
    bb = nt.nodes.new("ShaderNodeBlackbody")
    bb.inputs["Temperature"].default_value = blackbody_k
    emission = nt.nodes["Emission"]
    nt.links.new(bb.outputs["Color"], emission.inputs["Color"])

    obj = bpy.data.objects.new("Sun", data)

    # The rotation is the whole of it. A Sun in Blender is directional and
    # infinitely distant, so the object's position changes nothing about
    # the light: only its local -Z axis matters, and every photon arrives
    # travelling along that. The angles below put 95% of the beam
    # perpendicular to a cord running down +Y, which is the component that
    # lights it (the remaining 31% runs along the cord and hits it end-on,
    # lighting nothing), and send it the same way the cameras look, so the
    # cord is front-lit rather than rimmed.
    rot = Euler((math.radians(elevation_deg), 0.0,
                 math.radians(azimuth_deg)), "XYZ")
    obj.rotation_euler = rot

    # The position is cosmetic, and that is exactly why it is computed
    # rather than typed. It used to be a hand-placed (6, depth/2, 6) with
    # a comment about keeping the lamp out of frame, which is reasoning
    # about a property the lamp does not have. Worse, it sat on +X while
    # shining towards +X, so the gizmo in the viewport pointed away from
    # the cord and looked like a bug every time anyone opened the file.
    # Placing it upstream of the beam makes the arrow point at the subject
    # and the viewport agree with the physics.
    # from the Euler, not from matrix_world: assigning rotation_euler does
    # not refresh matrix_world until the dependency graph is evaluated, so
    # reading it here returns the identity and puts the lamp straight
    # overhead, which is how this first went wrong.
    direction = (rot.to_quaternion() @ Vector((0.0, 0.0, -1.0))).normalized()
    target = Vector((0.0, depth / 2.0, 5.0))
    obj.location = target - direction * 8.0
    bpy.context.collection.objects.link(obj)
    return obj


def configure_render(sensor, render):
    scene = bpy.context.scene
    scene.render.engine = render["engine"]
    scene.render.resolution_x = sensor["width_px"]
    scene.render.resolution_y = sensor["height_px"]
    scene.render.resolution_percentage = 100
    if hasattr(scene, "cycles"):
        scene.cycles.samples = render["samples"]
    # AgX, not Standard: it rolls bright regions off over about 16.5 stops
    # instead of clipping them, and exposure is adjusted with the slider
    # rather than by changing the light value.
    try:
        scene.view_settings.view_transform = render["view_transform"]
        scene.view_settings.exposure = float(render["exposure"])
    except (AttributeError, TypeError):
        pass
    scene.world = scene.world or bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        bg.inputs["Strength"].default_value = 0.0


# --------------------------------------------------------------- reporting

def optics_report(focal_mm, f_number, span_m, sensor):
    rows = []
    for z in (2.5, 5.0, 10.0, 20.0, span_m):
        rows.append({"distance_m": z,
                     "tether_px": round(projected_width_px(
                         focal_mm, z, TETHER["diameter_mm"], sensor["pixel_um"]), 3)})
    limit = focal_mm * TETHER["diameter_mm"] / (sensor["pixel_um"] / 1000.0) / 1000.0
    near, far = depth_of_field(focal_mm, f_number, max(2.0, span_m / 2.0),
                               pixel_um=sensor["pixel_um"])
    return {
        "horizontal_fov_deg": round(horizontal_fov_deg(focal_mm, sensor["width_mm"]), 2),
        "one_pixel_limit_m": round(limit, 2),
        "projected_width": rows,
        "depth_of_field_focused_at_half_span_m": [round(near, 2),
                                                  None if far == float("inf") else round(far, 2)],
        "verdict": ("the far end of the span is below one pixel and will not be "
                    "detectable" if projected_width_px(
                        focal_mm, span_m, TETHER["diameter_mm"], sensor["pixel_um"]) < 1.0
                    else "the far end resolves to at least one pixel"),
    }


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="SIMULATION/TV2_Room_40x20x10.blend")
    ap.add_argument("--sun-elevation", type=float,
                    default=SUN_GEOMETRY["elevation_deg"])
    ap.add_argument("--sun-azimuth", type=float,
                    default=SUN_GEOMETRY["azimuth_deg"],
                    help="0 keeps the beam in the plane that bisects the "
                         "baseline, which is the only value that lights the "
                         "cord equally for both cameras; see SUN_GEOMETRY")
    ap.add_argument("--exposure", type=float, default=RENDER["exposure"],
                    help="stop offset applied after the render. The default "
                         "places a white Lambertian surface under the AM0 "
                         "sun at 1.0; raise it to see into the shadows")
    ap.add_argument("--focal", type=float, default=OPTICS["focal_mm"])
    ap.add_argument("--fnumber", type=float, default=OPTICS["f_number"])
    ap.add_argument("--baseline", type=float, default=OPTICS["baseline_mm"])
    ap.add_argument("--depth", type=float, default=ROOM["depth_m"])
    ap.add_argument("--width", type=float, default=ROOM["width_m"])
    ap.add_argument("--height", type=float, default=ROOM["height_m"])
    ap.add_argument("--tether-span", type=float, default=TETHER["span_m"])
    ap.add_argument("--tether-z", type=float, default=None,
                    help="tether height, default half the room height")
    ap.add_argument("--sag", type=float, default=TETHER["sag_m"])
    args = ap.parse_args(argv)

    report = optics_report(args.focal, args.fnumber, args.tether_span, SENSOR)

    if bpy is None:
        print("Not running inside Blender. Optics report only:\n")
        print(json.dumps(report, indent=2))
        return

    _clear()
    tz = args.tether_z if args.tether_z is not None else args.height / 2.0
    build_room(args.depth, args.width, args.height)
    build_tether(args.tether_span, tz, TETHER["diameter_mm"], args.sag)
    cams = build_stereo_pair(args.focal, args.baseline, SENSOR, tz)
    build_sun(SUN["irradiance_w_m2"], SUN["blackbody_k"],
              SUN["angular_diameter_rad"], args.depth,
              args.sun_elevation, args.sun_azimuth)
    render_cfg = dict(RENDER, exposure=args.exposure)
    configure_render(SENSOR, render_cfg)
    bpy.context.scene.camera = cams[0]

    params = {
        "room_m": {"depth": args.depth, "width": args.width, "height": args.height},
        "sensor": SENSOR,
        "optics": {"focal_mm": args.focal, "f_number": args.fnumber,
                   "baseline_mm": args.baseline},
        "sun": SUN,
        "sun_geometry": {"elevation_deg": float(args.sun_elevation),
                         "azimuth_deg": float(args.sun_azimuth)},
        "exposure_stops": float(args.exposure),
        "tether": {**TETHER, "span_m": args.tether_span,
                   "height_m": tz, "sag_m": args.sag},
        "render": RENDER,
        "fx_px": round(args.focal / (SENSOR["pixel_um"] / 1000.0), 2),
        "optics_report": report,
    }

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    with open(os.path.splitext(out)[0] + "_params.json", "w", encoding="utf-8") as fh:
        json.dump(params, fh, indent=2)

    print(f"Saved {out}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

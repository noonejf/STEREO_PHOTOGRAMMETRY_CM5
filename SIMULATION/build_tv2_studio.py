"""Build the TV2 studio as it actually measures, 30 x 15 x 10 m, lit by lamps.

This is the companion to ``build_tv2_room.py`` and not a replacement for it.
That file builds the **orbital** case: a 40 x 20 x 10 enclosure lit by a Sun,
which is parallel by construction because a Blender Sun has no position. This
one builds the **studio** case: the room at its real measured size, lit by a
row of rectangular area lights hanging inside it. The pair exists so the same
cord can be rendered under both and the difference measured; that difference
is the question the simulation is for.

    blender --background --python SIMULATION/build_tv2_studio.py -- \
            --out SIMULATION/TV2_Studio_30x15x10.blend

WHY THE ROOM CHANGED
--------------------
The 40 x 20 figure was wrong. The studio is **30 m long by 15 m wide**; the
10 m ceiling is the working assumption until someone measures it. Ten metres
less of room is not a cosmetic change, because the lamp row has to overhang
the cord at both ends and in a room the same length as the cord there is
nowhere to put that overhang. Measured on this geometry, with the row filling
the usable 29 m:

    lamp height over cord   cord lit to +-5%   lamps   kW
         1.5 m                   26.5 m          21    2.0
         3.0 m                   24.0 m          10    4.3
         5.0 m                   22.0 m           7    7.8

so **lower is better here**, which is the opposite of the 40 m room, where
height bought coverage. The binding constraint moved from each lamp's
footprint to the overhang, and the overhang grows with height.

THE LIMIT THAT NO LAMP FIXES
----------------------------
A 1 mm cord framed across 30 m is **0.135 px** wide, and that number does not
depend on the lens, the distance or the room: 4056 px over 30 m is 7.4 mm per
pixel. Checked against the lens needed to frame 30 m from 7.5, 10, 15 and
30 m, which is 1.57, 2.10, 3.14 and 6.29 mm; the width is 0.135 px in all
four. One pixel of width means framing at most 4.06 m of cord.

Pointing the camera down the cord does not escape it, it hides it: the far
part piles up against the vanishing point. One metre of cord spans 258 px at
1 m and 0.29 px at 30 m, and everything past 20 m, out to infinity, lands in
13 px. The cord stays visible there, measured at 42 against a background of
24 in the earlier render, which is the point: detectable and measurable are
different questions and this view only answers the first.

EXPOSURE
--------
Not the same value as the orbital scene, and copying it across is the easy
mistake. Exposure is a stop offset applied after the render, and the right
offset puts a notional white Lambertian surface at the cord's illumination
level at 1.0. Orbit means AM0, 1361 W/m2, hence -8.76. Here it is the
illumination the lamp row delivers, R5's 2320 lx, which is 23.8 W/m2 at the
97.6 lm/W that falls out of the project's own AM0 figures. That gives -2.92.
Use the orbital value here and the room renders six stops dark.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

try:
    import bpy
    from mathutils import Euler
except ImportError:  # pragma: no cover - lets the file be imported for its constants
    bpy = None


# --------------------------------------------------------------- parameters

#: The studio as measured. Height is the assumption, the other two are not.
ROOM = dict(depth_m=30.0, width_m=15.0, height_m=10.0)

SENSOR = dict(name="IMX477", width_px=4056, height_px=3040,
              pixel_um=1.55, width_mm=6.287, height_mm=4.712)

OPTICS = dict(focal_mm=8.0, f_number=1.6, baseline_mm=100.0)

#: Luminous efficacy of radiation, from the project's own AM0 pair
#: (132800 lx against 1361 W/m2). It is what converts a Blender area light's
#: radiometric watts into the photometric units a lamp datasheet uses.
LER = 132800.0 / 1361.0

#: How much light the cord has to receive, in lux. The three figures below
#: come from the illumination deliverable and they are NOT interchangeable.
#:
#: The default used to be 2320 lx labelled "R5", and that label was wrong.
#: 2320 lx is one row of the light budget, the IMX477 with the fitted 8 mm at
#: 1 deg/s (chapter4.tex:299 gives E_min = 2317 lx), and chapter4.tex:322 says
#: in so many words that dropping to it means **dropping the Hawk-eye**.
#: Requirement R5 itself (chapter5.tex:21 and :72) is sized for the Hawk-eye,
#: which is the most demanding of the three sensors, and asks for 3600 lx at
#: 1 deg/s and 10000 lx at 2.76 deg/s measured at the tether.
#:
#: AM0 is the Sun itself, 1361 W/m2 through the project's own LER. Nobody is
#: going to build it: at this geometry it is 180 kW of lamps. It is here as
#: the scale the other two are quoted against, and because the orbital scene
#: in ``build_tv2_room.py`` really does run at it, with a Sun that has no
#: position and therefore no falloff.
E_IMX477_FLOOR_LX = 2320.0     # the fitted IMX477 alone, 1 deg/s
E_R5_SLOW_LX      = 3600.0     # R5, all three sensors, 1 deg/s
E_R5_FAST_LX      = 10000.0    # R5, all three sensors, 2.76 deg/s
E_AM0_LX          = 1361.0 * LER   # the Sun, for scale only

#: What a variant gets when it does not say otherwise.
E_TARGET_LX = E_R5_SLOW_LX

TETHER = dict(diameter_mm=1.0, albedo=0.65, z_m=5.0)

#: The cord is not straight, because in flight it never is. A tether strung
#: between two satellites is pinned at both ends and carries a slow lateral
#: oscillation, so the honest shape is the first few modes of a pinned string
#: and not a line. Amplitude in metres per mode, mode k being
#: ``sin(k*pi*t)``, which is **zero at both ends by construction**: that is
#: the property to keep when editing these numbers, because the near end is
#: the midpoint of the stereo baseline and has to stay exactly there.
#:
#: 0.82 m of excursion over 24 m of cord is 3.4% of its length, the steepest
#: slope it produces is 9.6 degrees, and the arc is 0.65% longer than the
#: chord. Keeping the slope moderate is not cosmetic: the chosen view was
#: chosen because the cord's image runs across the epipolar lines, and a wave
#: steep enough to turn a stretch of it parallel to them would hand stage 5
#: the degenerate case locally.
#: Mode 1 in z is negative on purpose, so the cord bows **away** from the
#: optical axis rather than back towards it. Positive, it cancels the 0.25 m
#: anchor offset near mid-cord, the image collapses onto the principal point
#: and the one property the view was chosen for, the cord's image crossing
#: the epipolar lines, is lost in the middle of the frame. As set, the cord's
#: image never comes closer than 95 px to the principal point. Downwards is
#: also the direction gravity will bow the real one in the studio.
#:
#: Mode 2 in z is what makes it read as a wave rather than a bow. With modes
#: 1 and 3 alone the shape is monotone down and back up, which from the side
#: is a sag; mode 2 breaks the symmetry and puts an inflection in the frame.
WAVE = dict(x=(0.0, 0.35), z=(-0.55, 0.30, 0.20))

ROOM_ALBEDO = 0.02


def candela_to_watts(cd):
    """A Lambertian emitter of on-axis intensity I0 has flux pi*I0."""
    return math.pi * cd / LER


def exposure_for(illuminance_lx):
    """Stop offset putting a white Lambertian surface at that level at 1.0."""
    return -math.log2((illuminance_lx / LER) / math.pi)


def projected_width_px(focal_mm, distance_m, diameter_mm=1.0, pixel_um=1.55):
    return (focal_mm / (pixel_um * 1e-3)) * (diameter_mm / 1000.0) / distance_m


def hfov_deg(focal_mm, sensor_w_mm=SENSOR["width_mm"]):
    return 2.0 * math.degrees(math.atan(sensor_w_mm / 2.0 / focal_mm))


def _mode_sum(t, amps):
    """Pinned-string modes at parameter ``t`` in [0, 1]."""
    return sum(a * math.sin((k + 1) * math.pi * t)
               for k, a in enumerate(amps) if a)


def cord_points(x, z, y0, y1, segments=512, x_far=None, z_far=None,
                sag=0.0, wave=None):
    """The cord as a polyline, in metres.

    Separated from ``build_tether`` because the mesh is not the only thing
    that needs it: solving for the lamp intensity asks how dark the dimmest
    point of the cord is, and with a wave the cord's height above the floor
    is no longer one number. Answering that against a straight line while
    rendering a wavy cord sets every lamp from a geometry that is not in the
    frame, and 0.33 m of excursion under a row 2 m up is a factor of 1.6 in
    illuminance, not a rounding error.
    """
    x_far = x if x_far is None else x_far
    z_far = z if z_far is None else z_far
    wx = (wave or {}).get("x", ())
    wz = (wave or {}).get("z", ())
    pts = []
    for i in range(segments):
        t = i / (segments - 1)
        pts.append((x + t * (x_far - x) + _mode_sum(t, wx),
                    y0 + t * (y1 - y0),
                    z + t * (z_far - z) - sag * math.sin(math.pi * t)
                    + _mode_sum(t, wz)))
    return pts


# --------------------------------------------------------------- scene build

def _clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.lights, bpy.data.cameras,
                  bpy.data.materials, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def _matte(name, albedo):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (albedo, albedo, albedo, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.0
    return mat


def build_room(depth, width, height):
    """Inward-facing box, origin on the floor at the camera end, X centred.

    Unlike the orbital scene the walls **do** occlude here. There the Sun was
    infinitely distant, so a sealed box stopped every ray and the first render
    came out uniformly black; the fix was to turn off the box's shadow
    visibility. Here the lamps hang inside the box, so that fix would be
    wrong: it would let their light leak out through the walls and kill the
    very reflections and falloff the studio case exists to reproduce.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    room = bpy.context.active_object
    room.name = "Room"
    room.scale = (width, depth, height)
    room.location = (0.0, depth / 2.0, height / 2.0)
    bpy.ops.object.transform_apply(scale=True, location=True)

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode="OBJECT")

    room.data.materials.append(_matte("RoomBlack", ROOM_ALBEDO))
    return room


def _build_world(stars=False):
    """Black sky, with or without stars.

    The stars have to be sparse, and "looks sparse" is not good enough: the
    first attempt used a threshold of 0.72 at strength 600 because it looked
    like a starfield, and measured, **98.9% of the frame came out above 2
    levels** and the frame mean went from 0.257 to 52.5. That is not a
    backdrop, it is a mottled sky acting as ambient light from every
    direction, which is the one thing space does not have, and it lifted the
    cord in its dimmest stretches by a factor of seven.

    Swept at 20% scale, frame mean against the starless scene's 0.257:

        threshold 0.72, strength 600  ->  52.508,  98.9% of pixels over 2
        threshold 0.84, strength 400  ->   1.490,   5.3%
        threshold 0.90, strength 400  ->   0.310,   0.8%
        threshold 0.94, strength 500  ->   0.260,   0.3%   <- adopted
        no stars                      ->   0.257,   0.2%

    So the adopted pair adds 1% to the frame mean and nothing measurable to
    the cord. Anything looser is lighting the scene. Re-measure after
    touching either number.
    """
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("Space")
        bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    if bg is None:
        return world
    if not stars:
        bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        bg.inputs["Strength"].default_value = 0.0
        return world

    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 900.0
    noise.inputs["Detail"].default_value = 0.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    ramp.color_ramp.elements[1].position = 0.94
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    # Strength is what gets a single star above the floor after the -8.76
    # stops of AM0 exposure: 2**8.76 is 433, so a point needs that order of
    # magnitude to register at all. The threshold is what keeps the rest of
    # the sky at exact zero, and it is the number that was measured, not
    # eyeballed.
    bg.inputs["Strength"].default_value = 500.0
    return world


def build_sun(tilt_deg=40.0, tilt_dir="-y", irradiance=1361.0,
              temperature=5772.0, angular_diameter_deg=0.526, stars=False):
    """The orbital case: one Sun, and a world that emits nothing.

    Every default here is a number from the illumination deliverable rather
    than a Blender default, and three of them are the ones most often left
    wrong:

    * ``irradiance`` is AM0, 1361 W/m2, and a Blender Sun takes W/m2 directly
      with no conversion. The common error is the ground-level figure of
      about 1050, which almost every tutorial assumes. The other error, found
      in this project's own ``Simulation camera_64MP.blend``, is a Sun left
      at 3.0 W/m2 with the exposure slider opened to compensate: the picture
      then looks right and the file's numbers are 454 times off.
    * ``angular_diameter_deg`` is 0.526, the real angular size of the Sun from
      Earth orbit. It is what makes the shadow edges as hard as they are in
      space, and it is the parameter most often left at whatever the file came
      with. Blender's ``angle`` is this diameter, in radians.
    * ``temperature`` is 5772 K, the Sun's effective blackbody temperature.

    The world is forced to emit nothing. Blender ships a grey world that acts
    as uniform ambient light from every direction, which is the one thing
    space does not have, and inside the studio it goes unnoticed only because
    the room encloses the scene.

    ``tilt_deg`` and ``tilt_dir`` match ``build_lamp_row`` on purpose, so the
    orbital and studio scenes can be rendered with the beam arriving from the
    same direction. That leaves the lighting model as the only difference
    between them: parallel and unattenuated here, divergent and falling off
    as 1/r2 there.
    """
    _build_world(stars=stars)

    t = math.radians(tilt_deg)
    if tilt_dir == "-y":
        rot = (-t, 0.0, 0.0)
    elif tilt_dir == "+y":
        rot = (t, 0.0, 0.0)
    elif tilt_dir == "+x":
        rot = (0.0, -t, 0.0)
    elif tilt_dir == "-x":
        rot = (0.0, t, 0.0)
    else:
        raise ValueError(f"tilt_dir {tilt_dir!r}")

    data = bpy.data.lights.new("Sun", type="SUN")
    data.energy = irradiance
    data.angle = math.radians(angular_diameter_deg)
    data.use_nodes = True
    nt = data.node_tree
    bb = nt.nodes.new("ShaderNodeBlackbody")
    bb.inputs["Temperature"].default_value = temperature
    nt.links.new(bb.outputs["Color"], nt.nodes["Emission"].inputs["Color"])

    obj = bpy.data.objects.new("Sun", data)
    # A Sun has no position, only a direction, but it still needs somewhere
    # to sit in the outliner.
    obj.location = (0.0, 0.0, 10.0)
    obj.rotation_euler = Euler(rot, "XYZ")
    bpy.context.collection.objects.link(obj)
    return obj


def build_tether(x, z, y0, y1, diameter_mm, sag=0.0, segments=512,
                 x_far=None, z_far=None, wave=None):
    """The cord, from (x, y0, z) near the rig to (x_far, y1, z_far) at the back.

    ``x_far``/``z_far`` default to the near values, which is the taut cord the
    studio will actually string. They exist because of what the axis view
    does to a cord that is exactly on the optical axis: it collapses.

    Looking down the cord, the image of a straight cord is the segment
    between its near end and its vanishing point, and the vanishing point of
    a cord parallel to the optical axis is the principal point. So the whole
    length, 30 m or 30 km, lands inside ``fx * off / d_near`` pixels of the
    centre, where ``off`` is how far the near end sits off the axis and
    ``d_near`` how far ahead it starts. Anchored at the baseline midpoint
    0.5 m ahead of an 8 mm camera that is 516 px, and the frame is 4056 wide:
    the cord reads as a short stick floating in the middle, which is not a
    rendering fault but the projection. Moving the anchor sideways on the rig
    is what makes it sweep the frame, because it raises ``off`` without
    touching anything else.

    ``wave`` bends it. Pass ``WAVE`` for the shape a tether actually holds;
    ``None`` leaves it dead straight, which is what the earlier variants
    measured and is kept so those numbers stay reproducible.
    """
    pts = cord_points(x, z, y0, y1, segments, x_far, z_far, sag, wave)
    curve = bpy.data.curves.new("TetherCurve", type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 4
    spline = curve.splines.new("POLY")
    spline.points.add(segments - 1)
    for i, (px, py, pz) in enumerate(pts):
        spline.points[i].co = (px, py, pz, 1.0)
    curve.bevel_depth = (diameter_mm / 1000.0) / 2.0
    curve.bevel_resolution = 4

    obj = bpy.data.objects.new("Tether", curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(_matte("CordWhite", TETHER["albedo"]))
    return obj


def build_lamp_row(x, z, y0, y1, count, candela, size=1.0, spread_deg=180.0,
                   visible_to_camera=False, tilt_deg=0.0, tilt_dir="+y",
                   over=0.0):
    """A row of identical rectangles, every one aimed the same way.

    All parallel, never converging. Two converging beams put two specular
    lines on a 1 px target, which is a duplicated cord and a failure mode the
    stereo matching stage is not built for; the illumination deliverable
    forbids the arrangement outright.

    ``tilt_deg`` leans every beam instead of pointing it straight down, and
    it is not cosmetic. The cord is a cylinder, so a beam from directly
    overhead puts the lit band on **top** of it while the cameras look at its
    side. ``over`` is the lamps' height above the cord, which is what sets
    how far upstream of it each lamp has to sit for its beam to land on it.

    ``tilt_dir`` is the direction the **beam travels**, and getting it
    backwards is easy: to light the face a camera can see, the lamp has to
    stand on the camera's side of the cord and throw across it, so a camera
    at -X wants ``+x`` and not ``-x``. The opposite choice lights the far
    face and leaves the camera looking at the shadowed one.
    """
    watts = candela_to_watts(candela)
    t = math.radians(tilt_deg)
    shift = over * math.tan(t)
    sx = sy = 0.0
    rot = (0.0, 0.0, 0.0)
    if tilt_dir == "+y":
        sy, rot = -shift, (t, 0.0, 0.0)
    elif tilt_dir == "-y":
        sy, rot = +shift, (-t, 0.0, 0.0)
    elif tilt_dir == "+x":
        sx, rot = -shift, (0.0, -t, 0.0)
    elif tilt_dir == "-x":
        sx, rot = +shift, (0.0, t, 0.0)

    # A tilted lamp sits upstream of the cord, and upstream can be outside the
    # room. That failed silently and cost a pair of renders: with the cord
    # 0.5 m off the side wall and the beam leaning 40 degrees, every lamp
    # landed at x = 8.68 against a wall at 7.5, the wall absorbed all of it
    # and both frames came back black with a maximum pixel value of 2. A black
    # frame looks like a dark room working, so it has to be an error.
    hw, depth, height = ROOM["width_m"] / 2.0, ROOM["depth_m"], ROOM["height_m"]
    for probe in (x + sx, ):
        if not -hw < probe < hw:
            raise ValueError(
                f"lamp x={probe:.2f} is outside the room (walls at +-{hw:.2f}). "
                f"A {tilt_deg:.0f} degree tilt pushes each lamp "
                f"{shift:.2f} m upstream; move the cord away from the wall.")
    for probe in (y0 + sy, y1 + sy):
        if not 0.0 < probe < depth:
            raise ValueError(
                f"lamp y={probe:.2f} is outside the room (0 to {depth:.2f}).")
    if not 0.0 < z < height:
        raise ValueError(f"lamp z={z:.2f} is outside the room "
                         f"(0 to {height:.2f}).")

    lamps = []
    for i in range(count):
        y = y0 if count == 1 else y0 + (y1 - y0) * i / (count - 1)
        data = bpy.data.lights.new(f"Lamp_{i:02d}", type="AREA")
        data.shape = "RECTANGLE"
        data.size = size
        data.size_y = size
        data.energy = watts
        data.spread = math.radians(spread_deg)
        data.use_nodes = True
        nt = data.node_tree
        bb = nt.nodes.new("ShaderNodeBlackbody")
        bb.inputs["Temperature"].default_value = 5600.0
        nt.links.new(bb.outputs["Color"], nt.nodes["Emission"].inputs["Color"])

        obj = bpy.data.objects.new(data.name, data)
        obj.location = (x + sx, y + sy, z)   # an AREA light emits along -Z
        obj.rotation_euler = Euler(rot, "XYZ")
        bpy.context.collection.objects.link(obj)
        obj.visible_camera = visible_to_camera
        lamps.append(obj)
    return lamps


def build_stereo_pair(focal_mm, baseline_mm, z, mode, cord_x, cord_y_mid,
                      cam_offset):
    """Two cameras. ``mode`` is "axis" (down the cord) or "side" (across it).

    **The baseline must not run parallel to the cord**, and which direction
    that is depends on the mode. A cord is a line with no texture along it,
    so when the baseline is parallel to it every point on the left cord lies
    on the epipolar line of every point on the right one and the match is
    undetermined: the stage would return disparities, all of them arbitrary.

    Looking down the cord, the cord runs along Y and a baseline across X is
    already perpendicular. Looking at it from the side the cord still runs
    along Y, so the horizontal baseline that a stereo rig uses by habit is
    the wrong one and the pair is stacked **vertically** instead. That is a
    real constraint on the rig for the studio session, not a detail of the
    render: a side-on view of a cord wants one camera above the other.

    In side mode the names stay Cam_L and Cam_R so the rest of the pipeline
    reads the pair unchanged, but Cam_L is the **lower** camera and the
    disparity is vertical. Measured on the 2.6 mm render at 12 m, it is
    13.88 px against the 13.98 the geometry predicts, scattering 0.057 px
    over the whole 29 m of cord.
    """
    half = (baseline_mm / 1000.0) / 2.0
    cams = []
    for name, s in (("Cam_L", -1.0), ("Cam_R", +1.0)):
        data = bpy.data.cameras.new(name)
        data.type = "PERSP"
        data.lens = focal_mm
        data.sensor_fit = "HORIZONTAL"
        data.sensor_width = SENSOR["width_mm"]
        data.clip_start = 0.05
        data.clip_end = 300.0
        obj = bpy.data.objects.new(name, data)
        if mode == "axis":
            # cord along Y, baseline along X: perpendicular, as it should be
            obj.location = (cord_x + s * half, cam_offset, z)
            obj.rotation_euler = Euler((math.radians(90.0), 0.0, 0.0), "XYZ")
        else:
            # cord along Y, so the baseline goes along Z, not along Y
            obj.location = (cam_offset, cord_y_mid, z + s * half)
            obj.rotation_euler = Euler(
                (math.radians(90.0), 0.0, math.radians(-90.0)), "XYZ")
        bpy.context.collection.objects.link(obj)
        cams.append(obj)
    return cams


def configure_render(samples, exposure, scale=100):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = SENSOR["width_px"]
    scene.render.resolution_y = SENSOR["height_px"]
    scene.render.resolution_percentage = scale
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = exposure
    try:
        scene.cycles.device = "CPU"
    except Exception:
        pass
    return scene


# --------------------------------------------------------------- driver

def build(args):
    _clear()
    build_room(ROOM["depth_m"], ROOM["width_m"], ROOM["height_m"])

    cord_x = args.cord_x
    cord_z = TETHER["z_m"]
    build_tether(cord_x, cord_z, args.cord_y0, args.cord_y1,
                 TETHER["diameter_mm"], sag=args.sag)

    build_lamp_row(cord_x, cord_z + args.lamp_h,
                   args.lamp_y0, args.lamp_y1, args.lamps,
                   args.candela, spread_deg=args.spread)

    mid = (args.cord_y0 + args.cord_y1) / 2.0
    build_stereo_pair(args.focal, OPTICS["baseline_mm"], cord_z,
                      args.view, cord_x, mid, args.cam_offset)

    exposure = args.exposure if args.exposure is not None else \
        exposure_for(E_TARGET_LX)
    configure_render(args.samples, exposure, args.scale)
    return exposure


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--cord-x", type=float, default=0.0)
    ap.add_argument("--cord-y0", type=float, default=0.5)
    ap.add_argument("--cord-y1", type=float, default=29.5)
    ap.add_argument("--sag", type=float, default=0.0)
    ap.add_argument("--lamps", type=int, default=12)
    ap.add_argument("--lamp-h", type=float, default=2.0)
    ap.add_argument("--lamp-y0", type=float, default=0.5)
    ap.add_argument("--lamp-y1", type=float, default=29.5)
    ap.add_argument("--candela", type=float, default=5600.0)
    ap.add_argument("--spread", type=float, default=180.0)
    ap.add_argument("--view", choices=("axis", "side"), default="axis")
    ap.add_argument("--cam-offset", type=float, default=0.2,
                    help="axis: camera y. side: camera x")
    ap.add_argument("--focal", type=float, default=OPTICS["focal_mm"])
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--exposure", type=float, default=None)
    args = ap.parse_args(argv)

    exposure = build(args)
    print(f"[build] exposure {exposure:.3f} stops, "
          f"{args.lamps} lamps at {args.candela:.0f} cd "
          f"({candela_to_watts(args.candela):.0f} W each)")
    if args.out:
        path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print(f"[build] wrote {path}")


if bpy is not None and __name__ == "__main__":
    main()

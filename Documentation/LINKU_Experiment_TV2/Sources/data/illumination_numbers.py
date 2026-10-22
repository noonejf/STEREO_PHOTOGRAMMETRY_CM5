"""
Reproduces every derived number in the LINKU dark-room illumination report.

All inputs are either primary data files stored next to this script, or
manufacturer/standard constants declared in CONSTANTS below with their source.
No number in the report is entered by hand: each one is printed here.

Data files:
  astm_e490_00a_am0.dat  ASTM E490-00a AM0 spectrum (microns, W/m2/micron),
                         mirror of the NREL file kept in pytroll/pyspectral
  CIE_sle_photopic.csv   CIE photopic V(lambda), 1 nm steps (CIE 018:2019 Table 1)

Run: python illumination_numbers.py
"""
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# --- Constants, with the source each one comes from ------------------------
KM = 683.0            # lm/W, luminous efficacy at 555 nm, SI definition of the candela
TSI = 1361.0          # W/m2, nominal solar constant, IAU 2015 Resolution B3
R_SUN = 695_700.0     # km, nominal solar radius, IAU 2015 Resolution B3
T_SUN = 5772.0        # K, nominal solar effective temperature, IAU 2015 Resolution B3
AU = 149_597_870.7    # km, astronomical unit, IAU 2012 Resolution B2

# Sony IMX477-AACK-C datasheet, sections 10-1 and 11-3/11-4
IMX477_S = 250.0      # LSB, sensitivity, standard imaging condition I
IMX477_VSAT = 1023.0  # LSB, saturation signal (includes optical-black level)
IMX477_OB = 64.0      # LSB, recommended optical-black level
IMX477_L = 706.0      # cd/m2, pattern-box luminance of the test condition
IMX477_T = 1 / 120    # s, storage time of the test condition
IMX477_N = 2.8        # f-number of the test condition

# (pixel pitch um, h pixels, focal mm, f-number, shutter). The active sensor
# width is derived as pitch x resolution so that every geometric quantity rests
# on the same two published numbers.
#
# Sensors: IMX477 and IMX296 pitch and resolution from the Raspberry Pi camera
# documentation; Hawk-eye from the Arducam 64MP Hawkeye wiki.
#
# Lenses, all three C/CS-mount units owned by the project:
#   8 mm F1.6-F16   Arducam C1508ZM04, SKU LN043, C-mount, MOD 0.15 m.
#                   THE LENS CURRENTLY FITTED TO THE IMX477 STEREO PAIR
#                   (LINKU D5 Camera System Report, ch. 5).
#   6 mm F1.2       Raspberry Pi recommended CS-mount wide angle, MOD 0.2 m.
#                   Shipped with the HQ camera; retained by the project.
#   16 mm F1.4-F16  PT3611614M10MP / SEN-16761 telephoto, C-mount, MOD 0.2 m.
#                   Quoted with the IMX296; previously excluded by project
#                   decision, kept here for comparison only.
# Adjustable lenses are evaluated wide open, which is the best case for light.
# The Hawk-eye is a sealed module with an integrated 5.1 mm F1.8 optic and
# cannot take any of the three.
CAMERAS = {
    "IMX477 + 8 mm F1.6 (fitted)":    (1.55, 4056, 8.0, 1.6, "rolling"),
    "IMX477 + 6 mm F1.2":             (1.55, 4056, 6.0, 1.2, "rolling"),
    "IMX296 + 16 mm F1.4":            (3.45, 1456, 16.0, 1.4, "global"),
    "IMX296 + 8 mm F1.6":             (3.45, 1456, 8.0, 1.6, "global"),
    "IMX296 + 6 mm F1.2":             (3.45, 1456, 6.0, 1.2, "global"),
    "Hawk-eye + 5.1 mm F1.8 (fixed)": (0.80, 9152, 5.1, 1.8, "rolling"),
}

WORKING_DISTANCE_M = 3.5   # stereo pair to tether, Blender replica of the enclosure
TETHER_MM = 1.0            # default tether diameter in camera_dof_visualizer.py
OMEGAS = (1.0, 2.76)       # deg/s, the two bounds of the rolling-shutter deliverable
RHO_WHITE = 0.9            # reflectance of a white card


def rule(title):
    print("\n" + title)
    print("-" * len(title))


def trapezoid(y, x):
    return float(np.sum((y[1:] + y[:-1]) * np.diff(x)) / 2.0)


# --- 1. Photometry of the orbital Sun --------------------------------------
def photometry():
    rule("1. Orbital Sun, radiometry to photometry")
    d = np.loadtxt(HERE / "astm_e490_00a_am0.dat", comments="#")
    wl = d[:, 0] * 1000.0          # nm
    e = d[:, 1] / 1000.0           # W/m2/nm
    v = np.loadtxt(HERE / "CIE_sle_photopic.csv", delimiter=",")
    vv = np.interp(wl, v[:, 0], v[:, 1], left=0.0, right=0.0)

    total = trapezoid(e, wl)
    lux_e490 = KM * trapezoid(e * vv, wl)
    efficacy = lux_e490 / total
    lux = efficacy * TSI
    print(f"  E490 integrated irradiance      Ee = {total:9.1f} W/m2")
    print(f"  E490 integrated illuminance     Ev = {lux_e490:9.0f} lx")
    print(f"  luminous efficacy of AM0 light  K  = {efficacy:9.2f} lm/W")
    print(f"  at the IAU nominal constant     Ev = {lux:9.0f} lx  (<- report value)")
    for a, b, label in [(400, 700, "visible"), (400, 1100, "IEC restricted"),
                        (300, 1200, "IEC extended")]:
        m = (wl >= a) & (wl <= b)
        print(f"  share {a}-{b} nm ({label:>14s}) : {100 * trapezoid(e[m], wl[m]) / total:5.1f} %")
    return lux


# --- 2. Angular size and shadow geometry -----------------------------------
def geometry():
    rule("2. Angular size and penumbra")
    full = 2 * math.degrees(math.atan(R_SUN / AU))
    print(f"  Sun angular diameter at 1 au    alpha = {full:.3f} deg")
    print("  penumbra width w = L*tan(alpha), per metre of L:")
    for ang, who in ((full, "real Sun"), (1.0, "1 deg source"),
                     (1.9, "ESA LSS beam"), (2.0, "LINKU limit"), (5.0, "5 deg source")):
        print(f"    alpha = {ang:4.2f} deg ({who:13s}) -> {1000 * math.tan(math.radians(ang)):5.1f} mm/m")
    return full


# --- 3. Inverse-square falloff across the working volume -------------------
def falloff():
    rule("3. Uncollimated source: falloff across object depth")
    print("  non-uniformity NU = (Emax-Emin)/(Emax+Emin), IEC 60904-9 definition")
    print("  minimum throw D for a target NU, as a multiple of object depth dz:")
    for nu, cls in ((0.02, "A"), (0.05, "B"), (0.10, "C")):
        r = math.sqrt((1 - nu) / (1 + nu))
        print(f"    NU <= {100 * nu:4.0f} % (class {cls}) -> D >= {r / (1 - r):5.1f} * dz")
    print("  NU produced by a given throw and depth:")
    for d, dz in ((3, 0.5), (5, 0.5), (10, 0.5), (5, 1.0), (10, 1.0)):
        r = (d / (d + dz)) ** 2
        print(f"    D = {d:2d} m, dz = {dz:3.1f} m -> Emin/Emax = {r:.3f}, NU = {100 * (1 - r) / (1 + r):5.1f} %")


# --- 4. Exposure arithmetic -------------------------------------------------
def stops(sun_lux):
    rule("4. Stops below the orbital Sun")
    for lx in (132_800, 50_000, 20_000, 10_000, 5_000, 1_000):
        s = math.log2(sun_lux / lx)
        print(f"    {lx:7d} lx -> {s:4.2f} stops below the Sun, exposure x{2 ** s:6.1f}")
    print("  IEC non-uniformity classes expressed in stops (max-to-min spread):")
    for nu, cls in ((0.01, "A+"), (0.02, "A"), (0.05, "B"), (0.10, "C")):
        print(f"    class {cls:2s}: NU = {100 * nu:4.0f} % -> {math.log2((1 + nu) / (1 - nu)):.3f} EV")


# --- 5. Saturation exposure of the IMX477, from its datasheet ---------------
def saturation_exposure(n_lens):
    """H_sat in lx*s on a Lambertian white card, for a given f-number."""
    headroom = (IMX477_VSAT - IMX477_OB) / IMX477_S       # dimensionless
    lt_28 = headroom * IMX477_L * IMX477_T                # cd*s/m2 at F2.8
    lt = lt_28 * (n_lens / IMX477_N) ** 2                 # cd*s/m2 at the lens in use
    return math.pi * lt / RHO_WHITE, headroom, lt_28, lt


def datasheet_anchor():
    rule("5. IMX477 saturation exposure, from the Sony datasheet")
    h12, headroom, lt28, lt12 = saturation_exposure(1.2)
    print(f"  usable range / sensitivity      = ({IMX477_VSAT:.0f}-{IMX477_OB:.0f})/{IMX477_S:.0f} = {headroom:.3f}")
    print(f"  saturation at F2.8  (L*t)_sat   = {lt28:6.2f} cd s/m2")
    print(f"  saturation at F1.2  (L*t)_sat   = {lt12:6.2f} cd s/m2")
    print(f"  on a rho={RHO_WHITE} white card   H_sat = {h12:6.2f} lx s")
    print(f"  the orbital Sun saturates it in   {1000 * h12 / 132_824:.2f} ms")
    return h12


# --- 6. Per-camera requirement ---------------------------------------------
def cameras(sun_lux):
    rule("6. Per-camera exposure limit and light requirement")
    print(f"  IFOV = p/f ; t_max = blur*IFOV/omega ; E_min = H_sat(N)/t_max")
    print(f"  working distance {WORKING_DISTANCE_M} m, tether {TETHER_MM} mm, blur 1 px\n")
    hdr = (f"  {'configuration':32s} {'width mm':>8s} {'IFOV deg':>9s} {'FOV H deg':>9s} "
           f"{'GSD mm':>7s} {'px/teth':>8s}")
    for w in OMEGAS:
        hdr += f" {'t@' + str(w):>8s}"
    hdr += f" {'E@1deg/s':>9s}"
    print(hdr)
    rows = {}
    for name, (p_um, nh, f_mm, n, shutter) in CAMERAS.items():
        sw = p_um * 1e-3 * nh                                   # active width, mm
        ifov = (p_um * 1e-3) / f_mm                             # rad
        fov = 2 * math.degrees(math.atan(sw / 2 / f_mm))        # deg
        gsd = p_um * 1e-3 * (WORKING_DISTANCE_M * 1000.0) / f_mm   # mm per pixel
        px = TETHER_MM / gsd
        h_sat, *_ = saturation_exposure(n)
        line = (f"  {name:32s} {sw:8.3f} {math.degrees(ifov):9.4f} {fov:9.1f} "
                f"{gsd:7.3f} {px:8.2f}")
        ts = []
        for w in OMEGAS:
            t = ifov / math.radians(w)
            ts.append(t)
            line += f" {1000 * t:7.1f}m"
        e_min = h_sat / ts[0]
        line += f" {e_min:8.0f}"
        print(line)
        rows[name] = dict(ifov=ifov, fov=fov, gsd=gsd, px=px, t=ts, e=e_min,
                          h_sat=h_sat, shutter=shutter, n=n)
    print("\n  Light requirement at each rotation rate (lx):")
    for name, r in rows.items():
        vals = "  ".join(f"{r['h_sat'] / t:7.0f} lx @ {w:g} deg/s" for t, w in zip(r["t"], OMEGAS))
        print(f"    {name:32s} {vals}")
    print("\n  Relative to the fitted IMX477 + 8 mm (same rate):")
    ref = rows["IMX477 + 8 mm F1.6 (fitted)"]["e"]
    for name, r in rows.items():
        print(f"    {name:32s} x{r['e'] / ref:4.2f} ({math.log2(r['e'] / ref):+.1f} stops)")
    return rows


# --- 7. Flicker -------------------------------------------------------------
def flicker(rows):
    rule("7. Flicker periods vs exposure limits")
    for f_grid in (50, 60):
        print(f"    {f_grid} Hz grid -> luminous flicker at {2 * f_grid} Hz, period "
              f"{1000 / (2 * f_grid):.1f} ms")
    for f_src, label in ((75, "ARRI flicker-free mode"), (1000, "ARRI high-speed mode")):
        print(f"    {label:24s} {f_src} Hz square wave -> period {1000 / f_src:.2f} ms")
    print("\n  exposure limits for comparison (ms):")
    for name, r in rows.items():
        print(f"    {name:32s} " + ", ".join(f"{1000 * t:5.1f} @ {w:g} deg/s"
                                             for t, w in zip(r["t"], OMEGAS)))


if __name__ == "__main__":
    sun = photometry()
    geometry()
    falloff()
    stops(sun)
    datasheet_anchor()
    rows = cameras(sun)
    flicker(rows)

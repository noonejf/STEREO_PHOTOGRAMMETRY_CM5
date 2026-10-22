"""
Generates the data-driven figures of the dark-room illumination report.

Outputs (vector PDF, written into ../../Images/):
  fig_spectrum_vlambda.pdf   AM0 spectral irradiance, CIE V(lambda), and their
                             product: the part of sunlight that becomes lux.
  fig_camera_requirement.pdf Required illuminance vs angular rate, per camera.

Run: python make_figures.py
"""
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from illumination_numbers import (CAMERAS, KM, TSI, OMEGAS, saturation_exposure,
                                  trapezoid)

HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / "Images"
OUT.mkdir(exist_ok=True)

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.linewidth": 0.6,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "legend.frameon": False,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
})


def spectrum_figure():
    d = np.loadtxt(HERE / "astm_e490_00a_am0.dat", comments="#")
    wl = d[:, 0] * 1000.0        # nm
    e = d[:, 1] / 1000.0         # W/m2/nm
    v = np.loadtxt(HERE / "CIE_sle_photopic.csv", delimiter=",")
    vv = np.interp(wl, v[:, 0], v[:, 1], left=0.0, right=0.0)

    m = (wl >= 250) & (wl <= 1400)
    total = trapezoid(e, wl)
    scale = TSI / total                       # renormalise E490 to the IAU constant
    lux = KM * trapezoid(e * vv, wl) * scale

    fig, ax = plt.subplots(figsize=(6.2, 3.3))
    ax.axvspan(400, 700, color="0.93", zorder=0)
    ax.plot(wl[m], e[m] * scale, color="0.15", lw=1.0,
            label=r"AM0 spectral irradiance $E_{e,\lambda}$")
    ax.fill_between(wl[m], 0, e[m] * vv[m] * scale, color="0.55", alpha=0.65, lw=0,
                    label=r"product $E_{e,\lambda}\,V(\lambda)$: the integrand of $E_v$")
    ax.set_xlabel(r"wavelength $\lambda$  [nm]")
    ax.set_ylabel(r"spectral irradiance  [W m$^{-2}$ nm$^{-1}$]")
    ax.set_xlim(250, 1400)
    ax.set_ylim(0, 2.8)

    ax2 = ax.twinx()
    ax2.plot(wl[m], vv[m], color="0.15", lw=1.0, ls="--",
             label=r"CIE photopic $V(\lambda)$, right axis")
    ax2.set_ylabel(r"$V(\lambda)$  [-]")
    ax2.set_ylim(0, 1.35)
    ax2.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax2.tick_params(direction="in")

    ax.annotate("visible band 400-700 nm: 38.6 % of the AM0 energy",
                xy=(550, 2.62), ha="center", va="center", fontsize=8, color="0.25")
    ax.text(0.985, 0.63,
            rf"$E_e = {TSI:.0f}$ W m$^{{-2}}$" "\n"
            rf"$E_v = {lux / 1000:.1f}$ klx" "\n"
            rf"$K = {lux / TSI:.1f}$ lm W$^{{-1}}$",
            transform=ax.transAxes, ha="right", va="top", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="0.7", lw=0.5))

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, -0.22),
              ncol=2, fontsize=8)
    fig.savefig(OUT / "fig_spectrum_vlambda.pdf")
    plt.close(fig)
    print(f"wrote fig_spectrum_vlambda.pdf  (Ev = {lux:.0f} lx, K = {lux / TSI:.2f} lm/W)")


def requirement_figure():
    """Required illuminance vs angular rate, one curve per configuration.

    Curves are labelled at their right-hand end rather than in a legend,
    because six overlapping curves make a legend hard to match up.
    """
    omega = np.linspace(0.2, 3.0, 300)
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    ends = []
    for name, (p_um, nh, f_mm, n, shutter) in CAMERAS.items():
        ifov = (p_um * 1e-3) / f_mm
        h_sat, *_ = saturation_exposure(n)
        e_min = h_sat / (ifov / np.radians(omega))
        fitted = "fitted" in name
        ax.plot(omega, e_min, ls="-" if fitted else "--", color="0.1" if fitted else "0.45",
                lw=1.5 if fitted else 1.0)
        for w in OMEGAS:
            ax.plot([w], [h_sat / (ifov / math.radians(w))], "o", ms=3.0,
                    color="0.1" if fitted else "0.45")
        ends.append((e_min[-1], name.replace(" (fixed)", "").replace(" (fitted)", ""), fitted))
    # label each curve at its right end, nudged apart where they would collide
    ends.sort()
    prev = 0.0
    for val, name, fitted in ends:
        y = max(val, prev * 1.22)
        prev = y
        ax.annotate(name + (" [fitted]" if fitted else ""), xy=(3.0, val),
                    xytext=(3.08, y), fontsize=7.5,
                    color="0.1" if fitted else "0.35",
                    fontweight="bold" if fitted else "normal",
                    va="center", ha="left",
                    arrowprops=dict(arrowstyle="-", lw=0.4, color="0.6",
                                    shrinkA=0, shrinkB=0))
    for w, lab in zip(OMEGAS, [r"$1^\circ$/s", r"$2.76^\circ$/s"]):
        ax.axvline(w, color="0.45", lw=0.7, ls=":", zorder=3)
        ax.text(w, 1.02, lab, transform=ax.get_xaxis_transform(), ha="center",
                va="bottom", fontsize=8, color="0.35")
    ax.set_xlabel(r"angular rate $\omega$  [deg/s]")
    ax.set_ylabel(r"illuminance to saturate a white card  $E_{\min}$  [lx]")
    ax.set_xlim(0.2, 3.0)
    ax.set_yscale("log")
    ax.set_ylim(100, 2e4)
    ax.grid(True, which="both", lw=0.4, color="0.9")
    ax.set_axisbelow(True)
    fig.savefig(OUT / "fig_camera_requirement.pdf")
    plt.close(fig)
    print("wrote fig_camera_requirement.pdf")


def flicker_figure(f_grid=50.0, t_exp=4.0e-3, t_frame=25e-3, n_rows=3040):
    """Banding produced by an AC-powered lamp on a rolling-shutter sensor.

    Lamp output is modelled as L(t) = sin^2(2*pi*f_grid*t), the standard
    rectified behaviour of a source driven from an AC supply: luminous output
    peaks twice per electrical cycle, so it varies at 2*f_grid.
    A rolling shutter starts row k at t_k = k*t_frame/n_rows and integrates
    for t_exp, so each row collects a different part of that waveform.
    """
    t_row = t_frame / n_rows
    rows = np.arange(n_rows)
    t0 = rows * t_row

    # analytic integral of sin^2(2 pi f t) over [t0, t0+t_exp]
    w = 2 * np.pi * f_grid
    def integ(a, b):
        return 0.5 * (b - a) - (np.sin(2 * w * b) - np.sin(2 * w * a)) / (4 * w)
    sig = integ(t0, t0 + t_exp)
    sig_n = sig / sig.max()
    contrast = (sig.max() - sig.min()) / (sig.max() + sig.min())

    fig = plt.figure(figsize=(6.4, 2.9))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.55, 1.0, 0.34], wspace=0.46)

    # (a) lamp waveform with two exposure windows
    ax = fig.add_subplot(gs[0, 0])
    tt = np.linspace(0, t_frame, 2000)
    ax.plot(tt * 1e3, np.sin(w * tt) ** 2, color="0.15", lw=1.0)
    # the brightest and the darkest window of this duration: centred on a peak
    # of the waveform, and centred on a trough
    t_peak = 0.25 / f_grid
    t_trough = 0.5 / f_grid
    wins = [(t_peak - t_exp / 2, "brightest row", dict(facecolor="0.72", edgecolor="0.3")),
            (t_trough - t_exp / 2, "darkest row", dict(facecolor="none", edgecolor="0.3",
                                                       hatch="////"))]
    for i, (start, lab, style) in enumerate(wins):
        sel = (tt >= start) & (tt <= start + t_exp)
        ax.fill_between(tt[sel] * 1e3, 0, np.sin(w * tt[sel]) ** 2, lw=0.6, **style)
        frac = integ(start, start + t_exp) / sig.max()
        ax.annotate(f"{lab}, {100 * frac:.0f} %",
                    xy=((start + t_exp / 2) * 1e3, 0.04),
                    xytext=(0.52, [-0.24, -0.47][i]),
                    textcoords=("axes fraction", "data"),
                    ha="left", va="center", fontsize=7, color="0.2",
                    arrowprops=dict(arrowstyle="-", lw=0.5, color="0.5",
                                    shrinkA=1, shrinkB=1))
    ax.set_xlabel("time  [ms]")
    ax.set_ylabel("relative lamp output")
    ax.set_xlim(0, t_frame * 1e3)
    ax.set_ylim(-0.62, 1.08)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.spines["bottom"].set_bounds(0, t_frame * 1e3)
    ax.set_title(f"(a) lamp on a {f_grid:.0f} Hz supply, output period "
                 f"{1e3 / (2 * f_grid):.0f} ms\n"
                 f"two {t_exp * 1e3:.1f} ms exposure windows", fontsize=8)

    # (b) accumulated signal per row
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(sig_n, rows, color="0.15", lw=1.0)
    ax2.set_ylim(n_rows, 0)
    ax2.set_xlim(0, 1.08)
    ax2.set_xlabel("signal / max")
    ax2.set_ylabel("sensor row")
    ax2.set_title(f"(b) rolling shutter\ncontrast {100 * contrast:.0f} %", fontsize=8)

    # (c) the resulting image
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.imshow(sig_n.reshape(-1, 1), cmap="gray", aspect="auto",
               vmin=0, vmax=1, extent=(0, 1, n_rows, 0))
    ax3.set_xticks([])
    ax3.set_ylim(n_rows, 0)
    ax3.set_yticks([])
    ax3.set_title("(c) image\nof a white\ncard", fontsize=8)

    fig.savefig(OUT / "fig_flicker_banding.pdf")
    plt.close(fig)
    print(f"wrote fig_flicker_banding.pdf  (row time {t_row * 1e6:.2f} us, "
          f"banding contrast {100 * contrast:.1f} %)")
    return contrast


if __name__ == "__main__":
    spectrum_figure()
    requirement_figure()
    flicker_figure()
    print("\nflicker contrast at other exposures (50 Hz supply, 25 ms frame):")
    for te in (3.3e-3, 4.0e-3, 5.4e-3, 9.0e-3, 10.0e-3, 11.1e-3,
               12.4e-3, 14.8e-3, 20.0e-3, 24.7e-3, 32.9e-3):
        w = 2 * np.pi * 50.0
        t0 = np.arange(3040) * 25e-3 / 3040
        s = 0.5 * te - (np.sin(2 * w * (t0 + te)) - np.sin(2 * w * t0)) / (4 * w)
        print(f"   t_exp = {te * 1e3:5.1f} ms -> contrast {100 * (s.max() - s.min()) / (s.max() + s.min()):5.1f} %")

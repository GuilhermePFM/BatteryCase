"""Draw the cutting-plane figure of M§6.6, docs/model/figures/cutting-plane.png.

    uv run python scripts/plot_cutting_plane.py

The figure is a schematic, not a measurement: it shows the shape of the dual
$L(\\lambda)$ and what two passes of Kelley's method know about it. The pieces
below are invented to make that shape legible — a convex piecewise-linear $L$,
two evaluations far enough apart that their cuts cross well below the curve —
so the axes carry no numbers. Only the structure is claimed.

Each piece is the Lagrangian value of one schedule $x$, affine in $\\lambda$:

    profit(x) + lambda * (cycle_budget - cycles(x))

so a piece's slope is the subgradient the evaluation returns, negative while
the relaxed schedule overspends the budget and positive once it underspends.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

OUT = Path(__file__).resolve().parents[1] / "docs" / "model" / "figures" / "cutting-plane.png"

# Categorical slots 1 and 2 of the documented palette, plus its ink and surface.
CURVE = "#2a78d6"
CUT = "#eb6834"
INK = "#0b0b0b"
MUTED = "#52514e"
SURFACE = "#fcfcfb"

# (intercept, slope) per schedule; the slope is the subgradient at that piece.
PIECES = [
    (220_000.0, -1943.0),
    (200_000.0, -500.0),
    (170_000.0, 300.0),
    (140_000.0, 900.0),
]

LAM_1, LAM_2 = 5.0, 55.0  # the two multipliers already evaluated
CUT_LO, CUT_HI = PIECES[0], PIECES[-1]  # the pieces those evaluations land on


def dual(lam: np.ndarray) -> np.ndarray:
    """L(lambda), the upper envelope of the pieces."""
    return np.max([a + b * lam for a, b in PIECES], axis=0)


def affine(piece: tuple[float, float], lam: np.ndarray) -> np.ndarray:
    a, b = piece
    return a + b * lam


def main() -> None:
    sns.set_theme(style="ticks", context="paper")

    lam = np.linspace(0.0, 60.0, 2001)
    values = dual(lam)

    lam_star = lam[int(np.argmin(values))]
    l_star = values.min()

    # The cuts cross where the two affine pieces meet: that is the master's
    # minimiser, the next multiplier to evaluate, and its height is the bound.
    lam_3 = (CUT_HI[0] - CUT_LO[0]) / (CUT_LO[1] - CUT_HI[1])
    theta_star = affine(CUT_LO, lam_3)
    upper = min(dual(np.array([LAM_1]))[0], dual(np.array([LAM_2]))[0])

    fig, ax = plt.subplots(figsize=(7.2, 4.5), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # The two bound levels, drawn first so the marks sit over them.
    for level in (upper, theta_star):
        ax.axhline(level, color=MUTED, lw=0.8, ls=(0, (4, 4)), alpha=0.55, zorder=1)

    ax.plot(lam, values, color=CURVE, lw=2.4, solid_joinstyle="round", zorder=2)

    # Drawn over the curve, so each cut is visibly the continuation of the
    # piece its pass landed on rather than a line that appears at the kink.
    for piece in (CUT_LO, CUT_HI):
        ax.plot(lam, affine(piece, lam), color=CUT, lw=2.0, ls=(0, (5, 3)), zorder=3)

    marks = [
        (LAM_1, dual(np.array([LAM_1]))[0], CURVE),
        (LAM_2, dual(np.array([LAM_2]))[0], CURVE),
        (lam_star, l_star, CURVE),
        (lam_3, theta_star, CUT),
    ]
    for x, y, colour in marks:
        ax.plot(x, y, "o", ms=8, color=colour, mec=SURFACE, mew=2.0, zorder=5)

    # The gap the loop terminates on: the distance between the two levels.
    ax.annotate(
        "",
        xy=(60.0, upper),
        xytext=(60.0, theta_star),
        arrowprops=dict(arrowstyle="<->", color=MUTED, lw=1.0, shrinkA=0, shrinkB=0),
    )
    ax.text(
        59.0,
        (upper + theta_star) / 2,
        "gap at pass $k$",
        color=MUTED,
        fontsize=9,
        va="center",
        ha="center",
        rotation=90,
    )

    # Direct labels: identity is never left to colour alone.
    ax.text(15.5, 203_000, r"$L(\lambda)$", color=CURVE, fontsize=11, fontweight="bold")
    ax.annotate(
        "cut from the\npass at " + r"$\lambda_1$",
        xy=(21.0, affine(CUT_LO, np.array([21.0]))[0]),
        xytext=(11.0, 173_500),
        color=CUT,
        fontsize=9,
        ha="center",
        arrowprops=dict(arrowstyle="-", color=CUT, lw=0.8, shrinkA=3, shrinkB=3),
    )
    ax.annotate(
        "cut from the\npass at " + r"$\lambda_2$",
        xy=(47.0, affine(CUT_HI, np.array([47.0]))[0]),
        xytext=(50.5, 170_500),
        color=CUT,
        fontsize=9,
        ha="center",
        arrowprops=dict(arrowstyle="-", color=CUT, lw=0.8, shrinkA=3, shrinkB=3),
    )
    ax.text(
        0.6,
        upper + 1_400,
        r"$\min_i L(\lambda_i)$: upper bound",
        color=MUTED,
        fontsize=9,
    )
    ax.text(
        0.6,
        theta_star + 1_400,
        r"$\theta^\star_k$: lower bound",
        color=MUTED,
        fontsize=9,
    )
    ax.annotate(
        r"$L(\lambda^\star)$, the true minimum",
        xy=(lam_star, l_star),
        xytext=(lam_star - 1.0, l_star - 9_000),
        color=INK,
        fontsize=9,
        ha="center",
        arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8, shrinkA=2, shrinkB=4),
    )

    ax.set_xlim(0.0, 61.5)
    ax.set_ylim(158_000, 224_000)
    ax.set_xlabel(r"$\lambda$  (£ per equivalent full cycle)", color=INK, fontsize=10)
    ax.set_ylabel(r"$L(\lambda)$  (£ over the horizon)", color=INK, fontsize=10)

    # Only the four multipliers the method names are worth a tick.
    ax.set_xticks([LAM_1, lam_3, lam_star, LAM_2])
    ax.set_xticklabels(
        [r"$\lambda_1$", r"$\lambda_3$", r"$\lambda^\star$", r"$\lambda_2$"], fontsize=10
    )
    ax.set_yticks([])
    ax.tick_params(axis="x", colors=MUTED, length=4)
    sns.despine(ax=ax, left=True, trim=False)
    ax.spines["bottom"].set_color(MUTED)
    ax.spines["bottom"].set_linewidth(0.8)

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=SURFACE, bbox_inches="tight")
    print(f"wrote {OUT.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()

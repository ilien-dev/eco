"""Builds Eco's logo masters (symbol, small cut, wordmark, lockups) as filled paths. Python 3, no deps."""
import math, os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
# Lima is the brand colour. It is too light for a mark on a light background (1.1:1), so there the
# colour mark is an ink symbol on a lima tile; on dark backgrounds the symbol itself is lima.
# LIME_DEEP is for small text and rules on light backgrounds only, never for the logo.
LIME, LIME_DEEP, INK, PAPER = "#C4F03A", "#4A6600", "#151515", "#F4F4F2"
T60 = math.tan(math.radians(60))

def f(v): return f"{v:.2f}".rstrip("0").rstrip(".")

# ---------- symbol: two peaks (60° flanks) with a cave and its echo ----------
DY = -6  # optical lift: a bottom-heavy mark sits slightly above centre
BASE = 220
def toward(p, q, d):
    l = math.hypot(q[0] - p[0], q[1] - p[1])
    return (p[0] + (q[0] - p[0]) * d / l, p[1] + (q[1] - p[1]) * d / l)

def mountain():
    """Two peaks; each peak's inner flank mirrors its outer flank, the valley is where they meet."""
    L, R = (96, 68), (164, 48)
    lb, rb = L[0] - (BASE - L[1]) / T60, 244   # left flank at exactly 60°
    kl = (BASE - L[1]) / (L[0] - lb)          # left peak slope
    kr = (BASE - R[1]) / (rb - R[0])          # right peak slope
    vx = (R[1] + kr * R[0] - L[1] + kl * L[0]) / (kl + kr)
    vy = L[1] + kl * (vx - L[0])
    V = (vx, vy)
    a1, a2 = toward(L, (lb, BASE), 14), toward(L, V, 14)
    b1, b2 = toward(R, V, 14), toward(R, (rb, BASE), 14)
    pts = (f"M{f(lb)} {BASE}L{f(a1[0])} {f(a1[1])}Q{L[0]} {L[1]} {f(a2[0])} {f(a2[1])}L{f(vx)} {f(vy)}"
           f"L{f(b1[0])} {f(b1[1])}Q{R[0]} {R[1]} {f(b2[0])} {f(b2[1])}L{rb} {BASE}Z")
    return pts, (lb, rb, vy)

def arch(cx, w, top):
    r = w / 2; spring = top + r
    return f"M{f(cx-r)} {BASE}V{f(spring)}A{f(r)} {f(r)} 0 0 1 {f(cx+r)} {f(spring)}V{BASE}Z"

def symbol(small=False):
    m, _ = mountain()
    if small:
        d = m + arch(128, 96, 158)
    else:
        d = m + arch(128, 88, 158) + arch(128, 40, 182)
    return d

def svg(body, vb="0 0 256 256", title="Eco"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}"><title>{title}</title>{body}</svg>\n'

def sym_path(color, small=False, tx=0, ty=0, s=1):
    return f'<path transform="translate({f(tx)} {f(ty + DY*s)}) scale({f(s)})" fill="{color}" fill-rule="evenodd" d="{symbol(small)}"/>'

# ---------- wordmark "eco": geometric letters, terminals cut at 60° like the flanks ----------
H, S = 120, 22            # x-height, stroke
R, r = H / 2, H / 2 - S
def circle(cx, cy, rad, ccw=False):
    sw = 0 if ccw else 1
    return f"M{f(cx-rad)} {f(cy)}A{f(rad)} {f(rad)} 0 1 {sw} {f(cx+rad)} {f(cy)}A{f(rad)} {f(rad)} 0 1 {sw} {f(cx-rad)} {f(cy)}Z"

def cut(cx, cy, theta_deg, slope_sign):
    """Points where a 60° line through the stroke's mid-circle at angle theta meets outer and inner circles."""
    th = math.radians(theta_deg)
    rm = (R + r) / 2
    px, py = cx + rm * math.cos(th), cy - rm * math.sin(th)
    dx, dy = 0.5, -slope_sign * math.sqrt(3) / 2
    res = []
    for rad in (R, r):
        # solve |P + t d - C| = rad
        ox, oy = px - cx, py - cy
        b = 2 * (ox * dx + oy * dy); c = ox * ox + oy * oy - rad * rad
        disc = math.sqrt(b * b - 4 * c)
        t = min(((-b + disc) / 2, (-b - disc) / 2), key=abs)
        res.append((px + t * dx, py + t * dy))
    return res  # outer, inner

def arc_pts(cx, cy, rad, a0, a1, n=48):
    return [(cx + rad * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy - rad * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]

def ang(cx, cy, p):
    return math.degrees(math.atan2(cy - p[1], p[0] - cx)) % 360

def poly(pts):
    return "M" + "L".join(f"{f(x)} {f(y)}" for x, y in pts) + "Z"

def letter_c(cx, cy):
    to, ti = cut(cx, cy, 42, +1)     # top terminal, "/" cut
    bo, bi = cut(cx, cy, -42, -1)    # bottom terminal, "\" cut
    a_to, a_bo = ang(cx, cy, to), ang(cx, cy, bo)
    a_ti, a_bi = ang(cx, cy, ti), ang(cx, cy, bi)
    outer = arc_pts(cx, cy, R, a_to, a_bo if a_bo > a_to else a_bo + 360)
    inner = arc_pts(cx, cy, r, a_bi if a_bi > a_ti else a_bi, a_ti)
    inner = arc_pts(cx, cy, r, (a_bi if a_bi > a_ti else a_bi + 360), a_ti)
    return poly(outer + inner)

def letter_e(cx, cy):
    bo, bi = cut(cx, cy, -38, -1)
    a_bo, a_bi = ang(cx, cy, bo), ang(cx, cy, bi)
    outer = arc_pts(cx, cy, R, 0, a_bo)
    inner = arc_pts(cx, cy, r, a_bi, 0)
    ring = poly(outer + inner)
    bar = S * 0.86
    rect = [(cx + R, cy + bar / 2), (cx + R, cy - bar / 2), (cx - r - 1, cy - bar / 2), (cx - r - 1, cy + bar / 2)]
    return ring + poly(rect)

def wordmark_paths(color, x0, base_y, scale=1.0, gap=6):
    """Letters drawn on x-height H at origin; returns svg elements and width."""
    adv = 2 * R + gap
    cy = -R
    g = (f'<g transform="translate({f(x0)} {f(base_y)}) scale({f(scale)})" fill="{color}">'
         f'<path d="{letter_e(R, cy)}"/>'
         f'<path d="{letter_c(R + adv, cy)}"/>'
         f'<path fill-rule="evenodd" d="{circle(R + 2*adv, cy, R)}{circle(R + 2*adv, cy, r, ccw=True)}"/></g>')
    width = (2 * R * 3 + 2 * gap) * scale
    return g, width

def tile(small=False, side=256.0, x=0.0, y=0.0, pad=0.16):
    """The colour mark for light backgrounds: an ink symbol centred on a lima square."""
    lb, rb, _ = mountain()[1]
    s = side * (1 - 2 * pad) / (rb - lb)
    sw, sh = (rb - lb) * s, (BASE - 48) * s
    tx = x + (side - sw) / 2 - lb * s
    ty = y + (side - sh) / 2 - 48 * s
    return (f'<rect x="{f(x)}" y="{f(y)}" width="{f(side)}" height="{f(side)}" fill="{LIME}"/>'
            + sym_path(INK, small, tx, ty, s))

def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "lockups"), exist_ok=True)
    w = lambda n, s: open(os.path.join(OUT, n), "w", encoding="utf-8").write(s)
    w("eco-symbol.svg", svg(sym_path(LIME), title="Eco"))
    w("eco-symbol-small.svg", svg(sym_path(LIME, small=True), title="Eco"))
    w("eco-symbol-tile.svg", svg(tile(), title="Eco"))
    w("eco-symbol-tile-small.svg", svg(tile(small=True, pad=0.12), title="Eco"))
    lb, rb, _ = mountain()[1]
    mh = BASE - 48                      # mountain height
    unit = 44                           # half the cave width: spacing unit
    # horizontal lockup: wordmark x-height = 0.58 x mountain height
    sc = 0.58 * mh / H
    wmw = wordmark_paths(INK, 0, 0, sc)[1]
    # on dark: lima symbol, paper word, baselines aligned (the plain master for one-colour variants)
    W = (rb - lb) + unit + wmw
    dark = sym_path(LIME, tx=-lb, ty=-48 - DY) + wordmark_paths(PAPER, (rb - lb) + unit, mh, sc)[0]
    w("lockups/eco-horizontal-on-dark.svg", svg(dark, vb=f"0 0 {f(W)} {mh}", title="Eco"))
    # on light: the tile, then the ink word centred on the tile
    TW = mh + unit + wmw
    light = tile(side=mh) + wordmark_paths(INK, mh + unit, mh / 2 + H * sc / 2, sc)[0]
    w("eco-horizontal.svg", svg(light, vb=f"0 0 {f(TW)} {mh}", title="Eco"))
    # stacked lockup
    sc2 = 0.5 * mh / H
    wmw2 = wordmark_paths(INK, 0, 0, sc2)[1]
    SW = max(rb - lb, wmw2)
    SH = mh + unit + H * sc2
    dark = (sym_path(LIME, tx=(SW - (rb - lb)) / 2 - lb, ty=-48 - DY) +
            wordmark_paths(PAPER, (SW - wmw2) / 2, SH, sc2)[0])
    w("lockups/eco-stacked-on-dark.svg", svg(dark, vb=f"0 0 {f(SW)} {f(SH)}", title="Eco"))
    TS = max(mh, wmw2)
    light = tile(side=mh, x=(TS - mh) / 2) + wordmark_paths(INK, (TS - wmw2) / 2, SH, sc2)[0]
    w("eco-stacked.svg", svg(light, vb=f"0 0 {f(TS)} {f(SH)}", title="Eco"))
    wmb, wmbw = wordmark_paths(INK, 0, H, 1)
    w("eco-wordmark.svg", svg(wmb, vb=f"0 0 {f(wmbw)} {H}", title="Eco"))

if __name__ == "__main__":
    main()

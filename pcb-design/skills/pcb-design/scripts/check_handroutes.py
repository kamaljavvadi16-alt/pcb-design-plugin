"""Generate-time gate for the hand-routed spec.SEGMENTS / spec.VIAS tables.

Those tables are **coordinate-keyed**: literal (x, y) pairs that do NOT follow the parts they
serve. Move a footprint and the backbone silently keeps pointing at the old anchor -- it still
generates, still looks plausible, and only shows up as a short or a stubborn unrouted net after a
full autoroute. On the board this skill was distilled from, one stale backbone drove a shorting
violation on all 10 routing attempts before anyone looked at the table.

Checks, in about a second, what otherwise costs a routing round:
  1. every segment endpoint that lands on a pad lands on a pad of ITS OWN net
     (an endpoint on another net's pad is a designed-in short);
  2. no segment passes through a different-net pad, using the REAL clearance envelope
     (track half-width + clearance -- not the centreline, or width-induced violations are invisible);
  3. no two different-net hand-routed segments collide on the same layer;
  4. no via clashes with a different-net pad;
  5. no via-vs-via and no via-vs-segment clash across nets -- a via is a through-hole barrel, so
     unlike a track it clashes on EVERY layer regardless of the segment's own layer.

Netless pads are skipped: they cannot create a net-to-net short, and legitimately exist (QFN EP
paste sub-pads, deliberately floating pins such as a charger's 1S/4.2V select).

Read-only. Exit 1 on any finding.
    <kicad_python> check_handroutes.py [board.kicad_pcb]
"""
import math
import sys

try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config

spec = config.spec
P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB
OX, OY = getattr(spec, "ORIGIN", (0.0, 0.0))
CLR = getattr(spec, "DEFAULT_CLEARANCE", 0.20)
VIA_R = getattr(spec, "DEFAULT_VIA", 0.7) / 2.0
ENDPOINT_TOL = 0.30     # an endpoint this close to a pad counts as "landing" on it

SEGMENTS = list(getattr(spec, "SEGMENTS", []))
VIAS = list(getattr(spec, "VIAS", []))
if not SEGMENTS and not VIAS:
    print("no hand-routed SEGMENTS/VIAS in the board spec -- nothing to check.  PASS")
    sys.exit(0)

b = pcbnew.LoadBoard(P)
mm = pcbnew.ToMM

pads = []
for fp in b.GetFootprints():
    for p in fp.Pads():
        if not p.GetNetname():
            continue
        bb = p.GetBoundingBox()
        pads.append((f"{fp.GetReference()}.{p.GetPadName()}", p.GetNetname(),
                     mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY,
                     mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY))


def _rect_dist(x, y, a, c, d, e):
    """True distance from a point to an axis-aligned rectangle (0 inside).

    NOT per-axis bbox inflation: that over-flags a diagonal approach at a pad CORNER, where the
    real Euclidean distance is larger than either axis suggests, and produces false failures on
    perfectly legal escapes.
    """
    return math.hypot(max(a - x, 0.0, x - d), max(c - y, 0.0, y - e))


def near_pad(x, y, tol=0.0):
    return [(n, net) for n, net, a, c, d, e in pads if _rect_dist(x, y, a, c, d, e) <= tol]


def seg_pad_hits(x1, y1, x2, y2, net, w):
    """Different-net pads the segment violates clearance against (real envelope, not centreline)."""
    hits = set()
    n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.1))
    tol = CLR + w / 2.0
    for i in range(n + 1):
        x, y = x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n
        for nm, pnet in near_pad(x, y, tol):
            if pnet != net:
                hits.add((nm, pnet))
    return hits


def seg_seg_dist(a, b_):
    (x1, y1, x2, y2), (x3, y3, x4, y4) = a, b_
    n, best = 24, 9e9
    for i in range(n + 1):
        px, py = x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n
        for j in range(n + 1):
            qx, qy = x3 + (x4 - x3) * j / n, y3 + (y4 - y3) * j / n
            best = min(best, math.hypot(px - qx, py - qy))
    return best


bad = []
print(f"hand-routed: {len(SEGMENTS)} segments, {len(VIAS)} vias")

# 1 + 2 -- endpoints and pass-throughs
for x1, y1, x2, y2, w, layer, net in SEGMENTS:
    for ex, ey, which in ((x1, y1, "start"), (x2, y2, "end")):
        wrong = [(n, pn) for n, pn in near_pad(ex, ey, ENDPOINT_TOL) if pn != net]
        if wrong:
            bad.append(f"[{net}] {which} ({ex:.2f},{ey:.2f}) lands on WRONG-NET pad(s): "
                       + ", ".join(f"{n}[{pn}]" for n, pn in wrong))
    for n, pn in sorted(seg_pad_hits(x1, y1, x2, y2, net, w)):
        bad.append(f"[{net}] segment ({x1:.2f},{y1:.2f})->({x2:.2f},{y2:.2f}) on {layer} "
                   f"CROSSES {n}[{pn}]")

# 3 -- segment vs segment, different nets, same layer
for i in range(len(SEGMENTS)):
    for j in range(i + 1, len(SEGMENTS)):
        a, c = SEGMENTS[i], SEGMENTS[j]
        if a[6] == c[6] or a[5] != c[5]:
            continue
        d = seg_seg_dist(a[:4], c[:4]) - (a[4] + c[4]) / 2
        if d < CLR:
            bad.append(f"[{a[6]}] vs [{c[6]}] hand-routes collide on {a[5]}: gap {d:.3f}mm")

# 4 -- via vs different-net pad
for x, y, net in VIAS:
    for nm, pnet in near_pad(x, y, VIA_R + CLR):
        if pnet != net:
            bad.append(f"[{net}] via ({x:.2f},{y:.2f}) clashes with {nm}[{pnet}]")

# 5 -- via vs via, and via vs segment, across nets (barrels clash on every layer)
for i in range(len(VIAS)):
    for j in range(i + 1, len(VIAS)):
        x1, y1, n1 = VIAS[i]
        x2, y2, n2 = VIAS[j]
        if n1 == n2:
            continue
        d = math.hypot(x1 - x2, y1 - y2) - 2 * VIA_R
        if d < CLR:
            bad.append(f"[{n1}] via ({x1:.2f},{y1:.2f}) vs [{n2}] via ({x2:.2f},{y2:.2f}): "
                       f"gap {d:.3f}mm")
for vx, vy, vnet in VIAS:
    for x1, y1, x2, y2, w, lay, snet in SEGMENTS:
        if snet == vnet:
            continue
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.1))
        dmin = min(math.hypot(vx - (x1 + (x2 - x1) * k / n), vy - (y1 + (y2 - y1) * k / n))
                   for k in range(n + 1)) - VIA_R - w / 2.0
        if dmin < CLR:
            bad.append(f"[{vnet}] via ({vx:.2f},{vy:.2f}) vs [{snet}] segment on {lay}: "
                       f"gap {dmin:.3f}mm")

if bad:
    print(f"\n{len(bad)} FINDING(S):")
    for s in bad:
        print("   ! " + s)
    sys.exit(1)
print("\nall hand-routed segments/vias land on their own net and clear everything else.  PASS")

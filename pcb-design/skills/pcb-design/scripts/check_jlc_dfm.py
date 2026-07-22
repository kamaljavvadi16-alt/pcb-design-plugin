"""Fab-house DFM gate for the checks KiCad's own DRC does NOT perform.

This exists because a board can be **DRC 0 violations / 0 unconnected and still carry real
manufacturing DANGERs**. `kicad-cli pcb drc` does not police drill-to-drill spacing, via annular
ring, or the drilled hole's clearance to pad copper -- all three are things JLCPCB's DFM flags and
all three have shipped from a "clean" board.

Checks (thresholds overridable in board_spec.py):
  1. hole -> hole edge gap        vias + drilled pads      DANGER  < MIN_HOLE_GAP     (0.30)
  2. via annular ring             (pad - drill) / 2        WARNING < MIN_ANNULAR      (0.20)
  3. via copper -> DIFFERENT-net pad copper                DANGER  < MIN_CLEARANCE    (0.20)
  4. via DRILL  -> pad copper, ANY net                     DANGER  < MIN_HOLE_TO_PAD  (0.20)
  5. copper -> board edge                                  DANGER  < MIN_EDGE         (0.30)
  6. acute trace corners (one path turning sharply)        WARNING < ACUTE_DEG        (80)

On #4: the fab measures the **drilled hole** against pad copper, regardless of net -- the risk is
drill registration breaking into the pad and solder wicking down the barrel, not an electrical
short. Checking copper-to-copper instead (and concluding "same net, harmless") is the classic miss.

A via whose hole sits INSIDE a pad is reported separately:
  * on a thermal EP (parent footprint has >= EP_MIN_PADS pads) it is intentional and standard;
  * on a 2-pad chip land it wicks solder out of the joint and is reported as a DANGER.
  Pad AREA cannot tell these apart -- a real QFN EP can be 1.49 mm2 and an 0805 land 1.45 mm2 --
  so the discriminator is the parent footprint's pad count.

Read-only. Exit 1 on any DANGER (warnings print but do not fail), so it can gate the fab export:
    <kicad_python> check_jlc_dfm.py [board.kicad_pcb]
"""
import math
import sys
from collections import defaultdict

try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config

spec = config.spec
P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB

MIN_HOLE_GAP = getattr(spec, "MIN_HOLE_GAP", 0.30)
MIN_ANNULAR = getattr(spec, "MIN_ANNULAR", 0.20)
MIN_CLEARANCE = getattr(spec, "DEFAULT_CLEARANCE", 0.20)
MIN_HOLE_TO_PAD = getattr(spec, "MIN_HOLE_TO_PAD", 0.20)
MIN_EDGE = getattr(spec, "EDGE_CLEARANCE", 0.30)
ACUTE_DEG = getattr(spec, "ACUTE_DEG", 80.0)
EP_MIN_PADS = getattr(spec, "EP_MIN_PADS", 6)

b = pcbnew.LoadBoard(P)
mm = pcbnew.ToMM
OX, OY = getattr(spec, "ORIGIN", (0.0, 0.0))
danger, warn, in_pad = [], [], []


def L(v):
    return mm(v.x) - OX, mm(v.y) - OY


def _shape_gap(shape, pos, radius, ceiling):
    """Distance from a circle (pos, radius) to a pad shape, by Collide bisection. None if far."""
    if not shape.Collide(pos, pcbnew.FromMM(radius + ceiling)):
        return None
    lo, hi = 0.0, radius + ceiling + 0.5
    for _ in range(20):
        mid = (lo + hi) / 2
        if shape.Collide(pos, pcbnew.FromMM(mid)):
            hi = mid
        else:
            lo = mid
    return hi - radius


CU_LAYERS = [l for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)]
vias = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
pads = [(fp, p) for fp in b.GetFootprints() for p in fp.Pads()]

# ---- 1. hole-to-hole spacing -------------------------------------------------------------
holes = [("via",) + L(t.GetPosition()) + (mm(t.GetDrill()) / 2.0,) for t in vias]
holes += [(f"{fp.GetReference()}.{p.GetPadName()}",) + L(p.GetPosition())
          + (mm(p.GetDrillSizeX()) / 2.0,) for fp, p in pads if p.GetDrillSizeX() > 0]
worst_hole = 9e9
for i in range(len(holes)):
    n1, x1, y1, r1 = holes[i]
    for j in range(i + 1, len(holes)):
        n2, x2, y2, r2 = holes[j]
        d = math.hypot(x1 - x2, y1 - y2) - r1 - r2
        worst_hole = min(worst_hole, d)
        if d < MIN_HOLE_GAP:
            danger.append(f"hole gap {d:.3f}mm  {n1} ({x1:.2f},{y1:.2f}) <-> {n2} ({x2:.2f},{y2:.2f})")

# ---- 2. annular ring ---------------------------------------------------------------------
worst_ann = 9e9
for t in vias:
    a = (mm(t.GetWidth(pcbnew.F_Cu)) - mm(t.GetDrill())) / 2.0
    worst_ann = min(worst_ann, a)
    if a < MIN_ANNULAR - 1e-6:
        x, y = L(t.GetPosition())
        warn.append(f"annular {a:.3f}mm  via[{t.GetNetname()}] ({x:.2f},{y:.2f})")

# ---- 3 + 4. via copper / via DRILL vs pad copper ------------------------------------------
worst_vp = worst_vh = 9e9
for t in vias:
    vnet = t.GetNetname()
    vcu = mm(t.GetWidth(pcbnew.F_Cu)) / 2.0
    vdr = mm(t.GetDrill()) / 2.0
    pos = t.GetPosition()
    x, y = L(pos)
    for fp, p in pads:
        pnet = p.GetNetname()
        for layer in CU_LAYERS:
            if not p.IsOnLayer(layer):
                continue
            sh = p.GetEffectiveShape(layer)
            # 3: copper-to-copper, different nets only (an electrical short)
            if pnet and pnet != vnet:
                g = _shape_gap(sh, pos, vcu, MIN_CLEARANCE)
                if g is not None:
                    worst_vp = min(worst_vp, g)
                    if g < MIN_CLEARANCE:
                        danger.append(f"via->pad {g:.3f}mm  via[{vnet}] ({x:.2f},{y:.2f}) -> "
                                      f"{fp.GetReference()}.{p.GetPadName()}[{pnet}]")
            # 4: DRILL vs pad copper, any net (drill registration / solder wicking)
            gh = _shape_gap(sh, pos, vdr, MIN_HOLE_TO_PAD)
            if gh is None:
                continue
            if gh < 0:
                n_pads = len(list(fp.Pads()))
                tag = f"{fp.GetReference()}.{p.GetPadName()}"
                if n_pads >= EP_MIN_PADS:
                    in_pad.append(f"thermal-EP via[{vnet}] ({x:.2f},{y:.2f}) -> {tag}")
                else:
                    danger.append(f"via inside COMPONENT pad (wicks solder)  via[{vnet}] "
                                  f"({x:.2f},{y:.2f}) -> {tag} "
                                  f"({mm(p.GetSize().x):.2f}x{mm(p.GetSize().y):.2f})")
            else:
                worst_vh = min(worst_vh, gh)
                if gh < MIN_HOLE_TO_PAD:
                    danger.append(f"via HOLE->pad {gh:.3f}mm  via[{vnet}] ({x:.2f},{y:.2f}) -> "
                                  f"{fp.GetReference()}.{p.GetPadName()}[{pnet}]")
            break

# ---- 5. copper to board edge --------------------------------------------------------------
edges = []
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts and d.Type() == pcbnew.PCB_SHAPE_T \
            and d.GetShape() == pcbnew.SHAPE_T_SEGMENT:
        edges.append(L(d.GetStart()) + L(d.GetEnd()))


def segd(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


worst_edge = 9e9
for t in b.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        pts, half = [L(t.GetPosition())], mm(t.GetWidth(pcbnew.F_Cu)) / 2.0
    else:
        pts, half = [L(t.GetStart()), L(t.GetEnd())], mm(t.GetWidth()) / 2.0
    for px, py in pts:
        for e in edges:
            d = segd(px, py, *e) - half
            worst_edge = min(worst_edge, d)
            if d < MIN_EDGE:
                danger.append(f"copper->edge {d:.3f}mm  [{t.GetNetname()}] ({px:.2f},{py:.2f})")

# ---- 6. acute corners ----------------------------------------------------------------------
# A real acid-trap corner is ONE trace path turning sharply: exactly TWO segments meeting at a
# point. Counting every pair that shares an endpoint also counts normal fan-out (3+ traces off a
# pad) and duplicate collinear segments -- pure noise, and a gate that cries wolf gets ignored.
joints = defaultdict(list)
for t in b.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        continue
    key = (t.GetNetCode(), t.GetLayer())
    a, c = L(t.GetStart()), L(t.GetEnd())
    joints[(key, (round(a[0], 3), round(a[1], 3)))].append(c)
    joints[(key, (round(c[0], 3), round(c[1], 3)))].append(a)
acute = 0
for (key, pt), others in joints.items():
    if len(others) != 2:
        continue
    (ax, ay), (bx, by) = others
    v1, v2 = (ax - pt[0], ay - pt[1]), (bx - pt[0], by - pt[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        continue
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    ang = math.degrees(math.acos(cos))
    if ang < 1.0 or ang > 179.0:          # duplicate / collinear, not a corner
        continue
    if ang < ACUTE_DEG:
        acute += 1
        net = b.FindNet(key[0])
        warn.append(f"acute corner {ang:.1f}deg at ({pt[0]:.2f},{pt[1]:.2f}) "
                    f"net {net.GetNetname() if net else '?'}")


def _fmt(v):
    return "n/a" if v > 1e8 else f"{v:.3f} mm"


print(f"fab-house DFM on {P.replace(chr(92), '/').split('/')[-1]}")
print(f"  min hole-to-hole gap : {_fmt(worst_hole)}   (limit {MIN_HOLE_GAP})")
print(f"  min via annular      : {_fmt(worst_ann)}   (limit {MIN_ANNULAR})")
print(f"  min via->pad (diff)  : {_fmt(worst_vp)}   (limit {MIN_CLEARANCE})")
print(f"  min via HOLE->pad    : {_fmt(worst_vh)}   (limit {MIN_HOLE_TO_PAD})")
print(f"  min copper->edge     : {_fmt(worst_edge)}   (limit {MIN_EDGE})")
print(f"  via-in-pad (thermal) : {len(in_pad)}")
print(f"  acute corners        : {acute}")
if danger:
    print(f"\n{len(danger)} DANGER(S):")
    for d in danger[:25]:
        print("   ! " + d)
if warn:
    print(f"\n{len(warn)} warning(s):")
    for w in warn[:15]:
        print("   - " + w)
if not danger and not warn:
    print("\nno fab-house DFM issues.  PASS")
sys.exit(1 if danger else 0)

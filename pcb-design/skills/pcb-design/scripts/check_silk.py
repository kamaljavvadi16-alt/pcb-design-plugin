"""Trustworthy silkscreen DFM gate (JLCPCB-equivalent). Checks EVERY silk item with accurate
geometry and reports PASS/ISSUES:
  - line width   : graphic strokes >= MIN_W
  - text width   : effective (rendered) pen >= 0.15mm
  - silk -> pad  : text GLYPHS, logo POLYGONS and shape SEGMENTS all clear same-side pad copper
  - silk -> hole : ... all clear every drilled hole AND via (holes go through both sides)
Read-only; KiCad may stay open.   <kicad_python> check_silk.py [board.kicad_pcb]
"""
import sys
import math
try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config
import fix_silk

_FIELD_T = getattr(pcbnew, "PCB_FIELD_T", None)
P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB
MINW = pcbnew.FromMM(fix_silk.MIN_W)
PEN_MIN = pcbnew.FromMM(0.15)
CLR = 0.15


def text_pts(it):
    ps = pcbnew.SHAPE_POLY_SET()
    it.TransformTextToPolySet(ps, 0, pcbnew.FromMM(0.02), pcbnew.ERROR_INSIDE)
    pts = []
    for oi in range(ps.OutlineCount()):
        o = ps.Outline(oi)
        pts += [(pcbnew.ToMM(o.CPoint(k).x), pcbnew.ToMM(o.CPoint(k).y)) for k in range(o.PointCount())]
    return pts


def seg_pts(it):
    pts = []
    for x1, y1, x2, y2 in (fix_silk._shape_segs(it) or []):
        n = max(1, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / 0.05)))
        pts += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]
    return pts


def near_holes(pts, half, obs):
    for x, y in pts:
        for ox, oy, r in obs:
            if math.hypot(x - ox, y - oy) - r - half < CLR:
                return True
    return False


def near_pads(pts, half, pads, cu_layer):
    if not pts:
        return False
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    bl, bt, br, bb = min(xs), min(ys), max(xs), max(ys)
    cl = CLR + half
    cl_iu = pcbnew.FromMM(cl)
    for p in pads:
        pb = p.GetBoundingBox()
        if (pcbnew.ToMM(pb.GetRight()) < bl - cl or pcbnew.ToMM(pb.GetLeft()) > br + cl or
                pcbnew.ToMM(pb.GetBottom()) < bt - cl or pcbnew.ToMM(pb.GetTop()) > bb + cl):
            continue
        sh = p.GetEffectiveShape(cu_layer)
        for x, y in pts:
            if sh.Collide(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)), cl_iu):
                return True
    return False


board = pcbnew.LoadBoard(P)
front, back, holes = fix_silk._obstacles(board)
fpads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.IsOnLayer(pcbnew.F_Cu)]
bpads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.IsOnLayer(pcbnew.B_Cu)]
thin = thintext = pad = hole = 0
items = [it for fp in board.GetFootprints() for it in fp.GraphicalItems()]
items += list(board.GetDrawings())
try:
    items += [fld for fp in board.GetFootprints() for fld in fp.GetFields() if fld.IsVisible()]
except Exception as e:
    print(f"  (silk field check skipped: {e})")
for it in items:
    layer = it.GetLayer()
    if layer not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
        continue
    side_pads = fpads if layer == pcbnew.F_SilkS else bpads
    cu_layer = pcbnew.F_Cu if layer == pcbnew.F_SilkS else pcbnew.B_Cu
    if it.Type() == pcbnew.PCB_TEXT_T or (_FIELD_T is not None and it.Type() == _FIELD_T):
        if it.GetEffectiveTextPenWidth() < PEN_MIN:
            thintext += 1
        pts, half = text_pts(it), 0.0
    elif it.Type() == pcbnew.PCB_SHAPE_T:
        half = pcbnew.ToMM(it.GetWidth()) / 2.0
        if it.GetShape() == pcbnew.SHAPE_T_POLY:
            if it.GetWidth() > 0 and it.GetWidth() < MINW:
                thin += 1
            pts = fix_silk._poly_pts(it)
        else:
            if it.GetWidth() < MINW:
                thin += 1
            pts = seg_pts(it)
    else:
        continue
    pad += near_pads(pts, half, side_pads, cu_layer)
    hole += near_holes(pts, half, holes)

ok = (thin == 0 and thintext == 0 and pad == 0 and hole == 0)
print(f"silk DFM ({'PASS' if ok else 'ISSUES'}): "
      f"lines<{fix_silk.MIN_W}mm={thin}, text<0.15mm={thintext}, "
      f"silk-on-pad items={pad}, silk-on-hole/via items={hole}  [JLC min 0.15mm]")
sys.exit(0 if ok else 1)

"""Placement gate: load the board (validates syntax) and report
  - board outline bbox
  - every pair of footprints whose COURTYARDS overlap (collisions to fix before routing)
  - any footprint extending past the board edge
  - unconnected ratsnest count + total nets (net-table sanity)
Read-only; KiCad may stay open.   Usage: <kicad_python> check_overlap.py [board.kicad_pcb]
"""
import sys
try:
    import pcbnew
except ModuleNotFoundError:
    raise SystemExit("This script needs KiCad's bundled Python (no 'pcbnew' in this interpreter).\n"
                     "  Run it with KiCad's python; get the path from:  python config.py")
import config

spec = config.spec
P = sys.argv[1] if len(sys.argv) > 1 else config.BOARD_PCB
OX, OY = spec.ORIGIN
b = pcbnew.LoadBoard(P)
mm = pcbnew.ToMM
# Board size is DERIVED from Edge.Cuts, not taken from the spec. If the outline is edited (or the
# spec is copied to a new revision and W/H not updated) a hardcoded size silently compares parts
# against the WRONG board and the off-board test can never fire near the real edge.
_e = b.GetBoardEdgesBoundingBox()
W, H = mm(_e.GetWidth()), mm(_e.GetHeight())
if abs(W - getattr(spec, "W", W)) > 0.2 or abs(H - getattr(spec, "H", H)) > 0.2:
    print(f"note: Edge.Cuts is {W:.2f} x {H:.2f} mm but the spec says "
          f"{getattr(spec, 'W', 0):.2f} x {getattr(spec, 'H', 0):.2f} -- using Edge.Cuts.")


def court_poly(fp):
    ps = pcbnew.SHAPE_POLY_SET()
    try:
        cf = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cf.OutlineCount():
            ps.Append(cf)
        cb = fp.GetCourtyard(pcbnew.B_CrtYd)
        if cb.OutlineCount():
            ps.Append(cb)
    except Exception:
        pass
    return ps if ps.OutlineCount() else None


def pad_silk_bbox(fp):
    xs, ys = [], []
    for it in list(fp.Pads()) + list(fp.GraphicalItems()):
        bb = it.GetBoundingBox()
        xs += [bb.GetX(), bb.GetRight()]; ys += [bb.GetY(), bb.GetBottom()]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


edge = b.GetBoardEdgesBoundingBox()
print(f"Board outline: {mm(edge.GetWidth()):.2f} x {mm(edge.GetHeight()):.2f} mm "
      f"@ ({mm(edge.GetX())-OX:.1f},{mm(edge.GetY())-OY:.1f})")

fps = list(b.GetFootprints())
print(f"Footprints: {len(fps)}")

polys, nocourt = {}, []
for fp in fps:
    cp = court_poly(fp)
    if cp is None:
        nocourt.append(fp.GetReference())
    else:
        polys[fp.GetReference()] = cp
hits = []
refs = sorted(polys)
for i in range(len(refs)):
    for j in range(i + 1, len(refs)):
        a = pcbnew.SHAPE_POLY_SET(polys[refs[i]])
        a.BooleanIntersection(polys[refs[j]])
        if a.OutlineCount():
            area = sum(abs(a.Outline(k).Area()) for k in range(a.OutlineCount()))
            hits.append((refs[i], refs[j], mm(mm(area))))
print(f"\nCourtyard OVERLAPS: {len(hits)}")
for a, c, ar in sorted(hits, key=lambda t: -t[2]):
    print(f"   ! {a:5} <-> {c:5}  overlap ~{ar:.2f} mm^2")
if nocourt:
    print(f"(no-courtyard fps, bbox-only: {', '.join(sorted(nocourt))})")

# ---- NPTH holes vs courtyards -------------------------------------------------------------
# Mounting holes are usually bare NPTH footprints with `allow_missing_courtyard` and NO courtyard,
# so the pairwise test above SKIPS them entirely -- they are invisible as obstacles. KiCad only
# catches the collision at route time as `npth_inside_courtyard`, i.e. after a full autoroute.
# Model each NPTH pad as a disc of its drill radius and test it against every courtyard.
npth = []
for fp in fps:
    for p in fp.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and p.GetDrillSizeX() > 0:
            q = p.GetPosition()
            npth.append((fp.GetReference(), mm(q.x), mm(q.y), mm(p.GetDrillSizeX()) / 2))
nhits = []
for ref, hx, hy, r in npth:
    for oref, poly in polys.items():
        if oref == ref:
            continue
        if pcbnew.SHAPE_POLY_SET(poly).Collide(
                pcbnew.VECTOR2I(pcbnew.FromMM(hx), pcbnew.FromMM(hy)), pcbnew.FromMM(r)):
            nhits.append((ref, oref))
print(f"\nNPTH hole inside a courtyard: {len(nhits)}")
for ref, oref in nhits:
    print(f"   ! {ref:5} hole <-> {oref:5} courtyard")

print("\nParts past board edge (>0.5mm):")
out = False
for fp in fps:
    bb = pad_silk_bbox(fp)
    if not bb:
        continue
    x0, y0, x1, y1 = mm(bb[0]) - OX, mm(bb[1]) - OY, mm(bb[2]) - OX, mm(bb[3]) - OY
    if x0 < -0.5 or y0 < -0.5 or x1 > W + 0.5 or y1 > H + 0.5:
        print(f"   ! {fp.GetReference():5} ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})")
        out = True
if not out:
    print("   none")

b.BuildConnectivity()
print(f"\nUnrouted ratsnest: {b.GetConnectivity().GetUnconnectedCount(False)}   "
      f"Nets: {b.GetNetCount()-1}")
sys.exit(1 if hits else 0)

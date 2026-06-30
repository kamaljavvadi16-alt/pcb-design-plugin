"""Import the freerouting SES result, then finish the board: route stragglers, add the top GND
pour, stitch the pours, tie GND pads to the plane/pour, dedupe overlapping GND vias, and clean silk.

The order matters and is load-bearing (learned the hard way on the flex-box build):
  1. ImportSpecctraSES                          -- pull freerouting's tracks/vias back in
  2. route_stragglers(b)                        -- close congested nets while back layers are empty
  3. F.Cu top GND pour (post-route)             -- so it never blocks freerouting's signal routing
  4. GND stitching vias (grid, collision-checked) -- tie the pours F<->B everywhere
  5. per-pad GND plane-tie vias (4-layer)       -- guarantee each SMD GND pad reaches the plane
  6. fill zones, then connectivity-GUARDED removal of redundant / too-close GND vias (JLC drill DFM)
  7. fix_silkscreen                             -- last, so it sees final pad/via positions

Every via we add is collision-checked against other-net pads and tracks, so a stitch can never short
a signal. Geometry guards (board bounds, no-via keepout voids) come from board_spec. Most of this is
board-agnostic; gated by spec flags (STITCH_GND, GND_PLANE_TIES, ADD_TOP_GND_POUR).

Runs under KiCad's bundled Python.
"""
import math
import pcbnew
import config
from fix_silk import fix_silkscreen, _shape_segs, _poly_pts
from route_fix import route_stragglers

spec = config.spec
P = config.BOARD_PCB
OX, OY = spec.ORIGIN
W, H = spec.W, spec.H
MARG = 3.0
mm = pcbnew.ToMM
HAS_GND = "GND" in spec.NETS

_VIA_VOIDS = [k["region"] for k in getattr(spec, "KEEPOUTS", [])
              if (not k.get("vias") or not k.get("copperpour")) and k.get("region")]


def _void(x, y):
    for poly in _VIA_VOIDS:
        inside = False
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if x < xint:
                    inside = not inside
        if inside:
            return True
    return False


b = pcbnew.LoadBoard(P)
print("SES import:", pcbnew.ImportSpecctraSES(b, config.SES))


def vec(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))


# 2. close congested stragglers NOW (back layers still nearly empty)
route_stragglers(b)

if not HAS_GND:
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(P, b)
    print("no GND net -> skipped pours/stitching; saved", P)
    raise SystemExit(0)

gnd = b.GetNetsByName()["GND"]
gnd_code = gnd.GetNetCode()

# 3. F.Cu top GND pour (added AFTER routing so it never blocks signal routing)
if getattr(spec, "ADD_TOP_GND_POUR", True):
    z = pcbnew.ZONE(b)
    z.SetLayer(pcbnew.F_Cu)
    z.SetNetCode(gnd_code)
    z.SetZoneName("GND_POUR_TOP")
    z.SetLocalClearance(pcbnew.FromMM(0.4))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(pcbnew.FromMM(0.5))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.6))
    z.SetMinThickness(pcbnew.FromMM(0.25))
    z.SetIsFilled(True)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    poly = z.Outline(); poly.NewOutline()
    for x, y in [(0, 0), (W, 0), (W, H), (0, H)]:
        poly.Append(vec(x, y).x, vec(x, y).y)
    b.Add(z)

MINCLR_TRK = 1.2
_trk = list(b.GetTracks())
_pad = [p for fp in b.GetFootprints() for p in fp.Pads()]

# Sample every silk outline so a stitch can't land on a silk ring -> "silkscreen on hole" at the fab.
_silk = []
for _fp in b.GetFootprints():
    for _it in _fp.GraphicalItems():
        if _it.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS) or _it.Type() != pcbnew.PCB_SHAPE_T:
            continue
        if _it.GetShape() == pcbnew.SHAPE_T_POLY:
            _pts = _poly_pts(_it)
        else:
            _pts = []
            for _x1, _y1, _x2, _y2 in (_shape_segs(_it) or []):
                _n = max(1, int(math.hypot(_x2 - _x1, _y2 - _y1) / 0.5))
                _pts += [(_x1 + (_x2 - _x1) * i / _n, _y1 + (_y2 - _y1) * i / _n) for i in range(_n + 1)]
        _silk += [(x - OX, y - OY) for x, y in _pts]
MINCLR_SILK = 0.6


def _segd(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _clear(px, py):
    if px < MARG or px > W - MARG or py < MARG or py > H - MARG or _void(px, py):
        return False
    for t in _trk:
        s, e = t.GetStart(), t.GetEnd()
        if _segd(px, py, mm(s.x) - OX, mm(s.y) - OY, mm(e.x) - OX, mm(e.y) - OY) < MINCLR_TRK:
            return False
    for p in _pad:
        q = p.GetPosition()
        pr = max(mm(p.GetSize().x), mm(p.GetSize().y), mm(p.GetDrillSize().x)) / 2.0
        if math.hypot(px - (mm(q.x) - OX), py - (mm(q.y) - OY)) < pr + 0.9:
            return False
    for sx, sy in _silk:
        if math.hypot(px - sx, py - sy) < MINCLR_SILK:
            return False
    return True


# 4. GND stitching vias on a grid (collision-checked)
_n = 0
if getattr(spec, "STITCH_GND", True):
    dx_grid, dy_grid = getattr(spec, "STITCH_PITCH", (9, 11))
    for gx in range(int(MARG + 2), int(W) - 2, int(dx_grid)):
        for gy in range(int(MARG + 2), int(H) - 2, int(dy_grid)):
            if _clear(float(gx), float(gy)):
                v = pcbnew.PCB_VIA(b)
                v.SetPosition(vec(gx, gy))
                v.SetDrill(pcbnew.FromMM(0.4)); v.SetWidth(pcbnew.FromMM(0.8))
                v.SetNetCode(gnd_code)
                b.Add(v); _n += 1
print(f"GND stitching vias placed: {_n}")

# 5. per-pad GND plane-tie vias (mainly 4-layer: tie each SMD GND pad to the solid inner plane)
_tie = 0
_skip_tie = []
if getattr(spec, "GND_PLANE_TIES", spec.LAYERS == 4):
    _smd_gnd = [p for p in _pad if p.GetNetCode() == gnd_code and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    _dirs = [(1, 0), (0, 1), (-1, 0), (0, -1), (0.71, 0.71), (-0.71, 0.71), (0.71, -0.71), (-0.71, -0.71)]

    def _trkpath_clear(x1, y1, x2, y2, selfpad):
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.15))
        pts = [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]
        for op in _pad:
            if op.this == selfpad.this or op.GetNetCode() == gnd_code:
                continue
            ox, oy = mm(op.GetPosition().x) - OX, mm(op.GetPosition().y) - OY
            orr = max(mm(op.GetSize().x), mm(op.GetSize().y), mm(op.GetDrillSize().x)) / 2.0
            if any(math.hypot(px - ox, py - oy) < orr + 0.35 for px, py in pts):
                return False
        for t in _trk:
            if t.GetNetCode() == gnd_code:
                continue
            if t.Type() == pcbnew.PCB_VIA_T:
                tx, ty = mm(t.GetPosition().x) - OX, mm(t.GetPosition().y) - OY
                if any(math.hypot(px - tx, py - ty) < mm(t.GetWidth(pcbnew.F_Cu)) / 2 + 0.35 for px, py in pts):
                    return False
            elif t.Type() == pcbnew.PCB_TRACE_T:
                s, e = t.GetStart(), t.GetEnd()
                ax, ay, bxx, byy = mm(s.x) - OX, mm(s.y) - OY, mm(e.x) - OX, mm(e.y) - OY
                if any(_segd(px, py, ax, ay, bxx, byy) < mm(t.GetWidth()) / 2 + 0.35 for px, py in pts):
                    return False
        return True

    for p in _smd_gnd:
        q = p.GetPosition(); cx, cy = mm(q.x) - OX, mm(q.y) - OY
        ph = max(mm(p.GetSize().x), mm(p.GetSize().y)) / 2.0
        play = p.GetLayer()
        done = False
        for rad in (ph + 0.75, ph + 1.05, ph + 1.4, ph + 1.8):
            for dx, dy in _dirs:
                vx, vy = cx + dx * rad, cy + dy * rad
                if vx < MARG or vx > W - MARG or vy < MARG or vy > H - MARG or _void(vx, vy):
                    continue
                VIA_R, CLR = 0.3, 0.25
                bad = False
                for op in _pad:
                    if op.this == p.this:
                        continue
                    oq = op.GetPosition()
                    orr = max(mm(op.GetSize().x), mm(op.GetSize().y), mm(op.GetDrillSize().x)) / 2.0
                    if math.hypot(vx - (mm(oq.x) - OX), vy - (mm(oq.y) - OY)) < orr + VIA_R + CLR:
                        bad = True; break
                if not bad:
                    for t in _trk:
                        if t.GetNetCode() == gnd_code:
                            continue
                        if t.Type() == pcbnew.PCB_VIA_T:
                            tp = t.GetPosition()
                            if math.hypot(vx - (mm(tp.x) - OX), vy - (mm(tp.y) - OY)) \
                                    < VIA_R + mm(t.GetWidth(pcbnew.F_Cu)) / 2.0 + CLR:
                                bad = True; break
                        elif t.Type() == pcbnew.PCB_TRACE_T:
                            s, e = t.GetStart(), t.GetEnd()
                            if _segd(vx, vy, mm(s.x) - OX, mm(s.y) - OY, mm(e.x) - OX, mm(e.y) - OY) \
                                    < VIA_R + mm(t.GetWidth()) / 2.0 + CLR:
                                bad = True; break
                if bad:
                    continue
                v = pcbnew.PCB_VIA(b); v.SetPosition(vec(vx, vy))
                v.SetDrill(pcbnew.FromMM(0.3)); v.SetWidth(pcbnew.FromMM(0.6))
                v.SetNetCode(gnd_code); b.Add(v)
                if _trkpath_clear(cx, cy, vx, vy, p):
                    tk = pcbnew.PCB_TRACK(b); tk.SetStart(vec(cx, cy)); tk.SetEnd(vec(vx, vy))
                    tk.SetWidth(pcbnew.FromMM(0.3)); tk.SetLayer(play); tk.SetNetCode(gnd_code); b.Add(tk)
                _tie += 1; done = True; break
            if done:
                break
        if not done:
            _skip_tie.append(p.GetParentFootprint().GetReference() + "." + p.GetPadName())
    print(f"per-pad GND plane-tie vias: {_tie} (of {len(_smd_gnd)} SMD GND pads); "
          f"no-via (rely on pour): {_skip_tie}")

# congested/edge connector GND pads -> SOLID zone connection (thermal relief can't form spokes there)
for fp in b.GetFootprints():
    if fp.GetReference() in set(getattr(spec, "SOLID_GND_CONN", [])):
        for p in fp.Pads():
            if p.GetNetCode() == gnd_code:
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

# fill all zones first (so the connectivity guard below sees GND pads grounded via the pour)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())

# 6a. remove freerouting's redundant GND down-vias sitting on/next to a GND pad (JLC via-to-pad).
#     CONNECTIVITY-GUARDED: only drop a via if GND stays fully connected without it.
_gpads = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetCode() == gnd_code]


def _unconn():
    b.BuildConnectivity()
    return b.GetConnectivity().GetUnconnectedCount(False)


_base = _unconn(); _rm = 0
for v in list(b.GetTracks()):
    if v.Type() != pcbnew.PCB_VIA_T or v.GetNetCode() != gnd_code:
        continue
    vp = v.GetPosition(); vr = mm(v.GetWidth(pcbnew.F_Cu)) / 2.0
    near = False
    for p in _gpads:
        pp = p.GetPosition()
        d = math.hypot(mm(vp.x) - mm(pp.x), mm(vp.y) - mm(pp.y))
        pr = max(mm(p.GetSize().x), mm(p.GetSize().y)) / 2.0
        if d - vr - pr < 0.30:
            near = True; break
    if not near:
        continue
    b.Remove(v)
    if _unconn() > _base:
        b.Add(v)
    else:
        _rm += 1
print(f"removed redundant GND-at-pad vias: {_rm}")

# 6b. drill DFM: two holes closer than ~0.15mm edge-to-edge read as a 0-width slot / PTH-spacing
#     DANGER. Drop the redundant one of any too-close GND via pair, CONNECTIVITY-GUARDED.
def _all_holes(exclude=None):
    hs = []
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T and t is not exclude:
            q = t.GetPosition(); hs.append((mm(q.x), mm(q.y), mm(t.GetDrill()) / 2.0))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetDrillSizeX() > 0:
                q = p.GetPosition(); hs.append((mm(q.x), mm(q.y), mm(p.GetDrillSizeX()) / 2.0))
    return hs


_dedup = 0
for v in list(b.GetTracks()):
    if v.Type() != pcbnew.PCB_VIA_T or v.GetNetCode() != gnd_code:
        continue
    vp = v.GetPosition(); vr = mm(v.GetDrill()) / 2.0
    others = _all_holes(exclude=v)
    if not any(math.hypot(mm(vp.x) - hx, mm(vp.y) - hy) - vr - hr < 0.15 for hx, hy, hr in others):
        continue
    b.Remove(v)
    if _unconn() > _base:
        b.Add(v)
    else:
        _dedup += 1
print(f"removed overlapping/too-close GND vias: {_dedup}")

# re-fill to close the small voids left where vias were removed
pcbnew.ZONE_FILLER(b).Fill(b.Zones())

# 7. silk DFM cleanup (runs last so it sees every footprint's final pad position)
fix_silkscreen(b)

pcbnew.SaveBoard(P, b)

try:
    trk = list(b.GetTracks())
    tracks = [t for t in trk if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in trk if t.Type() == pcbnew.PCB_VIA_T]
    print(f"tracks: {len(tracks)}, vias: {len(vias)} (incl. stitching), zones: {b.GetAreaCount()}")
except Exception as e:
    print(f"(track-count diagnostic skipped: {e}); zones: {b.GetAreaCount()}")

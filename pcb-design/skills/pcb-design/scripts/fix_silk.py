"""DFM silkscreen cleanup for JLCPCB. Fixes the three flags their Gerber DFM check raises:
  1. Silkscreen line width  -> bump every silk stroke / text thickness below MIN_W to MIN_W.
  2. Silkscreen to pad        -> trim silk that comes within CLR of pad copper (same side).
  3. Silkscreen to hole       -> trim silk that comes within CLR of any drilled hole/via (both sides).

Why a geometric pass and not a source edit: most silk comes from stock KiCad library footprints
loaded verbatim by gen_pcb.py, so it can't be cleaned at the source. This runs in pcbnew, which
knows every pad's real position (rotation applied), copper extent and drill, so it measures actual
clearances instead of guessing.

What it does NOT touch:
  - Filled polygons (logos, SHAPE_T_POLY width 0): left intact; the fab punches a clearance ring
    around any hole/pad they cross, which is normal and not a hard error.
  - Value fields on F.Fab (wrong layer). Reference fields ON silk ARE handled (width + declutter).
  - Functional silk text labels: only their stroke thickness is bumped; positions kept (they were
    placed in clear margins on purpose), unless a glyph actually collides -> then slid clear.

Curves (circles/arcs) that violate are removed whole rather than polygonised; straight outlines
(segments + rects) are trimmed into their clear runs so most of the outline survives.

Board bounds / silk-exclusion voids come from board_spec (config). Run standalone on the current
board (KiCad must be CLOSED):  <kicad_python> fix_silk.py
Also called at the end of import_ses.py so a full build_routed.sh run stays clean.
"""
import math
import pcbnew
import config

spec = config.spec
OX, OY = spec.ORIGIN
BW, BH = spec.W, spec.H
MARGIN = 1.0                 # keep relocated text this far inside the board edge
# silk-exclusion voids: any spec.KEEPOUTS entry flagged {"silk": True} (e.g. a board notch)
VOIDS = [k["region"] for k in getattr(spec, "KEEPOUTS", []) if k.get("silk") and k.get("region")]

MIN_W   = 0.20    # mm  - silkscreen line / text width (JLC min ~0.153; 0.20 = recommended)
CLR     = 0.20    # mm  - target clearance from silk EDGE to pad/hole/via EDGE (JLC min 0.15 + margin)
STEP    = 0.10    # mm  - sampling pitch along a segment when trimming
MIN_RUN = 0.40    # mm  - discard trimmed silk fragments shorter than this (slivers)

FromMM = pcbnew.FromMM
ToMM   = pcbnew.ToMM
_FIELD_T = getattr(pcbnew, "PCB_FIELD_T", None)


def _in_void(cx, cy):
    """True if board-local (cx,cy) is outside the board margin or inside a silk-exclusion void."""
    if cx < MARGIN or cx > BW - MARGIN or cy < MARGIN or cy > BH - MARGIN:
        return True
    for poly in VOIDS:
        inside = False
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if (y1 > cy) != (y2 > cy):
                xint = x1 + (cy - y1) * (x2 - x1) / (y2 - y1)
                if cx < xint:
                    inside = not inside
        if inside:
            return True
    return False


def _obstacles(board):
    """(front_cu, back_cu, holes): lists of (x_mm, y_mm, radius_mm) circles. Pads approximated by
    enclosing circle (conservative). Holes apply to both silk sides (drill goes through); copper
    applies per side. Vias count as holes (JLC 'silkscreen to hole' includes them)."""
    front, back, holes = [], [], []
    round_shapes = (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            x, y = ToMM(pos.x), ToMM(pos.y)
            sz = p.GetSize()
            w, h = ToMM(sz.x), ToMM(sz.y)
            pr = (max(w, h) / 2.0) if p.GetShape() in round_shapes else (math.hypot(w, h) / 2.0)
            dr = p.GetDrillSize()
            hr = max(ToMM(dr.x), ToMM(dr.y)) / 2.0
            if hr > 0:
                holes.append((x, y, hr))
            if pr > 0 and p.IsOnLayer(pcbnew.F_Cu):
                front.append((x, y, pr))
            if pr > 0 and p.IsOnLayer(pcbnew.B_Cu):
                back.append((x, y, pr))
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            pos = t.GetPosition()
            try:
                cr = ToMM(t.GetWidth(pcbnew.F_Cu)) / 2.0
            except Exception:
                cr = ToMM(t.GetDrill()) / 2.0
            holes.append((ToMM(pos.x), ToMM(pos.y), cr))
    return front, back, holes


def _hit(x, y, half, obs):
    for ox, oy, r in obs:
        if math.hypot(x - ox, y - oy) < r + half + CLR:
            return True
    return False


def _arc_pts(it):
    c = it.GetCenter(); s = it.GetStart(); e = it.GetEnd()
    cx, cy = ToMM(c.x), ToMM(c.y)
    sx, sy = ToMM(s.x), ToMM(s.y)
    ex, ey = ToMM(e.x), ToMM(e.y)
    r = math.hypot(sx - cx, sy - cy)
    a0 = math.atan2(sy - cy, sx - cx)
    try:
        m = it.GetArcMid(); mx, my = ToMM(m.x), ToMM(m.y)
    except Exception:
        mx, my = (sx + ex) / 2.0, (sy + ey) / 2.0
    v0 = (sx - cx, sy - cy); vm = (mx - cx, my - cy); ve = (ex - cx, ey - cy)
    d_mid = math.atan2(v0[0] * vm[1] - v0[1] * vm[0], v0[0] * vm[0] + v0[1] * vm[1])
    d_end = math.atan2(v0[0] * ve[1] - v0[1] * ve[0], v0[0] * ve[0] + v0[1] * ve[1])
    if d_mid >= 0 and d_end < 0:
        d_end += 2 * math.pi
    elif d_mid < 0 and d_end > 0:
        d_end -= 2 * math.pi
    n = max(8, int(abs(d_end) * r / 0.3))
    return [(cx + r * math.cos(a0 + d_end * k / n),
             cy + r * math.sin(a0 + d_end * k / n)) for k in range(n + 1)]


def _poly_pts(it):
    pts = []
    poly = it.GetPolyShape()
    for oi in range(poly.OutlineCount()):
        o = poly.Outline(oi)
        for pi in range(o.PointCount()):
            p = o.CPoint(pi)
            pts.append((ToMM(p.x), ToMM(p.y)))
    return pts


def _text_glyph_pts(it):
    ps = pcbnew.SHAPE_POLY_SET()
    it.TransformTextToPolySet(ps, 0, FromMM(0.02), pcbnew.ERROR_INSIDE)
    pts = []
    for oi in range(ps.OutlineCount()):
        o = ps.Outline(oi)
        pts += [(ToMM(o.CPoint(k).x), ToMM(o.CPoint(k).y)) for k in range(o.PointCount())]
    return pts


def _pts_clear(pts, obs, half=0.0):
    for x, y in pts:
        for ox, oy, r in obs:
            if math.hypot(x - ox, y - oy) - r - half < CLR:
                return False
    return True


def _declutter_text(it, obs):
    """If a text's glyphs come within CLR of a pad/hole/via, slide the whole label to the nearest
    spot that clears everything and stays on the board (off any silk void). Returns True if moved."""
    pts = _text_glyph_pts(it)
    if not pts or _pts_clear(pts, obs):
        return False
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    w2, h2 = (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0
    cx = (max(xs) + min(xs)) / 2.0; cy = (max(ys) + min(ys)) / 2.0
    for dist in [d * 0.1 for d in range(1, 61)]:          # search out to 6 mm
        for ang in range(0, 360, 10):
            dx = dist * math.cos(math.radians(ang))
            dy = dist * math.sin(math.radians(ang))
            nlx, nly = cx + dx - OX, cy + dy - OY            # board-local new bbox centre
            if _in_void(nlx - w2, nly) or _in_void(nlx + w2, nly) or \
               _in_void(nlx, nly - h2) or _in_void(nlx, nly + h2):
                continue
            if _pts_clear([(x + dx, y + dy) for x, y in pts], obs):
                it.Move(pcbnew.VECTOR2I(FromMM(dx), FromMM(dy)))
                return True
    return False


def _shape_segs(it):
    s = it.GetShape()
    a, b = it.GetStart(), it.GetEnd()
    ax, ay, bx, by = ToMM(a.x), ToMM(a.y), ToMM(b.x), ToMM(b.y)
    if s == pcbnew.SHAPE_T_SEGMENT:
        return [(ax, ay, bx, by)]
    if s == pcbnew.SHAPE_T_RECT:
        return [(ax, ay, bx, ay), (bx, ay, bx, by), (bx, by, ax, by), (ax, by, ax, ay)]
    if s == pcbnew.SHAPE_T_CIRCLE:
        c = it.GetCenter(); cx, cy = ToMM(c.x), ToMM(c.y)
        r = math.hypot(ax - cx, ay - cy)
        n = max(24, int(2 * math.pi * r / 0.3))
        pts = [(cx + r * math.cos(2 * math.pi * k / n),
                cy + r * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
        return [(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1]) for k in range(n)]
    if s == pcbnew.SHAPE_T_ARC:
        pts = _arc_pts(it)
        return [(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1]) for k in range(len(pts) - 1)]
    return None


def _clip_seg(x1, y1, x2, y2, half, obs):
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return [] if _hit(x1, y1, half, obs) else [(x1, y1, x2, y2)]
    n = max(1, int(math.ceil(length / STEP)))
    clear = []
    for i in range(n + 1):
        t = i / n
        px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        clear.append((px, py, not _hit(px, py, half, obs)))
    runs, i = [], 0
    while i <= n:
        if clear[i][2]:
            j = i
            while j + 1 <= n and clear[j + 1][2]:
                j += 1
            ax, ay = clear[i][0], clear[i][1]
            bx, by = clear[j][0], clear[j][1]
            if math.hypot(bx - ax, by - ay) >= MIN_RUN:
                runs.append((ax, ay, bx, by))
            i = j + 1
        else:
            i += 1
    return runs


def _same(run, seg):
    tol = STEP * 0.01
    return (math.hypot(run[0] - seg[0], run[1] - seg[1]) < tol and
            math.hypot(run[2] - seg[2], run[3] - seg[3]) < tol)


def fix_silkscreen(board, verbose=True):
    front, back, holes = _obstacles(board)
    silk_layers = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    min_w_iu = FromMM(MIN_W)

    items = [(it, fp) for fp in board.GetFootprints() for it in fp.GraphicalItems()]
    items += [(it, None) for it in board.GetDrawings()]
    try:
        for fp in board.GetFootprints():
            for fld in fp.GetFields():
                if fld.IsVisible() and fld.GetLayer() in silk_layers:
                    items.append((fld, fp))
    except Exception as e:
        print(f"  (silk field declutter skipped: {e})")

    bumped = clipped = removed = nudged = 0
    to_remove, to_add = [], []

    for it, fp in items:
        layer = it.GetLayer()
        if layer not in silk_layers:
            continue
        t = it.Type()

        if t == pcbnew.PCB_TEXT_T or (_FIELD_T is not None and t == _FIELD_T):
            if it.GetTextThickness() < min_w_iu:
                it.SetTextThickness(min_w_iu)
                bumped += 1
            side_obs = (front if layer == pcbnew.F_SilkS else back) + holes
            if _declutter_text(it, side_obs):
                nudged += 1
            continue
        if t != pcbnew.PCB_SHAPE_T:
            continue
        side_obs = (front if layer == pcbnew.F_SilkS else back) + holes

        if it.GetShape() == pcbnew.SHAPE_T_POLY:
            w = it.GetWidth()
            if w == 0:
                continue
            half = ToMM(w) / 2.0
            if any(_hit(x, y, half, side_obs) for x, y in _poly_pts(it)):
                to_remove.append((it, fp)); removed += 1
            elif w < min_w_iu:
                it.SetWidth(min_w_iu); bumped += 1
            continue

        if it.GetWidth() < min_w_iu:
            it.SetWidth(min_w_iu); bumped += 1
        half = ToMM(it.GetWidth()) / 2.0

        segs = _shape_segs(it)
        if segs is None:
            continue

        if it.GetShape() in (pcbnew.SHAPE_T_CIRCLE, pcbnew.SHAPE_T_ARC):
            if any(_hit(x1, y1, half, side_obs) for x1, y1, _, _ in segs) or \
               _hit(segs[-1][2], segs[-1][3], half, side_obs):
                to_remove.append((it, fp)); removed += 1
            continue

        frags, changed = [], False
        for seg in segs:
            runs = _clip_seg(seg[0], seg[1], seg[2], seg[3], half, side_obs)
            if not (len(runs) == 1 and _same(runs[0], seg)):
                changed = True
            frags.extend(runs)
        if changed:
            to_remove.append((it, fp))
            w = max(ToMM(it.GetWidth()), MIN_W)
            for fx1, fy1, fx2, fy2 in frags:
                to_add.append((layer, w, fx1, fy1, fx2, fy2))
            if frags:
                clipped += 1
            else:
                removed += 1

    for it, fp in to_remove:
        (fp if fp is not None else board).Remove(it)
    for layer, w, x1, y1, x2, y2 in to_add:
        ns = pcbnew.PCB_SHAPE(board)
        ns.SetShape(pcbnew.SHAPE_T_SEGMENT)
        ns.SetLayer(layer)
        ns.SetWidth(FromMM(w))
        ns.SetStart(pcbnew.VECTOR2I(FromMM(x1), FromMM(y1)))
        ns.SetEnd(pcbnew.VECTOR2I(FromMM(x2), FromMM(y2)))
        board.Add(ns)

    if verbose:
        print(f"silk DFM: width-bumped {bumped}, trimmed {clipped} outlines "
              f"(+{len(to_add)} clear fragments), removed {removed} colliding shapes, "
              f"nudged {nudged} text labels off pads/holes")
    return bumped, clipped, removed, nudged


if __name__ == "__main__":
    b = pcbnew.LoadBoard(config.BOARD_PCB)
    fix_silkscreen(b)
    pcbnew.SaveBoard(config.BOARD_PCB, b)
    print("saved", config.BOARD_PCB)

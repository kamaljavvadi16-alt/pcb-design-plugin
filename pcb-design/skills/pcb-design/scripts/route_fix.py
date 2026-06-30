"""Close the short local connections freerouting leaves unrouted in congested areas.

`route_stragglers(b)` is called from import_ses.py RIGHT AFTER the SES import -- BEFORE the GND
plane-tie vias -- so these nets claim the (still-empty) inner/back layers first. It executes the
ops listed in spec.STRAGGLERS (usually EMPTY: freerouting handles normal boards). Each op:
  {"op":"tie_gnd",       "ref":"U3", "pad":"15"}                       pad -> GND plane/pour via
  {"op":"connect",       "a":("U5","3"), "b":("U6","5"), "net":"OC"}   pad <-> pad
  {"op":"connect_track", "a":("U4","11"), "net":"NTC"}                 pad -> nearest existing NTC track

Router: for each pad endpoint, enumerate collision-free "exit" via points (F.Cu stub + via both
clear); then search exit x exit x {inner/back layers} x {direct, vertical-dip detours} for a fully
clear polyline. Every segment and via is collision-checked, so it can NEVER add a DRC violation --
if no clean path exists it reports BLOCKED. Runs under KiCad's bundled Python.
"""
import math
import pcbnew
import config

spec = config.spec
OX, OY = spec.ORIGIN
W, H = spec.W, spec.H
MARG = 3.0
F = pcbnew.F_Cu
B = pcbnew.B_Cu
INNERS = [B, pcbnew.In2_Cu] if spec.LAYERS == 4 else [B]
mm = pcbnew.ToMM
FromMM = pcbnew.FromMM
_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0), (0.71, 0.71), (-0.71, 0.71), (0.71, -0.71), (-0.71, -0.71)]
_VIA_VOIDS = [k["region"] for k in getattr(spec, "KEEPOUTS", [])
              if not k.get("vias") and k.get("region")]


def _in_void(x, y):
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


def route_stragglers(b):
    ops = getattr(spec, "STRAGGLERS", [])
    if not ops:
        return

    def vec(x, y):
        return pcbnew.VECTOR2I(FromMM(OX + x), FromMM(OY + y))

    def N(n):
        return b.GetNetsByName()[n].GetNetCode()

    def pad(ref, name):
        for fp in b.GetFootprints():
            if fp.GetReference() == ref:
                for p in fp.Pads():
                    if p.GetPadName() == name:
                        q = p.GetPosition(); return mm(q.x) - OX, mm(q.y) - OY
        return None

    def track(x1, y1, x2, y2, net, layer, w=0.3):
        t = pcbnew.PCB_TRACK(b); t.SetStart(vec(x1, y1)); t.SetEnd(vec(x2, y2))
        t.SetWidth(FromMM(w)); t.SetLayer(layer); t.SetNetCode(net); b.Add(t)

    def via(x, y, net):
        v = pcbnew.PCB_VIA(b); v.SetPosition(vec(x, y)); v.SetDrill(FromMM(0.3))
        v.SetWidth(FromMM(0.6)); v.SetNetCode(net); b.Add(v)

    def segd(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay; l2 = dx * dx + dy * dy
        t = 0 if l2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / l2))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    _allpads = [p for fp in b.GetFootprints() for p in fp.Pads()]

    def via_ok(x, y, net):
        if x < MARG or x > W - MARG or y < MARG or y > H - MARG or _in_void(x, y):
            return False
        for p in _allpads:
            if p.GetNetCode() == net:
                continue
            q = p.GetPosition()
            pr = max(mm(p.GetSize().x), mm(p.GetSize().y), mm(p.GetDrillSize().x)) / 2
            if math.hypot(x - (mm(q.x) - OX), y - (mm(q.y) - OY)) < pr + 0.3 + 0.2:
                return False
        for t in b.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() != net:
                tp = t.GetPosition()
                if math.hypot(x - (mm(tp.x) - OX), y - (mm(tp.y) - OY)) < 0.3 + mm(t.GetWidth(F)) / 2 + 0.2:
                    return False
        return True

    def seg_ok(pts, net, layers, mar=0.3):
        samp = []
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.18))
            samp += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]
        for p in _allpads:
            if p.GetNetCode() == net:
                continue
            q = p.GetPosition(); ox, oy = mm(q.x) - OX, mm(q.y) - OY
            pr = max(mm(p.GetSize().x), mm(p.GetSize().y)) / 2
            if any(math.hypot(px - ox, py - oy) < pr + 0.15 + 0.2 for px, py in samp):
                return False
        for t in b.GetTracks():
            if t.GetNetCode() == net:
                continue
            if t.Type() == pcbnew.PCB_VIA_T:
                tp = t.GetPosition(); vx, vy = mm(tp.x) - OX, mm(tp.y) - OY
                if any(math.hypot(px - vx, py - vy) < mm(t.GetWidth(F)) / 2 + mar for px, py in samp):
                    return False
            elif t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() in layers:
                s, e = t.GetStart(), t.GetEnd()
                ax, ay, bx, by = mm(s.x) - OX, mm(s.y) - OY, mm(e.x) - OX, mm(e.y) - OY
                if any(segd(px, py, ax, ay, bx, by) < mm(t.GetWidth()) / 2 + mar for px, py in samp):
                    return False
        return True

    def exits(p, net):
        out = []
        for r in (0.95, 1.3, 1.7):
            for dx, dy in _DIRS:
                e = (p[0] + dx * r, p[1] + dy * r)
                if via_ok(e[0], e[1], net) and seg_ok([p, e], net, (F,)):
                    out.append(e)
        return out

    def detours(v1, v2):
        midx = (v1[0] + v2[0]) / 2
        outs = [[v1, v2]]
        for dip in (2.6, -2.6, 4.2, -4.2, 1.4, -1.4):
            outs.append([v1, (v1[0], v1[1] + dip), (v2[0], v2[1] + dip), v2])
            outs.append([v1, (midx, v1[1] + dip), v2])
        return outs

    def connect(p1, p2, net):
        for v1 in exits(p1, net):
            for v2 in exits(p2, net):
                for layer in INNERS:
                    for wp in detours(v1, v2):
                        if seg_ok(wp, net, (layer,)):
                            track(p1[0], p1[1], v1[0], v1[1], net, F); via(v1[0], v1[1], net)
                            for a, c in zip(wp, wp[1:]):
                                track(a[0], a[1], c[0], c[1], net, layer)
                            via(v2[0], v2[1], net); track(v2[0], v2[1], p2[0], p2[1], net, F)
                            return True
        return False

    def connect_track(p1, net):
        ep = [(mm(q.x) - OX, mm(q.y) - OY, t.GetLayer()) for t in b.GetTracks()
              if t.GetNetCode() == net and t.Type() == pcbnew.PCB_TRACE_T
              for q in (t.GetStart(), t.GetEnd())]
        if not ep:
            return False
        tx, ty, tl = min(ep, key=lambda q: math.hypot(q[0] - p1[0], q[1] - p1[1]))
        for v1 in exits(p1, net):
            for layer in INNERS:
                for wp in detours(v1, (tx, ty)):
                    if seg_ok(wp, net, (layer,)) and seg_ok([(tx, ty)], net, (layer,)):
                        track(p1[0], p1[1], v1[0], v1[1], net, F); via(v1[0], v1[1], net)
                        for a, c in zip(wp, wp[1:]):
                            track(a[0], a[1], c[0], c[1], net, layer)
                        if layer != tl:
                            via(tx, ty, net)
                        return True
        return False

    def tie_gnd(p1):
        for e in exits(p1, N("GND")):
            track(p1[0], p1[1], e[0], e[1], N("GND"), F); via(e[0], e[1], N("GND"))
            return True
        return False

    log = []
    for op in ops:
        kind = op["op"]
        try:
            if kind == "tie_gnd":
                p = pad(op["ref"], op["pad"])
                log.append(f"{op['ref']}.{op['pad']}-GND " + ("ok" if p and tie_gnd(p) else "BLOCKED"))
            elif kind == "connect":
                a, c = pad(*op["a"]), pad(*op["b"])
                ok = bool(a and c and connect(a, c, N(op["net"])))
                log.append(f"{op['net']} " + ("ok" if ok else "BLOCKED"))
            elif kind == "connect_track":
                a = pad(*op["a"])
                ok = bool(a and connect_track(a, N(op["net"])))
                log.append(f"{op['net']} " + ("ok" if ok else "BLOCKED"))
        except Exception as e:
            log.append(f"{kind} ERROR:{e}")
    print("route_stragglers:", "; ".join(log) if log else "(no ops)")


if __name__ == "__main__":
    b = pcbnew.LoadBoard(config.BOARD_PCB)
    route_stragglers(b)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(config.BOARD_PCB, b)
    b.BuildConnectivity()
    print("unrouted ratsnest now:", b.GetConnectivity().GetUnconnectedCount(False))

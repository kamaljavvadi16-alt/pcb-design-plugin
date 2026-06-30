"""Move the footprints in spec.FLIP_TO_BACK to the BOTTOM of the board.

Runs AFTER gen_pcb.py and BEFORE export_dsn.py, so freerouting routes with them already on the
back. pcbnew's Flip() gets the layer swap AND the mirror right (hand-editing the layer text would
leave silk un-mirrored). THT parts keep their pads on all copper layers (nets unchanged); flipping
just puts the body/silk on the back. Silk-only items (e.g. a back logo) just move to B.SilkS.

Runs under KiCad's bundled Python (imports pcbnew).
"""
import pcbnew
import config

spec = config.spec
P = config.BOARD_PCB
FLIP = set(getattr(spec, "FLIP_TO_BACK", []))

b = pcbnew.LoadBoard(P)
done = []
if FLIP:
    for fp in b.GetFootprints():
        if fp.GetReference() in FLIP and fp.GetLayer() != pcbnew.B_Cu:
            fp.Flip(fp.GetPosition(), False)   # to back; mirror up-down so silk reads upright
            done.append(fp.GetReference())
pcbnew.SaveBoard(P, b)
print("flipped to back:", sorted(done) if done else "(none)")

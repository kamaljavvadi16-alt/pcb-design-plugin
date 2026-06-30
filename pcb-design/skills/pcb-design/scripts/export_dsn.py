"""Export the board to Specctra DSN for freerouting.

For a 4-layer board with a solid inner GND plane, KiCad exports every layer as `(type signal)`,
which would let freerouting lay signal traces on the GND plane. We rewrite spec.GND_PLANE_LAYER to
`(type power)` so freerouting routes signals only on the other copper layers, while still letting
GND vias drop onto the plane (a power layer keeps its plane + accepts vias; a keepout would not).
2-layer boards (or 4-layer with no GND plane) skip the rewrite.

Runs under KiCad's bundled Python (imports pcbnew).
"""
import pcbnew
import config

spec = config.spec
b = pcbnew.LoadBoard(config.BOARD_PCB)
ok = pcbnew.ExportSpecctraDSN(b, config.DSN)
print("DSN export:", ok, "->", config.DSN)

plane = getattr(spec, "GND_PLANE_LAYER", None)
if spec.LAYERS == 4 and plane:
    raw = open(config.DSN, encoding="utf-8").read()
    marker = f"(layer {plane}\n      (type signal)"
    if marker in raw:
        raw = raw.replace(marker, f"(layer {plane}\n      (type power)", 1)
        open(config.DSN, "w", encoding="utf-8", newline="\n").write(raw)
        print(f"{plane} set to type=power (GND plane, excluded from signal routing)")
    else:
        print(f"WARNING: '{plane}' signal-layer block not found in DSN — plane NOT excluded "
              f"(DSN format change?). Routing may place signals on the plane.")

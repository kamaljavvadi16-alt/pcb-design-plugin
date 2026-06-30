# Electrical & layout design rules

Board-agnostic design judgement, distilled from real multi-revision hardware. Map each to a
`board_spec.py` field where relevant.

## Power tree & decoupling
- **Think in rails.** Draw power in → protection → regulation → each load. Know the current on every
  rail; it sets trace width and via count.
- **Bulk reservoir at the regulator output.** A big cap (e.g. 100–470 µF) within ~10 mm of the output
  pin/load is the anti-brownout reservoir. On a battery board, an undersized/distant bulk cap browns
  out the MCU on RF/load transients — placement *is* the function.
- **Decoupling at every IC.** 0.1 µF (+ a 1–10 µF) right at each VDD pin, shortest possible loop to
  GND. Put it in the spec next to the IC, not "nearby".
- **Net classes.** Signal default ~0.25 mm track / 0.7-0.3 via (0.2 mm annular). Power nets wider:
  set `POWER_TRACK`/`POWER_VIA` and list the high-current nets in `POWER_NETS`. Sanity-check with
  `track_widths.py` after routing (power nets should show the wide width).
- **Current ↔ width (1 oz Cu, ~10 °C rise, rule of thumb):** 0.25 mm ≈ 0.5 A, 0.5 mm ≈ 1 A,
  0.8 mm ≈ 2 A, 1.5 mm ≈ 3 A. Widen and/or parallel-via for more; don't rely on a thin trace + pour.

## Ground: planes and stitching
- **2-layer:** pour GND on both layers and stitch them together with vias so the return path is
  continuous; `import_ses.py` does this (`STITCH_GND`). Avoid splitting the ground under signals.
- **4-layer:** make a **solid inner GND plane** (`GND_PLANE_LAYER = "In1.Cu"`); it's the clean return
  path for switchers and the RF module. `export_dsn.py` marks it `type power` so the autorouter won't
  lay signals on it; `import_ses.py` ties every SMD GND pad to it (`GND_PLANE_TIES`) and stitches.
- **Don't route across a plane split.** A signal whose return current can't follow it underneath
  radiates and couples. Keep the reference plane continuous under fast/sensitive nets.

## Switching regulators (buck / boost / buck-boost / switch-mode charger)
- **Minimise the hot loop.** The loop {input cap → switch → inductor → output cap → back to cap GND}
  must be physically tiny. Large loop area = EMI + ringing + instability.
- **Hand-route the loop.** Pre-place the LX/inductor/Cin/Cout copper as `SEGMENTS`/`VIAS` in the spec
  and route those by hand; freerouting optimises for completion, not loop area. Let it do the signals.
- **Cin/Cout hard against the IC pins.** Feedback (FB) trace routed away from the switch node; tie the
  IC thermal pad (EP) straight down to the GND plane with vias.
- **Keep inductors away from antennas** and sensitive analog.

## RF (PCB/chip antenna, modules like ESP32-WROOM)
- **Antenna keepout on ALL layers.** No copper pour, tracks, or vias under or beside the antenna —
  a plane under a PCB antenna detunes/kills it. Encode as a `KEEPOUTS` entry with
  `copperpour: False, tracks: False, vias: False` and list every copper layer.
- **Antenna at a board edge**, pointing off the board, ≥ ~15 mm of clearance to metal (battery,
  shields, enclosure metal).
- The ESP32-WROOM footprint ships an oversize antenna courtyard + a fragmented thermal EP;
  `gen_pcb.py`'s `load_fp` strips the bogus courtyard and merges the EP into one GND pad — keep that
  fixup when using WROOM.

## Connectors, mechanical, edges
- **THT pad ≥ 3 mm from any SMD pad** (`THT_SMD_MIN`) so hand/wave assembly can't bridge onto SMD.
- Mounting holes: non-plated, sized to the screw (e.g. M2 → 2.2 mm); keep copper/pours clear.
- Edge clearance: copper ≥ 0.3 mm from the board outline (`EDGE_CLEARANCE`).
- For board cutouts/notches, define a custom `EDGE` outline and (if it's a void) a matching `KEEPOUT`
  with `"silk": True` so silk relocation avoids it.

## Silk & brand logos
- Functional silk: connector pinouts, polarity marks, a "⚠" for any do-this-or-damage rule, the board
  name/rev. Keep text in clear margins; `fix_silk.py` bumps thin lines and slides text off pads/holes.
- **Brand logos:** convert a PNG → a 1-bit silkscreen *footprint* in KiCad (Image Converter /
  bitmap2component → export as `*.kicad_mod`), then size it with `make_logo.py` and reference it from
  `board_spec.LOGO`. Don't try to approximate a logo with text.

## Layer stackup quick guide
- **2-layer:** signal+pour / signal+pour. Fine up to moderate density, low speed.
- **4-layer (recommended for power/RF):** L1 signal · L2 solid GND plane · L3 signal+power fills ·
  L4 signal+GND fill. Stitch GND L2↔L4. This is the default for any switching or RF design.

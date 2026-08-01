# pcb-design scripts — the toolchain

Board-agnostic KiCad toolchain: describe a board in **`board_spec.py`**, and these scripts generate
the layout, autoroute it, gate it for DFM, and export a JLCPCB fab package. Copy this whole directory
into your project's `hardware/<board>/_tools/`, then edit `board_spec.py`.

## Layout it expects
```
hardware/<board>/
  <board>.kicad_pcb / .kicad_sch / .kicad_pro   (generated)
  fab/                                          (gerbers + BOM/CPL land here)
  _tools/                                       (THIS dir: scripts + board_spec.py + freerouting.jar)
```
`config.py` derives all paths from `board_spec.NAME` and this dir's location.

## Two Pythons
- **System Python** runs the pure text/JSON generators: `gen_pcb.py`, `gen_sch.py`, `set_netclasses.py`.
- **KiCad's bundled Python** runs everything that imports `pcbnew`: `export_dsn.py`, `import_ses.py`,
  `flip_back.py`, `fix_silk.py`, `route_fix.py`, `gen_bom_cpl.py`, and all `check_*.py`.
- `build_routed.sh`/`export_fab.sh` call the right one for each step. Get the KiCad-python path from
  `python config.py`. **Close the KiCad GUI** before building (it locks the board).

## Requirements
KiCad (kicad-cli + bundled python with pcbnew), **Java** (for `freerouting.jar`, bundled here),
a POSIX shell (git-bash on Windows). `config.py` auto-detects KiCad; override with `KICAD_DIR`.

## Files
**Config / spec / preflight**
- `check_prereqs.py` — **preflight**. Verifies KiCad CLI, KiCad's pcbnew Python, Java, the bundled
  `freerouting.jar`, and `board_spec.py`; prints PASS/MISSING + exact fixes (read-only). Run on a new
  machine before anything else. `--install` offers to install each missing prereq via the platform
  package manager (winget/brew/apt/dnf/pacman), **prompting `[y/N]` before every install**. Non-zero
  exit if any prereq is missing — `build_routed.sh` runs it first and aborts early on failure.
- `config.py` — locates KiCad + freerouting, derives board paths, builds the gerber layer list, and
  provides `default_pro()` (a minimal `.kicad_pro` so no GUI bootstrap is needed). KiCad detection is
  independent of the board spec (so the preflight works before a board exists; `PCB_SKIP_SPEC=1`
  tolerates a missing `board_spec.py`). `--sh` emits shell vars for the build scripts; `python
  config.py` prints a diagnostic.
- `board_spec.example.py` — the schema + a complete example board (2-layer regulator breakout). Copy
  to `board_spec.py` and edit. **This is the only file you normally edit per board.**

**Generate**
- `gen_pcb.py` — emits `<board>.kicad_pcb` from the spec: layers/setup, nets, footprints (via
  `load_fp`), mounting holes, logo, outline (rounded-rect or custom `EDGE`), silk, keepouts, pours,
  pre-placed segments/vias. `load_fp` loads stock/local footprints verbatim and injects nets; it keeps
  two part-specific DFM fixups that only fire for those parts (ESP32-WROOM EP/courtyard; USB-C HRO
  slot widening).
- `gen_sch.py` — OPTIONAL documentation schematic from `spec.SCHEMATIC` (skips if undefined; the PCB
  is the authoritative netlist).
- `set_netclasses.py` — writes Default + Power net classes and DFM rule relaxations into `.kicad_pro`
  (creates it if missing). Run first.

**Route + finish**
- `flip_back.py` — moves `spec.FLIP_TO_BACK` parts/logos to the bottom layer (correct mirror).
- `export_dsn.py` — Specctra DSN for freerouting; marks the 4-layer GND plane `type power`.
- `import_ses.py` — imports the route, runs `route_fix`, adds the top GND pour, stitches GND vias,
  ties GND pads to the plane (4-layer), connectivity-guarded dedupe of overlapping/at-pad GND vias,
  then `fix_silk`. The order is load-bearing — see the header comment.
- `route_fix.py` — generic straggler-router engine; executes `spec.STRAGGLERS` ops (usually empty —
  freerouting handles normal boards). Every segment/via is collision-checked (never adds a violation).
- `fix_silk.py` — JLCPCB silk DFM cleanup (line width, silk→pad/hole/via). Reusable geometry library
  also imported by `import_ses.py` and `check_silk.py`.

**Build orchestration**
- `build_routed.sh` — the full loop: net classes → [generate → flip → DSN → freeroute → import → DRC]
  auto-retrying until **0 violations / 0 unconnected** → silk check → fab export → BOM/CPL.
- `export_fab.sh` — gerbers + Excellon drill + zip via kicad-cli (layer list incl. inner Cu for
  4-layer, from `config`).
- `gen_bom_cpl.py` — JLCPCB BOM + CPL CSVs from `spec.LCSC`/`LCSC_VAL`/`EXCLUDE_ASSEMBLY`/`CONN_DESC`.
- `make_logo.py` — rescales a silkscreen-logo `*.kicad_mod` (utility).

**Checks (read-only gates; each takes an optional board-path arg)**
- `check_overlap.py` — courtyard overlaps + off-board parts + ratsnest/net sanity (placement gate;
  non-zero exit on overlaps).
- `check_tht_smd.py` — THT↔SMD pad spacing, **CPL-aware**: `THT_SMD_MIN` (3.0) applies only to THT
  parts the fab PLACES; hand-fitted parts get `THT_HAND_MIN` (1.5); 0.5 mm is the hard floor.
  Falls back to the strict rule (and says so) if no CPL exists.
- `check_jlc_dfm.py` — **fab-house DFM gate for what KiCad's DRC does NOT check**: drill-to-drill
  spacing, via annular ring, via-copper-to-pad across nets, via-DRILL-to-pad copper (any net),
  copper-to-edge, acute corners. Non-zero exit on any DANGER; `build_routed.sh` gates the fab
  export on it. A board can be DRC 0/0 and still fail this.
- `check_handroutes.py` — validates `spec.SEGMENTS`/`spec.VIAS`. Those are coordinate-keyed and
  do NOT follow the parts they serve, so moving a footprint can leave a backbone shorting a pad
  on every routing attempt. ~1 s instead of a routing round.
- `check_silk.py` — trustworthy silk DFM gate (PASS/ISSUES; non-zero exit on issues).
- `check_route.py` — tracks per layer (GND-plane layer must be 0), power-net length+vias, ratsnest.
- `check_bends.py` — flags right-angle/acute trace bends.
- `structural_check.py` — outline, off-board parts, holes, ratsnest, track/via tally, net count.
- `dump_pads.py` / `track_widths.py` — pad dump / per-net track-width distribution.

## Quick start
```bash
cd hardware/<board>/_tools
python check_prereqs.py                   # 0. verify KiCad + Java + freerouting (+ --install to fix)
cp board_spec.example.py board_spec.py    # edit for your board
python config.py                          # verify KiCad + freerouting found
python gen_pcb.py && "<kicad_python>" check_overlap.py   # placement loop (0 overlaps)
"<kicad_python>" check_handroutes.py                     # stale/colliding hand-routes
"<kicad_python>" check_jlc_dfm.py                        # fab DFM (DRC does not cover this)
bash build_routed.sh                      # runs the preflight, then route -> DFM -> fab
```

## Adapting `board_spec.py` — the generalization map
Everything board-specific is data in `board_spec.py`; the scripts are generic. The fields and their
meaning are documented inline in `board_spec.example.py`. Key ones:
- identity: `NAME` (output filename), `TITLE/REV/COMPANY/DATE`
- geometry: `W/H/CORNER_R/THICKNESS/ORIGIN`, `LAYERS` (2|4), `GND_PLANE_LAYER`, `EDGE` (custom outline)
- nets: `NETS` (index 0 = ""), net classes `DEFAULT_*`/`POWER_*`/`POWER_NETS`, `EDGE_CLEARANCE`,
  `MIN_THROUGH_HOLE`
- parts: `FOOTPRINTS` = `(mod_file, libid, ref, value, x, y, rot, {pad: net})`
- copper: `POURS`, `KEEPOUTS`, `SEGMENTS`, `VIAS`, `STITCH_GND/STITCH_PITCH`, `GND_PLANE_TIES`,
  `ADD_TOP_GND_POUR`, `SOLID_GND_CONN`
- silk/mech: `SILK`, `LOGO`, `HOLES`, `FLIP_TO_BACK`
- advanced: `STRAGGLERS` (manual route ops), `THT_SMD_MIN`
- fab: `LCSC`, `LCSC_VAL`, `EXCLUDE_ASSEMBLY`, `CONN_DESC`, `PACKAGE_MAP`, `GERBER_EXTRA_LAYERS`

### What was stripped from the flex-box originals (don't re-introduce)
Absolute board paths, the flex net list, the joystick-notch / antenna keepouts, the WROOM pin-map, and
fixed dimensions are now **spec data**, not hard-coded. The two genuinely part-specific `load_fp`
fixups (WROOM EP/courtyard, USB-C HRO slots) are kept but only fire when those exact parts are placed.

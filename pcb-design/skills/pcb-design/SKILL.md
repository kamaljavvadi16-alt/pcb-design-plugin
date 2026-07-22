---
name: pcb-design
description: >-
  Design printed circuit boards (PCBs) end-to-end with a code-first KiCad workflow: define a board
  from a single Python spec, generate the .kicad_pcb layout, autoroute with freerouting, run
  manufacturability (DFM) gate checks, and export JLCPCB gerbers/drill/BOM/CPL -- all from the
  command line, no GUI clicking. Use for ANY PCB task: new board design, schematic/netlist capture,
  component placement, layout, routing, DFM review, fixing JLCPCB DFM flags, power/RF/switching-
  regulator layout, or generating fabrication outputs. Works for 2- and 4-layer boards.
---

# PCB Design (code-first KiCad workflow)

A board-agnostic toolkit for designing manufacturable PCBs as **code**. You describe a board in one
`board_spec.py`; reusable scripts generate the KiCad board, autoroute it, gate it against JLCPCB DFM
rules, and emit a fab package. Distilled from a real multi-revision hardware project (2- and 4-layer,
native switching regulators, on-board RF module, USB-C, fully PCBA — shipped DFM-clean to JLCPCB).

## When to use this
Any PCB work: a new board, adding/placing parts, routing, chasing a JLCPCB DFM flag, laying out a
switching regulator or an RF module, or producing gerbers/BOM/CPL. Also use it as the reference for
PCB *design judgement* (the `reference/` docs) even when not running the scripts.

## Mental model
The **`board_spec.py` is the source of truth** (the authoritative netlist = each footprint's pad→net
map). The schematic is optional documentation, not the driver. You think in **board-local millimetres**
(origin top-left, +x right, +y down) and let the scripts emit valid KiCad. Then freerouting routes,
and a battery of checks proves the board is fab-ready before any money is spent.

## The workflow (each phase is a checkpoint — verify before moving on)
1. **Spec** — copy `scripts/` into the project's `hardware/<board>/_tools/`, copy
   `board_spec.example.py` → `board_spec.py`, and fill it: dimensions, layer count, nets, footprints
   (with pad→net maps), placement coordinates, pours, keepouts, silk. (Read `reference/design-rules.md`
   first for power/RF boards.)
2. **Placement** — `python gen_pcb.py`, then `<kicad_python> check_overlap.py` and
   `check_handroutes.py`. Iterate until **0 courtyard overlaps, 0 NPTH-hole-in-courtyard, 0 off-board
   parts**, and the ratsnest/net count looks right. Hand-place the critical analog/switching parts;
   don't let the autorouter decide loop geometry. These gates cost ~1 s and catch the bugs that
   otherwise surface 30 minutes into an autoroute.
3. **Route + finish** — `bash build_routed.sh`. This sets net classes, generates, flips back-side
   parts, exports DSN, autoroutes (freerouting, **auto-retries** because it's stochastic), imports the
   result, adds GND pours + stitching, cleans silk, and runs DRC — looping until **0 violations / 0
   unconnected**. On success it exports the fab package.
4. **DFM gates** — `<kicad_python> check_jlc_dfm.py` (**the important one**), then `check_silk.py`,
   `check_tht_smd.py`, `check_route.py`, `check_bends.py`. Resolve every genuine flag. See
   `reference/dfm-rules.md` for what is a real defect vs a fab false-positive you should NOT chase.

   > **`DRC: 0/0` does not mean manufacturable.** KiCad's DRC does not police drill-to-drill spacing,
   > via annular ring, or the drilled hole's clearance to pad copper. `check_jlc_dfm.py` covers those
   > and gates the fab export, so a package that looks finished can't carry a known defect.
5. **Fab gate (before ordering)** — work through `reference/fab-gate-checklist.md`: verify any custom
   or uncertain footprint pad-map **1:1 against the datasheet**, do the paper print test, check every
   rotation in the fab's *interactive* CPL preview, and archive the exact gerber zip. Nothing is
   ordered before this passes.

   > **Ship the CPL with the footprint anchor unmodified.** A part body legitimately overhangs its
   > pads (module antenna ends, connector shells), so a preview can make a correct placement *look*
   > offset. Hand-"correcting" it moves the real pick-and-place off the pads. See `dfm-rules.md`.
   > **A CPL/BOM change needs no re-route** — regenerate and re-upload in seconds.

## Scaffolding a new board (concrete)
The toolchain lives in the **`scripts/` folder next to this SKILL.md**. Copy it into your board's
`_tools/`. The skill dir depends on how it was installed:
- manual install: `~/.claude/skills/pcb-design/`
- plugin install: `~/.claude/plugins/cache/<marketplace>/pcb-design/skills/pcb-design/`

(When I, Claude, run this, I resolve `<skill-dir>` to the directory this SKILL.md was loaded from.)
```bash
mkdir -p hardware/myboard/_tools hardware/myboard/fab
cp <skill-dir>/scripts/* hardware/myboard/_tools/   # <skill-dir> = folder containing this SKILL.md
cd hardware/myboard/_tools
python check_prereqs.py                        # 0. PREFLIGHT: verify KiCad + Java + freerouting + spec
cp board_spec.example.py board_spec.py         # then edit board_spec.py for your board
python config.py                               # verify it finds KiCad + freerouting
python gen_pcb.py && "<kicad_python>" check_overlap.py   # placement loop
bash build_routed.sh                           # route -> DFM -> fab (runs the preflight first)
```

**The preflight is mandatory and enforced — not optional.** `python check_prereqs.py` reports each
prerequisite PASS/MISSING (KiCad CLI, KiCad's pcbnew Python, Java, the bundled freerouting.jar, and
`board_spec.py`) and prints the exact fix for anything missing. It is enforced in two places so the
toolchain is always verified no matter how you enter: `build_routed.sh` runs the full preflight first
and aborts on any failure, and `gen_pcb.py` (the standalone first step) refuses to run if KiCad isn't
found, pointing you at the preflight. Run it yourself up front anyway — it's a 2-second check.

**Installing missing prerequisites (confirmation-gated):** `python check_prereqs.py --install`
offers to install each missing piece via the platform package manager (winget on Windows, brew on
macOS, apt/dnf/pacman on Linux) — **prompting `[y/N]` before every install**; nothing is installed
without your 'y'. When *you* (Claude) run this for the user, run the plain `check_prereqs.py` first,
then surface the proposed install commands and let the user approve them — don't install unprompted.
`<kicad_python>` = the path printed by `python config.py` as "kicad python" (KiCad's bundled
interpreter; the pcbnew scripts must run under it, the generators run under system Python).
**Close KiCad** before running the build (it locks the board file).

## Non-negotiable rules (the ones that cost a board respin)
- **Antenna keepout.** A PCB/chip antenna needs NO copper (no pour, tracks, or vias) under or beside
  it — on **all** layers for a 4-layer board. Encode it as a `KEEPOUTS` entry. #1 first-board killer.
- **Bulk + decoupling caps at the source.** Put the regulator's output bulk cap and each IC's decoupling
  right at the pin. Placement *is* the function (anti-brownout / anti-noise), not decoration.
- **Footprint must match the physical part.** Verify every non-trivial footprint; do the 1:1 paper
  print test. A wrong footprint is invisible until the board is unsolderable.
- **Switching-regulator loops: hand-route, don't autoroute.** Keep the LX/inductor/Cin/Cout loops
  tiny; route them by hand (pre-placed `SEGMENTS`/`VIAS`), let freerouting do the signals.
- **Verify uncertain pad-maps 1:1 at the fab gate.** Custom/hand-built footprints and ambiguous QFN/
  SOT pinouts get checked against the datasheet before ordering.

## Reference (read on demand)
- `reference/methodology.md` — the phased, checkpoint-driven process in full.
- `reference/design-rules.md` — electrical/layout: power tree, decoupling, GND planes + via stitching,
  switching-loop discipline, RF keepout, net-class widths, brand logos on silk.
- `reference/dfm-rules.md` — the JLCPCB DFM ruleset (silk, slots, annular, layer-count, THT↔SMD) **and
  the false-positive catalogue** so you don't chase non-defects.
- `reference/fab-gate-checklist.md` — the pre-order checklist.
- `reference/kicad-cli-cheatsheet.md` — kicad-cli / KiCad-python / freerouting commands + path setup.
- `reference/parts-sourcing.md` — JLCPCB Basic vs Extended, LCSC, lean-BOM defaults.
- `scripts/README.md` — what every script does, the build pipeline, and how to adapt `board_spec.py`.

## Requirements
KiCad (provides `kicad-cli` + a bundled Python with `pcbnew`), **Java** (for the bundled
`freerouting.jar`), a system `python`/`python3` on PATH (runs the generators), and a `board_spec.py`.
`config.py` auto-detects KiCad and overrides with the `KICAD_DIR` env var. **Windows is the primary,
tested platform**; Linux/macOS detection is best-effort — set `KICAD_DIR` if it isn't found. **Run
`python check_prereqs.py` to verify all of this up front** (`--install` to install missing pieces with
confirmation). Targets **JLCPCB** by default; the DFM rules transfer to other fabs.

> Two Pythons: the **generators** (`gen_pcb.py`, `gen_sch.py`, `set_netclasses.py`) run under system
> Python; the **pcbnew scripts** (`import_ses`, `fix_silk`, all `check_*`, …) must run under KiCad's
> bundled Python — `<kicad_python>`, the path printed by `python config.py`. If you run one under the
> wrong interpreter it now tells you so. `build_routed.sh` invokes the right one for each step.

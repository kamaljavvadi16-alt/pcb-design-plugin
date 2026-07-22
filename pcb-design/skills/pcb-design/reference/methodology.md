# PCB design methodology — the phased, checkpoint-driven process

The discipline that keeps boards out of the respin pile: **each phase ends in a checkpoint you verify
before spending the next phase's effort.** A mistake caught at placement costs minutes; caught after
ordering, it costs a board spin and weeks. This is the code-first adaptation (board_spec → scripts);
the same checkpoints apply if you draw in a GUI instead.

## Phase 0 — Decide before drawing
Lock these so you don't rework later:
- **Function + block diagram.** Power in → regulation → loads. List every supply rail and its current.
- **Layer count.** 2-layer for simple/low-speed boards; **4-layer** the moment you have a switching
  regulator, an RF module, or dense routing (you want a solid inner GND plane for the return path).
- **Form factor + constraints.** Board outline, mounting holes, connector edges, any enclosure limits,
  any antenna/keepout zones.
- **Parts you can actually buy.** Pick footprints that match in-stock parts (see `parts-sourcing.md`).
  For JLCPCB PCBA, prefer Basic parts; flag Extended parts early (one-time setup fee each).

## Phase 1 — Spec the board (`board_spec.py`)
Transcribe the netlist into the footprint pad→net maps; **don't improvise nets while placing.** Triple-
check the easy-to-get-wrong nets: FET gate/source/drain, voltage dividers, current-sense polarity,
charger/regulator feedback dividers, any "enable"/strapping pins. Name nets meaningfully (`+3V3`,
`SW_BAT`, `LX`) — net labels are how pins connect, not drawn wires.
**Checkpoint:** read the spec back net-by-net against your block diagram / datasheets.

## Phase 2 — Placement
`python gen_pcb.py` → `check_overlap.py`. Place by **function, not tidiness**:
- Power section together; regulator bulk/decoupling caps hard against the IC pins.
- Connectors on the edges that face their cables/enclosure openings.
- Hand-place the analog/switching/RF parts and their tight loops; everything else can be looser.
- Keep THT pads ≥3 mm from SMD pads (assembly clearance).
**Checkpoint:** 0 courtyard overlaps, 0 off-board parts, ratsnest + net count match the spec, and the
3D/2D view looks like the thing you intend to build.

## Phase 3 — Route + finish
`bash build_routed.sh`. Strategy: **route the critical loops by hand** (pre-placed `SEGMENTS`/`VIAS`
in the spec) so freerouting can't ruin loop geometry, then let freerouting do the rest. Freerouting is
stochastic — the build auto-retries the whole generate→route→import→DRC cycle until clean. The import
step adds the GND pours, stitches them with collision-checked vias, ties GND pads to the plane, dedupes
overlapping drills, and cleans the silk.
**Checkpoint:** DRC **0 violations / 0 unconnected**; power nets actually routed thick (`track_widths.py`).

## Phase 4 — DFM gates
Run the `check_*.py` gates and the JLCPCB online DFM (upload the gerber zip). Fix every **genuine**
flag. Critically: know the JLCPCB false-positives (`dfm-rules.md`) and don't waste spins chasing them.
**Checkpoint:** `check_silk.py` PASS, no critical THT↔SMD gaps, no acute trace bends, and every real
online-DFM danger resolved.

## Phase 5 — Fab gate (before money)
Work `fab-gate-checklist.md`: verify uncertain pad-maps 1:1 against the datasheet, paper-print test,
archive the exact gerber zip, sanity-check BOM/CPL.
**Checkpoint:** this passes → order. Not before.

## Iterating
Versions are cheap, respins are not. Keep each board revision in its own `hardware/<board-vN>/`
directory with its own `_tools/` + `board_spec.py`, and freeze the last known-good revision as a
fallback before starting the next. Commit the exact gerber zip you ordered.

## Rules never worth breaking
1. Antenna keepout (all layers on 4-layer).
2. Bulk/decoupling caps at the pin — placement is the function.
3. Footprint must match the physical part (paper test).
4. Hand-route switching/analog loops; autoroute only the rest.
5. Verify uncertain footprint pad-maps against the datasheet before ordering.

## Branching a board revision: geometry is the thing that goes stale
Copying a board directory to start a new revision is cheap; the bugs it creates are not. Board
dimensions and keep-out maps get hardcoded into helper scripts — outline W/H, notch rectangles,
antenna keep-outs, straggler-router bounds, hand-routed segment coordinates. Every one of those
silently mis-maps the new board, and **none of them fails until ~30 minutes into an autoroute.**

Rules that prevent the whole class:
- **Derive, never hardcode.** Board size from `Edge.Cuts`; keep-outs from the spec that draws them.
- **Hand-routed `SEGMENTS`/`VIAS` are coordinate-keyed and do NOT follow parts.** Gate them
  (`check_handroutes.py`) so a stale backbone is a 1-second failure, not a routing round.
- **Any pass that ADDS copper must run every geometric check itself**, regardless of where it sits
  in the pipeline. A late pass cannot rely on earlier passes having cleaned up — they ran before it.

## When the autorouter "can't" route something, check whether it is possible
Repeated failures on one net are often geometry, not effort. A power-class track leaving a
fine-pitch pad is the classic case: a 0.6 mm track on a 0.28 mm pad at 0.5 mm pitch leaves 0.06 mm
to the neighbour against a 0.2 mm rule — **no effort setting will ever route it.** Fixes:
- taper the escape (narrow until clear of the neighbour, then widen), or
- centre the escape **between two pads of the same net** (doubles the clearance for free), or
- pre-place the connection so the router works around it instead of racing it.

Pre-place anything the router keeps losing. Building a connection *after* the router has run means
competing for a corridor it already owns — that shows up as an intermittent "blocked" straggler.

## Diagnose with a histogram, not the last attempt
Autorouting is stochastic, so the failing net differs run to run and the final report describes only
the last attempt. Append each attempt's failures to a log and count them: the chronic offender is
the one that needs a design change; the singletons are noise. Chasing the last attempt's list means
fixing a different "random" net every round while the real blocker survives untouched.

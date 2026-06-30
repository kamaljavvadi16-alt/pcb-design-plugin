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

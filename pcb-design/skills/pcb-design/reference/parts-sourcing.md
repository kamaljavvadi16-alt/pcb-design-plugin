# Parts sourcing & BOM strategy

Design to parts you can actually buy, in stock, at the assembly house you'll use.

## JLCPCB PCBA: Basic vs Extended
- **Basic parts** — mounted free, always loaded. Prefer them for jellybean R/C/L, LEDs, common
  transistors, regulators. Cheapest and lowest-risk.
- **Extended parts** — a one-time **per-part loading fee** (~$3) plus the part cost; the feeder must be
  set up. Fine for the few ICs that need it (the main MCU/regulator/charger), but minimise the count —
  each distinct Extended part adds a fee. Flag them at design time, not at checkout.
- **In stock matters more than basic/extended.** A Basic part that's out of stock still blocks the
  order. Check live stock before committing; keep an alternate LCSC# ready for anything marginal.

## Picking parts
- Choose the **footprint that matches an in-stock LCSC part**, not the other way round. Search
  JLCPCB's parts library / LCSC by value + package; note the LCSC# (`Cxxxxx`).
- Put per-ref LCSC# in `board_spec.LCSC` (for ICs/connectors) and per-(value,package) in `LCSC_VAL`
  (for passives, so they auto-confirm in JLC's BOM tool instead of prompting "unconfirmed").
- Leave passives blank if you'd rather let JLCPCB's BOM tool auto-match by value+package — it's good at
  it for Basic parts. ICs should be pinned to a specific LCSC#.

## Lean-BOM default (pilot / cost-sensitive)
For early/pilot boards, propose the **minimum viable** BOM: fewest distinct parts, Basic where
possible, no premium parts unless the function demands it. Flag upgrades (better LDO, more protection,
nicer connectors) as **optional**, with the cost delta, rather than baking them in. Standardise on a
few passive values/packages across the board to cut distinct-part count and feeder fees.

## Hand-soldered vs machine-assembled
- THT connectors/headers and not-yet-populated parts are usually **hand-soldered** — list them in
  `board_spec.EXCLUDE_ASSEMBLY` so they drop out of both the BOM and CPL (JLC only places SMD).
- Relabel connector BOM rows via `CONN_DESC` so the assembler can't mistake a connector's value
  (e.g. "OLED") for a module to source — the peripheral is external; only the connector is on-board.

## Buying links — verify before recommending
When you cite a purchase link or stock level, **fetch/verify it first** rather than asserting from
memory; stock and part numbers change. Some distributor pages block automated fetches — prefer ones
that show live stock, and fall back to giving the search term + part number so the user can confirm.

## Other fabs
The DFM rules here target JLCPCB but transfer: PCBWay, OSHPark, Aisler etc. have their own minimums
(check trace/space, drill, annular, slot). The gerber/drill export is standard; the BOM/CPL CSV format
is JLCPCB-flavoured — other PCBA houses want their own column order, so re-map if you switch.

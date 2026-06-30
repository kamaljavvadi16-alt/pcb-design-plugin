# Fab gate — the pre-order checklist

The last gate before spending money. Nothing is ordered until every item passes. Respins cost weeks;
this checklist costs an hour.

## 1. Footprint pad-maps verified 1:1 against datasheets
The single highest-risk item. For **every** custom/hand-built footprint and every ambiguous pinout
(QFN/DFN/SOT thermal pads, parts where pin 1 orientation or S/G/D mapping is non-obvious):
- [ ] Open the manufacturer datasheet's package drawing (top view) and check pad number → pin function
      against your `board_spec` pad→net map, **physically, one pad at a time**.
- [ ] For dual-FET / protection / charger ICs, confirm S/G/D and sense polarity — these are the classic
      "electrically plausible but wrong" mistakes.
- [ ] Confirm EP/thermal-pad net (usually GND) and its via tie.
A wrong pad-map passes DRC, passes DFM, and only fails when the assembled board doesn't work.

## 2. Footprint matches the physical part (paper test)
- [ ] Print the layout (or the relevant footprints) **1:1 on paper**. Place the actual physical parts
      on the printout. Pin pitch, body size, connector orientation, polarity — all must match.
- [ ] Confirm connector genders and which way cables exit.

## 3. Electrical sanity
- [ ] Re-read the netlist for the classic traps: FET gate/source/drain, dividers, current-sense
      polarity, regulator/charger FB divider values, enable/strapping pins, NC pins left floating.
- [ ] Decoupling + bulk caps present and placed at the pins.
- [ ] Power net widths adequate for the current (`track_widths.py`).

## 4. DFM clean
- [ ] DRC: 0 violations, 0 unconnected (build log).
- [ ] `check_silk.py` PASS; `check_tht_smd.py` no critical (<0.5 mm) gaps; `check_bends.py` no acute.
- [ ] Uploaded the gerber zip to JLCPCB's online DFM; every genuine danger resolved; remaining flags
      confirmed as false-positives (`dfm-rules.md` §B).
- [ ] **4-layer:** the online DFM reads "PCB layers: 4" (inner layers present in the gerbers).

## 5. Outputs sane
- [ ] Gerber zip contains all expected layers + drill + `.gbrjob` (inner copper for 4-layer).
- [ ] BOM: every assembled part has a value+package; LCSC# assigned or to be matched in JLC's tool;
      hand-soldered/THT parts correctly excluded.
- [ ] CPL: every assembled part present; **rotations/polarity checked in JLCPCB's CPL preview**
      (JLC's 0° reference differs from KiCad's for some parts — LEDs, diodes, polarized caps, ICs).
- [ ] Parts in stock (re-check live stock for any marginal part; have an alternate LCSC# ready).

## 6. Archive
- [ ] Commit the **exact** gerber zip you upload (don't regenerate later "from memory").
- [ ] Commit `board_spec.py`, the `_tools/`, and the `.kicad_pcb/.kicad_pro` for this revision.
- [ ] Freeze the last known-good revision as a fallback before starting the next.

## Order settings (JLCPCB)
Layers (2/4) · 1.6 mm · 1 oz · HASL or ENIG · qty/colour. PCBA: economic vs standard assembly,
Basic vs Extended parts confirmed, CPL preview checked.

> Carry-forward cautions belong in the board's own context notes: list any pad-map you verified "by
> reasoning" rather than from an unambiguous datasheet drawing, and eyeball those again at this gate.

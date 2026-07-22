# JLCPCB DFM ruleset — and the false-positive catalogue

Hard-won from real JLCPCB DFM round-trips. Two parts: (A) the genuine rules to design to, and (B) the
flags JLCPCB raises that are **NOT defects** — knowing these saves you from chasing non-problems (and
from "fixing" something into an actual defect).

## A. Genuine rules — design to these
| Rule | Threshold (JLCPCB, std process) | How the toolchain handles it |
|---|---|---|
| Min trace width | 0.127 mm (5 mil); use ≥0.15 | `DEFAULT_TRACK` 0.25 default |
| Min clearance | 0.127 mm; use ≥0.15 | `DEFAULT_CLEARANCE` 0.2 default |
| Trace ↔ board edge | ≥ 0.3 mm | `EDGE_CLEARANCE` 0.3 |
| Min drill (PTH) | 0.2 mm | `MIN_THROUGH_HOLE` (relax to 0.2 for EP/thermal vias) |
| Via annular ring | ≥ 0.13 mm | default via 0.7/0.3 = 0.2 mm annular |
| **Routed slot width** | ≥ ~0.8 mm, and length ≥ 2×width (else "short slot") | `load_fp` widens USB-C SH slots to 0.85×1.70 mm |
| **Silk line width** | ≥ 0.153 mm; use 0.2 | `fix_silk.py` bumps every silk stroke/text to 0.2 |
| **Silk → pad / hole / via** | ≥ 0.15 mm clearance | `fix_silk.py` trims silk + slides text clear |
| **THT pad ↔ SMD pad** | ≥ 3 mm **only for THT parts the fab PLACES** (see below); ~1.5 mm for hand-fitted; 0.5 mm hard floor | `check_tht_smd.py` (CPL-aware) |
| **Hole ↔ hole (drill spacing)** | edge gap **≥ 0.3 mm**; 0.05 mm is flagged a hard DANGER | `check_jlc_dfm.py` + `import_ses.py` relocating dedupe |
| **Via DRILL ↔ pad copper** | ≥ 0.2 mm — the fab measures the **hole**, not the copper, and **regardless of net** | `check_jlc_dfm.py` |
| **Via inside a pad** | fine on a thermal EP; on a chip land it wicks solder out of the joint | `check_jlc_dfm.py` (discriminates by parent pad count) |
| **Unprintable mask slivers** | a mask web thinner than ~0.1 mm cannot be printed | set `solder_mask_min_width` 0.1 so KiCad merges them |
| Acute trace bends | avoid <90° (acid traps) | `check_bends.py` flags right-angle/acute corners |

### The ≥3 mm THT↔SMD rule applies only to FAB-PLACED through-hole parts
The clearance exists because the fab hand/wave-solders THT parts **after** SMD reflow. Parts you fit
yourself after delivery never see that operation, and bare mounting holes never see it at all — so
holding them to 3 mm buys nothing and costs a lot of board.

**Check the CPL, not the pad type.** On the board this skill came from, 12 holed parts were 18 % of
the BOM but **65 % of the placement budget**, and exactly ONE (the USB-C) was machine-placed.
Correcting it freed ~760 mm² — the difference between a shrink closing and not.

### `DRC: 0 violations` is NOT proof the board is manufacturable
`kicad-cli pcb drc` does **not** police drill-to-drill spacing, via annular ring, or the drilled
hole's clearance to pad copper. A board can be 0 violations / 0 unconnected and still carry real
fab DANGERs — that exact combination has shipped. Run `check_jlc_dfm.py`, and gate the fab export
on it so a package that looks finished can't be one that carries a known defect.

### The layer-count trap (4-layer boards) — easy to miss, fatal
When exporting gerbers for a 4-layer board you **must** include the inner copper layers
(`In1.Cu, In2.Cu`). Omit them and JLCPCB silently builds a **2-layer** board with no plane and no inner
routing — and the upload reads "PCB layers: 2". `config.gerber_layer_list()` includes the inner layers
automatically based on `spec.LAYERS`; never hand-trim the gerber layer list.

## B. JLCPCB false-positives — do NOT chase these
JLCPCB's automated Gerber DFM flags several things that are **manufacturable as-is**. "Fixing" them
often makes the board worse. Recognise them:

- **"Soldermask opening exposing trace" on a multi-pin IC net.** When a power trace crosses several
  pins of *its own net* on one IC (e.g. a regulator's VOUT over pins 7/8, VIN over pins 1/4/5/16), the
  exposed copper is the **same net** — it takes solder and cannot short. Verify the flagged copper is
  same-net (it is), then ignore. You can't "fix" it without not connecting the pins.
- **"Annular ring 0.15 mm" advisory** when you're using JLCPCB's own standard 0.3 mm-drill / 0.6 mm-via
  — that's their standard via; the flag is informational, not a defect.
- **QFN/DFN exposed-pad "multi-segment soldermask opening" / paste windowpane.** A split paste mask on
  a thermal EP is standard practice (controls solder volume); not a defect.
- **Different-net trace↔pad proximity flags that are actually ≥ your clearance.** Measure: if the real
  gap meets your design clearance and JLCPCB doesn't hard-flag it, it's noise.

- **SMT DFM "pin edge / lead area / pin without pad" on a correct CPL.** The fab renders each part
  from **its own 3D-model origin**, which for many packages is not the part centroid — so pins can
  read as off-pad even when the CPL is exact. Tell the two apart by the *pattern*: a real CPL fault
  is systematic (one field, one direction); model-origin noise is **per-part and in different
  directions**. Verify your side instead: CPL X/Y should equal the footprint anchor, and the anchor
  should equal the pad centroid on symmetric parts. If both hold, do not "compensate" — see below.

**How to triage:** a genuine danger reduces yield/connectivity (clearance, slot, drill spacing, layer
count, silk legibility). A false-positive is cosmetic or same-net. When unsure, confirm the geometry
in KiCad (measure the actual clearance / confirm same-net) before changing copper. For a pilot run,
same-net mask exposure and EP paste windows are fine.

## Never hand-tune CPL position or rotation from a preview image
The single most expensive mistake available here. A part's **body legitimately extends past its
pads** (a module's antenna end, a connector's shell), so in a preview the body looks "offset" when
the placement is correct. "Correcting" that offset in the CPL moves the **real pick-and-place** off
the pads — turning a non-problem into a genuine defect that then reads as *"lead area overlapping
pad 0 mm"* across every pin of that part.

- The KiCad footprint anchor **is** the correct placement origin. Ship it unmodified.
- Validate rotation in the fab's **interactive CPL preview** (per-part, with a pin-1 marker), never
  from the DFM report — the report gives a count and one sample image per check and never names the
  component, so it cannot be converged on by iteration.
- If you do keep a per-part rotation table, match part names **exactly**. Substring matching quietly
  applies a 3-pin `SOT-23` correction to `SOT-23-6`, which is a different package.
- Add pin-1 silk dots (`add_pin1_silk.py`) so the preview has something on-board to check against.

## Process options worth setting (JLCPCB order page)
2 or 4 layer · 1.6 mm · 1 oz outer Cu · HASL (cheapest) or **ENIG** (flat, fine-pitch friendly) ·
soldermask colour of choice. For PCBA: confirm Basic vs Extended parts, and **verify each part's
rotation/polarity in JLCPCB's CPL preview** — JLC's 0° reference can differ from KiCad's per part.

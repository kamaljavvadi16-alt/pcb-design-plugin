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
| **THT pad ↔ SMD pad** | keep ≥ 3 mm (assembly bridging) | `check_tht_smd.py` (advisory <3, critical <0.5) |
| Two holes too close | edge gap < ~0.15 mm reads as a 0-width slot / PTH-spacing DANGER | `import_ses.py` connectivity-guarded GND-via dedupe |
| Acute trace bends | avoid <90° (acid traps) | `check_bends.py` flags right-angle/acute corners |

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

**How to triage:** a genuine danger reduces yield/connectivity (clearance, slot, drill spacing, layer
count, silk legibility). A false-positive is cosmetic or same-net. When unsure, confirm the geometry
in KiCad (measure the actual clearance / confirm same-net) before changing copper. For a pilot run,
same-net mask exposure and EP paste windows are fine.

## Process options worth setting (JLCPCB order page)
2 or 4 layer · 1.6 mm · 1 oz outer Cu · HASL (cheapest) or **ENIG** (flat, fine-pitch friendly) ·
soldermask colour of choice. For PCBA: confirm Basic vs Extended parts, and **verify each part's
rotation/polarity in JLCPCB's CPL preview** — JLC's 0° reference can differ from KiCad's per part.

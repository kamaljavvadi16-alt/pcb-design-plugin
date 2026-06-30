# kicad-cli / KiCad-python / freerouting cheat-sheet

Everything the toolchain shells out to. The two Pythons matter: **generators** (`gen_pcb.py`,
`gen_sch.py`, `set_netclasses.py`) run under **system Python** (pure text/JSON, no pcbnew); the
**pcbnew scripts** (`export_dsn`, `import_ses`, `flip_back`, `fix_silk`, `route_fix`, `gen_bom_cpl`,
all `check_*`) run under **KiCad's bundled Python**.

## Paths (config.py does this for you)
`config.py` auto-detects KiCad and prints the paths:
```bash
python config.py            # human-readable: board, kicad bin/cli/python, footprints, freerouting, gerber layers
python config.py --sh       # shell var assignments for the build scripts: eval "$(python config.py --sh)"
```
- Windows: `%LOCALAPPDATA%\Programs\KiCad\<ver>\bin` (newest version auto-picked).
- Override: set `KICAD_DIR` to the dir containing `kicad-cli` / the bundled `python`.
- Override the active spec: set `BOARD_SPEC` (default `board_spec`).

Typical KiCad-python path (Windows): `%LOCALAPPDATA%\Programs\KiCad\10.0\bin\python.exe`.

## kicad-cli (the parts used)
```bash
# DRC -> report file; --severity-error filters to hard errors
kicad-cli pcb drc --severity-error -o drc.rpt board.kicad_pcb

# Gerbers: --no-protel-ext => <board>-<layer>.gbr names. LAYERS must include inner Cu for 4-layer!
kicad-cli pcb export gerbers --output out/ --no-protel-ext --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts,..." board.kicad_pcb

# Excellon drill, mm, absolute origin (matches the gerber coordinate origin)
kicad-cli pcb export drill --output out/ --format excellon --excellon-units mm --drill-origin absolute board.kicad_pcb

# Handy extras
kicad-cli pcb export pos   --output cpl.csv --units mm board.kicad_pcb     # placement (CPL-like)
kicad-cli pcb export svg   --output board.svg --layers "F.Cu,F.Silkscreen,Edge.Cuts" board.kicad_pcb
kicad-cli pcb render       --output board.png --side top board.kicad_pcb   # 3D render (if supported)
```
Other useful layer names: `F.Adhesive,B.Adhesive,F.Courtyard,B.Courtyard,F.Fab,B.Fab,Margin,User.Comments,User.Drawings,User.Eco1,User.Eco2`.

## KiCad bundled Python (pcbnew)
```bash
"<kicad_python>" import_ses.py        # the pcbnew scripts must run under THIS interpreter
"<kicad_python>" check_silk.py [board.kicad_pcb]   # check_* accept an optional board path arg
```
Notes from the KiCad 10 binding:
- `board.GetTracks()` returns a non-iterable SwigPyObject in some calls — wrap counts in `list(...)`
  and `try/except` (see `import_ses.py`'s defensive diagnostic).
- "swig/python detected a memory leak …" lines on exit are **harmless** binding noise.
- Close the KiCad GUI before running — it locks the `.kicad_pcb`.

## freerouting (the bundled freerouting.jar, needs Java)
```bash
java -jar freerouting.jar -de route.dsn -do route.ses -mp 100
```
- `-de` input Specctra DSN · `-do` output SES · `-mp N` max optimization passes (fewer = faster write,
  helps it finish before a timeout on dense boards).
- It's **stochastic**: `build_routed.sh` time-caps it (`timeout 340 …` when available) and **auto-
  retries** the whole generate→route→import→DRC cycle until DRC is clean.
- A 4-layer board's GND plane is excluded from signal routing by marking that layer `type power` in the
  DSN (`export_dsn.py`); GND vias still drop onto it.

## The route pipeline (what build_routed.sh runs)
`set_netclasses` → loop[ `gen_pcb` → `flip_back` → `export_dsn` → freerouting → `import_ses` → DRC ]
until 0/0 → `check_silk` → `export_fab` → `gen_bom_cpl`.

# pcb-tools — Claude Code plugin marketplace

A Claude Code plugin marketplace hosting **`pcb-design`**: a code-first KiCad workflow that designs a
PCB end-to-end. You describe a board in one Python spec; it generates the layout, autoroutes with
freerouting, runs JLCPCB DFM gate checks, and exports gerbers/drill/BOM/CPL. Works for 2- and 4-layer
boards.

## Install (for users)

In Claude Code:

```text
/plugin marketplace add kamaljavvadi16-alt/pcb-design-plugin
/plugin install pcb-design@pcb-tools
```

`kamaljavvadi16-alt/pcb-design-plugin` is this repo. `pcb-tools` is the marketplace name (the `name`
field in `.claude-plugin/marketplace.json`). After installing, invoke it with **`/pcb-design`** — or
just ask Claude to design a PCB.

You can also try it from a local clone:

```text
git clone https://github.com/kamaljavvadi16-alt/pcb-design-plugin
# in Claude Code:
/plugin marketplace add ./pcb-design-plugin
/plugin install pcb-design@pcb-tools
```

### No `/plugin` command? Install as a plain skill

Some Claude surfaces (older Claude Code versions, or certain IDE/remote/SDK-hosted sessions) don't
expose `/plugin`. Skills also load from a plain folder, so install it manually — no marketplace needed:

```bash
# macOS / Linux
git clone https://github.com/kamaljavvadi16-alt/pcb-design-plugin
cp -r pcb-design-plugin/pcb-design/skills/pcb-design ~/.claude/skills/pcb-design
```
```powershell
# Windows (PowerShell)
git clone https://github.com/kamaljavvadi16-alt/pcb-design-plugin
Copy-Item -Recurse pcb-design-plugin\pcb-design\skills\pcb-design "$env:USERPROFILE\.claude\skills\pcb-design"
```
Restart Claude Code, then invoke with `/pcb-design`. (If `/plugin` *is* available, prefer the
marketplace install above — it gives you clean updates.)

## Prerequisites

The plugin bundles everything except the heavy native tools. After installing, run the built-in
preflight from a scaffolded board's `_tools/` dir:

```bash
python check_prereqs.py            # report KiCad / Java / freerouting / board_spec
python check_prereqs.py --install  # install missing pieces (winget/brew/apt), prompts [y/N] each
```

- **KiCad** (provides `kicad-cli` + a bundled Python with `pcbnew`)
- **Java** (runs the bundled `freerouting.jar`)
- **Python** on PATH (runs the generators)

Windows is the primary, tested platform; macOS/Linux detection is best-effort (set `KICAD_DIR` if KiCad
isn't found).

## What's inside

```
.claude-plugin/marketplace.json     # the marketplace catalog (lists the plugin)
pcb-design/                         # the plugin
  .claude-plugin/plugin.json        # plugin manifest
  skills/pcb-design/                # the skill (auto-discovered)
    SKILL.md                        # entry point + workflow
    reference/                      # methodology, design rules, DFM rules, fab gate, cheatsheets
    scripts/                        # the toolchain (gen/route/check/fab) + freerouting.jar
```

## Updating

Push changes and bump the `version` in both `marketplace.json` and `pcb-design/.claude-plugin/plugin.json`.
Users refresh with `/plugin marketplace update pcb-tools` and reinstall/update.

## Licensing

The plugin's own scripts and docs are yours to license (MIT is a fine default — add a `LICENSE` file).
**`freerouting.jar` is a third-party tool** bundled here for convenience and is distributed under its
own license (see the [freerouting project](https://github.com/freerouting/freerouting)). If you'd
rather not redistribute it, delete `pcb-design/skills/pcb-design/scripts/freerouting.jar` and have users
fetch it themselves — the preflight/README can point them to the download.

## Customize before publishing

- Set `owner`/`author` names (and optionally email) in `marketplace.json` and `plugin.json`.
- Optionally rename the marketplace (`name` in `marketplace.json`) — that's the `@name` users type.

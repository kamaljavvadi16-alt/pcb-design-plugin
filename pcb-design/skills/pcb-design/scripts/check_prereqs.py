"""Preflight: verify the toolchain prerequisites, and optionally install the missing ones (with
your confirmation). Run this once on a new machine before build_routed.sh.

    python check_prereqs.py            # report only (READ-ONLY): prints PASS/MISSING + how to fix
    python check_prereqs.py --install  # interactively offer to install each MISSING prerequisite

Prerequisites checked:
  1. System Python         (running this script)
  2. KiCad CLI             (kicad-cli -- gerber/drill/DRC export)
  3. KiCad Python + pcbnew (the bundled interpreter the layout scripts run under)
  4. Java                  (runs the bundled freerouting.jar autorouter)
  5. freerouting.jar       (bundled in this dir)
  6. board_spec.py         (the per-board spec; copy from board_spec.example.py)

Install is confirmation-gated: nothing is installed unless you pass --install AND answer 'y' at each
prompt. Installs use the platform package manager (winget / brew / apt|dnf|pacman); KiCad and JDK are
large downloads and may require admin rights -- the prompt is your go/no-go. Exit code is non-zero if
any required prerequisite is still missing (so build_routed.sh can gate on it).
"""
import os
import sys
import shutil
import subprocess
import platform

os.environ["PCB_SKIP_SPEC"] = "1"   # tolerate a missing board_spec.py (it's one of the things we check)
import config

INSTALL = "--install" in sys.argv


def run(cmd, timeout=25):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def kicad_python_candidates():
    cands = [config.KICAD_PY]
    if not config.KICAD_BIN:                 # PATH fallback (Linux): pcbnew under system python3
        cands += ["python3", "python"]
    return [c for c in cands if c]


# ---------------- platform install commands ----------------
def installers():
    sysname = platform.system()
    if sysname == "Windows":
        wg = shutil.which("winget")
        if wg:
            return {"KiCad": [wg, "install", "-e", "--id", "KiCad.KiCad"],
                    "Java": [wg, "install", "-e", "--id", "Microsoft.OpenJDK.17"]}, "winget"
        return {}, None
    if sysname == "Darwin":
        br = shutil.which("brew")
        if br:
            return {"KiCad": [br, "install", "--cask", "kicad"],
                    "Java": [br, "install", "--cask", "temurin"]}, "brew"
        return {}, None
    # Linux
    if shutil.which("apt"):
        return {"KiCad": ["sudo", "apt", "install", "-y", "kicad"],
                "Java": ["sudo", "apt", "install", "-y", "default-jre"]}, "apt"
    if shutil.which("dnf"):
        return {"KiCad": ["sudo", "dnf", "install", "-y", "kicad"],
                "Java": ["sudo", "dnf", "install", "-y", "java-17-openjdk"]}, "dnf"
    if shutil.which("pacman"):
        return {"KiCad": ["sudo", "pacman", "-S", "--noconfirm", "kicad"],
                "Java": ["sudo", "pacman", "-S", "--noconfirm", "jre-openjdk"]}, "pacman"
    return {}, None


INSTALL_CMDS, PKG_MGR = installers()


# ---------------- checks ----------------
checks = []   # (name, ok, detail, fixhint, installable_key)

# 1. system python
checks.append(("System Python", True, sys.version.split()[0], "", None))

# 2. KiCad CLI
cli = config.KICAD_CLI if os.path.isfile(config.KICAD_CLI) else shutil.which("kicad-cli")
ok = detail = False
if cli:
    r = run([cli, "version"])
    if r and r.returncode == 0:
        ok = True
        detail = (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else "ok"
checks.append(("KiCad CLI", bool(ok), detail or "not found",
               "Install KiCad (provides kicad-cli + the bundled python).", "KiCad"))

# 3. KiCad python + pcbnew
ok = detail = False
probe = "import pcbnew; v=getattr(pcbnew,'GetBuildVersion',None); print(v() if v else 'imported')"
for py in kicad_python_candidates():
    p = py if (os.path.isfile(py) or shutil.which(py)) else None
    if not p:
        continue
    r = run([p, "-c", probe])
    if r and r.returncode == 0:
        ok = True
        detail = "pcbnew " + (r.stdout.strip() or "ok") + f"  [{py}]"
        break
checks.append(("KiCad Python + pcbnew", bool(ok), detail or "pcbnew not importable",
               "Comes with KiCad; if KiCad is installed, set KICAD_DIR to its bin dir.", "KiCad"))

# 4. Java
java = shutil.which("java")
ok = detail = False
if java:
    r = run([java, "-version"])
    if r is not None:
        ok = True
        line = (r.stderr or r.stdout).strip().splitlines()
        detail = line[0] if line else "ok"
checks.append(("Java (for freerouting)", bool(ok), detail or "not found",
               "Install a JDK/JRE 17+ to run the autorouter.", "Java"))

# 5. freerouting.jar
jok = os.path.exists(config.FREEROUTING_JAR) and os.path.getsize(config.FREEROUTING_JAR) > 100000
checks.append(("freerouting.jar (bundled)", jok,
               os.path.basename(config.FREEROUTING_JAR) if jok else "missing/too small",
               "Should be bundled in this dir; re-copy it from the skill's scripts/ folder.", None))

# 6. board_spec.py
spec_path = os.path.join(config.HERE, "board_spec.py")
spok = os.path.isfile(spec_path)
checks.append(("board_spec.py", spok, "present" if spok else "not found",
               "Copy board_spec.example.py to board_spec.py and edit it for your board.", "board_spec"))


# ---------------- report ----------------
print("PCB toolchain preflight\n" + "=" * 60)
for name, ok, detail, _hint, _k in checks:
    print(f"  [{'OK ' if ok else 'XX '}] {name:26} {detail}")
missing = [(n, h, k) for (n, ok, d, h, k) in checks if not ok]
print("=" * 60)

if not missing:
    print("All prerequisites satisfied. You can run:  bash build_routed.sh")
    sys.exit(0)

print(f"{len(missing)} missing:")
for name, hint, _k in missing:
    print(f"  - {name}: {hint}")

# show / offer install commands
def do_board_spec():
    ex = os.path.join(config.HERE, "board_spec.example.py")
    if not os.path.isfile(ex):
        print("  ! board_spec.example.py not found next to this script.")
        return False
    shutil.copyfile(ex, spec_path)
    print(f"  -> copied board_spec.example.py to {spec_path} (now EDIT it for your board)")
    return True

print("\nTo fix:")
for name, hint, key in missing:
    if key == "board_spec":
        print(f"  {name}:  cp board_spec.example.py board_spec.py   (then edit it)")
    elif key in INSTALL_CMDS:
        print(f"  {name}:  {' '.join(INSTALL_CMDS[key])}")
    elif key in ("KiCad", "Java"):
        print(f"  {name}:  (no supported package manager found — install manually: "
              f"{'kicad.org/download' if key == 'KiCad' else 'adoptium.net'})")

if not INSTALL:
    print("\nRe-run with  python check_prereqs.py --install  to install the missing pieces "
          "(you'll confirm each).")
    sys.exit(1)

# --install: confirmation-gated installation
print("\n-- install mode -- (you confirm each)")
done_keys = set()
for name, hint, key in missing:
    if key is None:
        print(f"  {name}: cannot auto-install (re-copy freerouting.jar from the skill).")
        continue
    if key in done_keys:
        continue
    if key == "board_spec":
        ans = input(f"Copy board_spec.example.py -> board_spec.py? [y/N] ").strip().lower()
        if ans == "y":
            do_board_spec()
        done_keys.add(key)
        continue
    cmd = INSTALL_CMDS.get(key)
    if not cmd:
        print(f"  {name}: no package manager available; install manually.")
        continue
    ans = input(f"Install {key} via:  {' '.join(cmd)}\n  proceed? [y/N] ").strip().lower()
    if ans == "y":
        print(f"  running: {' '.join(cmd)}")
        rc = subprocess.run(cmd).returncode
        print(f"  {key} install exit code: {rc}"
              + ("  (you may need to open a new shell so PATH updates take effect)" if rc == 0 else ""))
    else:
        print(f"  skipped {key}.")
    done_keys.add(key)

print("\nRe-run  python check_prereqs.py  to re-verify.")
sys.exit(1)

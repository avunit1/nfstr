# NFS: The Run -- Mod Menu

A single-player, offline mod menu / trainer for *Need for Speed: The Run*
(2011), rebuilt from scratch around one goal: **work on whatever build of
the game you actually have**, instead of hardcoding addresses for one
specific exe.

This is a from-scratch rewrite of an earlier, messier attempt in this
repo. The old `main.py` mixed a handful of genuinely-verified addresses
with several others that had drifted into plausible-but-unverifiable
guesses (most obviously the vehicle "hash ID" table, which didn't match
any real data). This version fixes that by treating every signature as
data with a traceable source, and by generating rather than hand-typing
every byte sequence it writes -- see [Architecture](#architecture) and
[Credits & provenance](#credits--provenance).

## Requirements

- Windows (this reads/writes another process's memory -- Windows-only by nature)
- Python 3.10+
- `pip install -r requirements.txt`
- Run as Administrator if the game itself needs elevation to launch
  (common for Origin/EA App installs)

## Getting the .exe

Two ways to get a standalone `NFSTR-ModMenu.exe` -- you don't need
Python installed at all as an end user, only to build it:

**Automatic (recommended):** push a version tag and GitHub Actions
builds it on a real Windows runner and attaches it to a new Release:
```
git tag v1.0.0
git push origin v1.0.0
```
Check the Actions tab for progress; the exe lands under that tag's
Release assets a couple of minutes later. You can also trigger a build
without publishing anything (Actions tab -> "Build Windows exe" -> "Run
workflow") just to confirm it still builds.

**Local build**, on a Windows machine with Python installed:
```
build.bat
```
This produces `dist\NFSTR-ModMenu.exe`. Copy that one file anywhere --
it creates a small `nfstr_data\` folder next to itself the first time
it runs (calibration cache + logs) and is otherwise fully self-contained.

*(I built and tested this from a Linux sandbox, so I can't hand you an
already-compiled .exe directly -- PyInstaller has to run on the target
OS. Both options above run on real Windows, either GitHub's or yours.)*

## Quick start

```
pip install -r requirements.txt
python main.py
```

Launch the mod menu, then launch the game (in either order -- **Auto-
attach** is on by default and picks up the game within a couple of
seconds of it starting). The first time it sees a given exe (identified
by its SHA256), resolving every signature takes a couple of seconds;
every launch after that reuses a cache (`nfstr_data/build_cache.json`)
and is instant. You can also drive this from the command line, with a
full report:

```
python tools/calibrate.py
```

## If something doesn't work: the Log tab

The **Log** tab in the GUI shows everything the tool is doing in real
time -- process attach details, per-signature resolution results,
every enable/disable attempt, and full tracebacks for anything
unexpected. It's also always written to
`nfstr_data/logs/session.log` next to the exe (rotated at 5MB, a few
backups kept), so it survives even if the window is closed or the app
crashes outright. Turn on **Verbose (debug) logging** in that tab for
maximum detail, reproduce whatever went wrong, then either **Copy all
to clipboard** or **Save to file...** and share that.


## How version-independence actually works

Every game build (Steam, Origin, cracked, patched) can load the exe at a
different base address, and can have shifted internal offsets if the
build differs from the one the addresses were originally recorded
against. Two mechanisms handle this, layered so the first one that works
wins:

1. **AOB (array-of-bytes) scanning.** A handful of signatures are
   genuine byte-pattern scans with wildcards (e.g. fast-boot, debug
   mode) -- these work on *any* build where that code exists at all,
   regardless of where it sits in the file.
2. **RVA + byte verification.** Most signatures are stored as an offset
   from the module's base address (matching the "`ExecutableName+RVA`"
   convention Cheat Engine itself uses), adjusted automatically if the
   live module loads somewhere other than the historical reference
   base. Before anything is ever written, the live bytes at that address
   are compared against the exact bytes the source material shows should
   be there. If they don't match, the tool refuses to touch it and tells
   you in the log -- it will never guess.

Everything that resolves successfully gets cached per-exe-hash, so
recalibration only costs anything the first time.

## What's included

| Category | Examples |
|---|---|
| Performance | Unlock gameplay framerate (real mechanism -- see below, not a fake "patch 7 addresses" hack) |
| Crash Fixes | Tunnel of Pain, Chicago Interstate (both known crash points) |
| Timers | Disable checkpoint timer, out-of-bounds reset, wrong-way respawn, rival-getting-away fail |
| Assists | Disable align-to-road, drift-intent override, Race Line Assist (status/calc/forces), drift forces, enhanced drift physics |
| Vehicle | Force blown-tire / blown-engine flags, adjustable damage/detach threshold, swap current car |
| Game | Unlock all vehicles, unlock all Challenge Series events, remove vehicle-event restrictions |
| AI / Race Setup | AI difficulty, force AI into events, opponent count, grid position, difficulty/traction scalars |
| Traffic | Density scale, max density, vehicle limit |
| World | Time of Day (Career/Challenge and Multiplayer presets) |
| UI | Show hidden UI/vehicle-list gate, debug main menu, garage car rendering, HUD visibility, fast boot, debug mode |

Each toggle shows a small risk dot (green/orange) and a plain-language
description in the GUI. Everything here is scoped to **single-player /
offline** play, matching how the source material itself frames these
(some entries explicitly note they don't work, or shouldn't be used, in
multiplayer).

### Vehicle Swap

The "Vehicle Swap" tab lists all 2,272 real vehicle entries parsed
straight from the community's vehicle customization library (see
`data/vehicles.json` / `tools/build_vehicles.py`), searchable, and wired
to the real Car Object pointer chain. This replaced a fabricated
6-vehicle hash table in the old version -- the mechanism and one of its
example values were independently cross-checked against the source
material's own test hotkey (which turned out to reference the
"Heynessey Venom GT" entry in the real library -- an exact match).

### Framerate unlock, explained

This is the one feature worth explaining because it's more involved than
a simple byte patch: the game keeps its target framerate on a
dynamically-allocated struct, so there's no fixed address to freeze. The
tool installs a small code cave at the point the game reads that
struct's pointer, which captures the live address into a scratch
allocation; a background thread then continuously writes your chosen fps
into the right field of whatever object that pointer currently points
to. This activates automatically once you're in a race (the hook only
fires when gameplay code actually runs past that point).

## Architecture

```
core/
  process.py    process discovery/attach, module base, SHA256 fingerprint
  memory.py      typed read/write with automatic before-state capture + restore
  scanner.py     AOB pattern scanning + a Cheat-Engine-style first/next scan tool
  jcc.py         generic x86 conditional-jump transforms (see below)
  codecave.py    minimal code-cave/detour engine (VirtualAllocEx + precomputed bytes)
  resolver.py    turns a signature entry into a live, verified address
  cache.py       per-exe-hash resolved-address cache
  paths.py       frozen-aware paths (bundled data vs. writable cache/logs next to the exe)
  logging_setup.py   rotating file log + live queue the GUI's Log tab drains
features/
  engine.py      dispatches enable/disable by patch_type; owns the freeze-thread
gui/
  app.py         tkinter front end, entirely data-driven from data/signatures.json;
                  also owns auto-attach polling and the Log tab
tools/
  build_signatures.py   the actual source of truth -- see below
  build_vehicles.py     regenerates data/vehicles.json from the raw CSV
  calibrate.py           CLI: attach, resolve everything, print a report
data/
  signatures.json   generated by build_signatures.py -- not hand-edited
  vehicles.json      generated by build_vehicles.py -- not hand-edited
nfstr_modmenu.spec, build.bat, .github/workflows/build.yml
  PyInstaller packaging -- see "Getting the .exe" above
```

### Why `tools/build_signatures.py` exists

Every byte sequence this tool ever writes is produced by assembling the
*mnemonic* text (transcribed from the source Cheat Engine tables) with
[Keystone](https://www.keystone-engine.org/), not typed in as hex by
hand. That script is run once, offline, to (re)generate
`data/signatures.json` -- it's not something the mod menu runs while
you're playing. Concretely, this means:

- A transcription mistake shows up as a failed assembly or a failed
  self-check *when the script is run*, not as a crash in your game.
- Hook lengths are *derived* from assembling the real original
  instruction (and doubles as the byte-verification check), not
  independently guessed and hoped to match.
- Conditional jumps (`jcc`) are never hand-encoded as fixed byte pairs.
  `core/jcc.py` detects the short (2-byte) vs near (6-byte) x86 encoding
  from the *live* bytes at run time and computes the correct relative
  displacement for whichever transform is needed -- inverting a
  condition, or converting it to an unconditional jump. An early draft
  of this project got exactly this wrong (reusing a displacement that
  was only valid for a different instruction length); the fix is
  covered by a dedicated arithmetic unit test.

If you want to add a new signature or fix one, edit
`tools/build_signatures.py` (needs `pip install keystone-engine`) and
re-run it -- don't hand-edit `data/signatures.json`.

### Testing note

This was built and tested without a Windows machine or the game itself
available, so nothing here has been run against the live process. To
compensate, every layer that *can* be tested in isolation was:
Keystone-verified byte sequences, a pure-arithmetic unit test for the
jcc transform, an AOB scanner test (including a wildcard match and a
pattern deliberately straddling a chunk boundary), and a full
mock-process integration test exercising every patch type (including
the code-cave allocator and the framerate-unlock data-slot mechanism)
against a simulated process memory buffer. **Please run
`tools/calibrate.py` and read its report before trusting any given
signature on your specific build** -- the tool is designed to tell you
plainly when something didn't verify rather than silently proceeding.

One real bug this process caught after the fact, worth being upfront
about: the source CT mixes two address conventions -- most simple
direct patches give a bare historical address, but every code-cave-style
entry gives its hook address as `"executable"+RVA` (already
module-relative). An earlier version of this project treated both the
same way, which happened to cancel out for entries using the bare form
but put every code-cave-based signature off by `0x00400000`. It's fixed
now (`core/process.py`'s `TargetProcess.addr()` is the only conversion
path left, and every one of the 37 checkable signatures has been
re-verified against the source text programmatically, not just by eye),
along with a related robustness gap where a single failed memory read
during verification could abort the whole calibration pass instead of
just marking that one signature as unresolved.

A second round of real bugs, found from an actual in-game crash report:
three code caves replayed part of the *original* instruction after
already overwriting the same register the cave forces (`traffic_vehicle_limit`,
`tod_multiplayer`), or duplicated a `push`/`pop` between the forcing
preamble and the replay (`game_no_vehicle_event_restriction`,
`tod_career_challenge`, `tod_multiplayer`) -- both silently corrupt
state (a bad pointer dereference, or a misaligned stack) every time the
hook fires. `tools/build_signatures.py` now runs an automated check on
every code-cave entry for both of these specific bug classes (net
push/pop balance, and the destination register of the forced value
being reused for addressing in whatever gets replayed) so they can't
silently reappear -- see `_check_no_register_hazard` and `_stack_delta`.
Separately, `perf_unlock_framerate` no longer auto-forces
`VariableSimTickTimeEnable`; the source only ever exposes that as a
plain viewable value, never a scripted one, and forcing it is the
suspected cause of a reported camera side effect (rigid car-locked
camera instead of free-floating).

## Credits & provenance

The overwhelming majority of the reverse-engineering behind every
signature in this project -- memory addresses, AOB patterns, and the
original Cheat Engine Auto Assembler scripts they're transcribed from --
was researched and discovered by **_mRally2**, via:

- `resources/Master Table/The Run Master Table by _mRally2.CT`
- `resources/Extra UI Options/`
- `resources/Framerate Unlocker/`
- `resources/Time of day Randomizer/`
- `resources/Unreleased Events/`
- `resources/Research/The Run Research.txt`

Per the terms stated in that material's own READMEs: *"By using any
piece of code shared here you agree to credit the respective author once
your mod or tool gets released to the public."* Consider this section
that credit, and please keep it if you fork or redistribute this project.

The `resources/` folder also contains additional material (IDA database
export, ReClass.NET structure definitions, Frostbite/EBX tooling, VLT
data) that wasn't needed for this rewrite but may be useful if you want
to extend it further -- notably the full Time-of-Day randomizer system
and the heap-based full vehicle-customization script (bodykit/spoiler/
exhaust/hood/rims/livery/performance), which are documented in the
Research notes but weren't ported here because they rely on scanning a
live heap allocation that moves around between sessions -- `core/
scanner.py`'s `LiveScanner` (a first-scan/next-scan tool, the same idea
as Cheat Engine's own manual workflow) is included specifically so you
can carry out those documented recipes interactively if you want them.

## Legitimate use

This is intended for single-player / offline use with a copy of the game
you own, in the same spirit as the source Cheat Engine tables it's built
from. Several entries explicitly note (from the source material) that
they don't work, or shouldn't be relied on, in multiplayer -- this
project doesn't add anything intended to affect other players online.

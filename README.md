<div align="center">

# 🏎️ NFSTR

**A feature-rich Python mod suite for *Need for Speed: The Run* with a full GUI, loadless speedrun timer, vehicle customizer, visual tweaks, and live memory patching.**

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Game](https://img.shields.io/badge/Game-NFS%20The%20Run%20v1.1.0.0-orange?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

</div>

---

## 📖 Overview

This mod suite connects directly to the game's process memory at runtime, exposing a full GUI toolkit for modifying behaviour that is otherwise inaccessible — from unlocking the framerate and patching vsync during loading screens, to a millisecond-accurate loadless timer built for speedrunning and a vehicle customizer with JSON preset support.

All modifications are applied live with no file patching required. Close the tool and every change resets with the game.

> ⚠️ **For single-player / offline use only.** This tool directly writes to game memory and should never be used in online or competitive contexts.

---

## ✨ Feature Overview

| Category | Features |
|---|---|
| 🖥️ **Performance** | FPS unlock, cutscene FPS, menu FPS control, loading vsync bypass, graphics quality |
| ⏱️ **Speedrun Tools** | Loadless timer, split tracking, auto-split, JSON export |
| 🚗 **Vehicle Mods** | Disable assists, infinite NOS, no damage, full vehicle customizer |
| 🌅 **Visual Enhancements** | Light intensity, sun position, force headlights |
| 🔧 **Game Tweaks** | Unlock all vehicles & challenges, crash bypasses, disable reset triggers |

---

## 🚀 Getting Started

### Requirements

- Windows 10 or 11
- Python 3.8 or newer
- **Need for Speed: The Run** — PC version **v1.1.0.0** (DRM-free executable)

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/avunit1/nfstr.git
cd nfstr
```

**2. Install the required Python package**
```bash
pip install pymem
```
> `tkinter` is included with Python on Windows. No other dependencies needed.

**3. Launch the game first**, then run the mod suite as Administrator:
```bash
python main.py
```
> Administrator privileges are required for process memory access.

### Verifying Connection

On launch, the status bar at the top of the window will show:

| Status | Meaning |
|---|---|
| ✓ **Connected** (green) | Game process found, memory access confirmed |
| ✗ **Not Connected** (red) | Game isn't running, or wrong version |

If not connected, start the game and click **Reconnect**.

---

## 🛠️ Features In Detail

### 🖥️ Performance Tab

Control framerate limits and graphics quality without editing any config files.

| Setting | Description |
|---|---|
| **Unlock Framerate** | Patches 7 framerate cap offsets — removes the 30fps lock in story mode and gameplay |
| **Unlock Cutscene FPS** | Removes the framerate cap during cutscenes *(experimental)* |
| **Menu FPS (MaxSimFps)** | Adjusts the simulation FPS for menus — slider + spinbox for precision. Default: 60 Hz |
| **Disable V-Sync During Loading** | NOPs 3 vsync jump instructions during loading screens — higher FPS = faster loads |
| **Enhanced Motion Blur** | Increases motion blur sample quality |
| **Higher Quality Shadows** | Raises shadow rendering quality |
| **Enhanced Reflections** | Improves real-time reflection fidelity |
| **RenderDoc Integration** | Launches RenderDoc for frame capture and GPU debugging |

> ⚠️ Change Menu FPS with caution — values outside the normal range can affect physics simulation.

---

### ⏱️ Speedrun Tools Tab

A purpose-built loadless timer for accurate speedrun timing. The tool monitors the game's internal vehicle state and automatically pauses the timer during loading screens, cutscenes, and moments when the player has no control.

```
┌─────────────────────────┐
│      00:04:23.817       │  ← Running time (excludes loads)
│  Loading Time: 00:00:41 │  ← Total time spent loading
│  Status: Running ●      │  ← Live game state
└─────────────────────────┘
```

| Control | Action |
|---|---|
| **Start** | Begins the timer and clears all splits |
| **Split** | Records a split at the current time |
| **Stop** | Stops the timer |
| **Reset** | Clears the timer and all split data |
| **Export Splits** | Saves all splits to a `.json` file |
| **Copy Time** | Copies the current time string to clipboard |
| **Auto-Split** | Automatically records a split at each checkpoint |

**How the loadless detection works:**

The monitor thread queries the game's vehicle state 30 times per second via a pointer chain resolved from the game's base address:

```
[[[[base + 0x2A8598C] + 0x1B8] + 0x38] + 0xD0]
```

The vehicle state is mapped to one of 8 values:

| Value | State | Timer |
|---|---|---|
| 0 | OnGround | ▶ Running |
| 1 | InAir | ⏸ Paused |
| 2 | Landing | ⏸ Paused |
| 3 | Tumbling | ⏸ Paused |
| 4 | Collided | ⏸ Paused |
| 5 | Totalled | ⏸ Paused |
| 6 | StartTumble | ⏸ Paused |
| 7 | Dead | ⏸ Paused |

---

### 🚗 Vehicle Mods Tab

Quick toggles for common vehicle behaviour changes, plus a full Vehicle Customizer window.

| Option | Description |
|---|---|
| **Disable All Assists** | Patches 7 assist-related memory offsets (ABS, traction control, etc.) |
| **Infinite NOS** | Freezes both the NOS tank level and the consumption rate offsets |
| **No Vehicle Damage** | Writes max health to all 3 vehicle damage offsets |

#### Vehicle Customizer

Click **Open Vehicle Customizer** to open a dedicated 700×600 window with four tabs:

**Vehicle** — Swap the current car instantly:

| Car | Hash |
|---|---|
| Porsche 911 GT3 RS 4.0 | `0xA998E13D` |
| Nissan GT-R R35 | `0xCE5A5DEB` |
| Lamborghini Gallardo | `0xFB1C95C1` |
| BMW M3 GTS | `0x2012C92C` |
| Ford Mustang Boss 302 | `0xDE2611F3` |
| Chevrolet Camaro SS | `0x9121385E` |
| Audi R8 | `0xCED5A7B6` |

**Bodykit** — Change the visual kit:

| Kit | ID |
|---|---|
| Stock | `0x00` |
| Time Attack | `0x01` |
| Aero Pack | `0x02` |
| Circuit Racer | `0x03` |

**Paint** — Apply a paint colour:

| Colour | Hash |
|---|---|
| Metallic Blue | `0x257F2512` |
| Matte Black | `0x4E9BBE75` |
| Glossy White | `0xC494BC78` |
| Carbon Fiber | `0x1780E1` |

**Performance** — Set the vehicle performance tier from 1 to 6 via slider.

**Preset Manager** — Save and load any combination of vehicle, bodykit, paint, and performance tier as a `.json` file.

---

### 🌅 Visual Enhancements Tab

| Setting | Range | Description |
|---|---|---|
| **Light Intensity** | 0.0 – 3.0 | Adjusts world render light multiplier |
| **Sun Position X** | -180° – 180° | Rotates the sun horizontally |
| **Sun Position Y** | -180° – 180° | Rotates the sun vertically |
| **Force Headlights** | On / Off | Forces vehicle headlights on at all times |

---

### 🔧 Game Tweaks Tab

| Action | Description |
|---|---|
| **Unlock All Vehicles** | Grants access to all vehicles in the roster |
| **Unlock All Challenges** | Unlocks all challenge events |
| **Apply All Crash Bypasses** | Fixes tunnel and Chicago-specific crash triggers |
| **Disable Reset Triggers** | Prevents forced vehicle resets in certain race segments |

---

## 🗂️ Repository Structure

```
nfstr/
├── main.py                              # Main application — all GUI and memory logic
├── Data.xml                             # Cheat Engine table data (10,902 entries, 806 KB)
├── NFSTR.rcnet                          # RCNet configuration
└── The Run Master Table by _mRally2.CT  # Cheat Engine table by community member _mRally2
```

---

## ⚙️ How It Works

The suite uses [`pymem`](https://github.com/srounet/Pymem) to open a handle to the game's process and perform direct memory reads and writes. All memory access is thread-safe using `threading.Lock()`.

For addresses that fall in protected memory regions, the tool uses the Windows `VirtualProtectEx` API (via `ctypes`) to temporarily change the page permissions to `PAGE_EXECUTE_READWRITE`, perform the write, then restore the original protection flags.

The background monitor thread runs at 30 Hz and uses an exponential backoff strategy on errors, dropping to a minimum of 15 Hz to avoid hammering a game that may be loading or paused. It tracks process liveness using `psutil` with a direct memory read as fallback.

```
Game Process (Need for Speed The Run.exe)
        │
        ▼
   pymem handle
        │
        ├── Direct offset writes  (vehicle, visuals, assists, NOS, damage)
        ├── Pointer chain reads   (vehicle state for loadless timer)
        ├── Byte patching / NOPs  (framerate unlock, vsync bypass)
        └── VirtualProtectEx      (protected region writes)
```

---

## ❓ Troubleshooting

| Problem | Fix |
|---|---|
| **"Not Connected"** on launch | Make sure the game is running before starting the tool, and that you're on v1.1.0.0 |
| **Tool needs to be run as Administrator** | Right-click `main.py` → Run as administrator, or launch from an elevated terminal |
| **Memory write errors in console** | Some offsets are only valid during active gameplay — try applying changes once in-race |
| **Timer not pausing on loads** | The vehicle pointer chain may be stale — reconnect the tool while in the main menu |
| **Antivirus flagging the tool** | Process memory access triggers heuristic AV alerts — this is a false positive. Review the source code yourself to verify |

---

## 🤝 Credits

- **_mRally2** — Cheat Engine master table included in this repo
- The NFS The Run modding and speedrunning community for memory research and documentation

---

## 📄 License

This project is licensed under the MIT License. *Need for Speed: The Run* is a trademark of Electronic Arts Inc. This project is not affiliated with or endorsed by EA.

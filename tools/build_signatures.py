#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import struct
import sys

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
except ImportError:
    print("This build script needs Keystone: pip install keystone-engine --break-system-packages")
    sys.exit(1)

ks = Ks(KS_ARCH_X86, KS_MODE_32)
REF_BASE = 0x00400000


def asm(lines, addr: int = 0) -> bytes:
    src = lines if isinstance(lines, str) else "\n".join(lines)
    encoding, _ = ks.asm(src, addr)
    if encoding is None:
        raise ValueError(f"Keystone failed to assemble:\n{src}")
    return bytes(encoding)


def hx(b: bytes) -> str:
    return b.hex().upper()


SIGNATURES: list[dict] = []
_ids: set[str] = set()


def add(**entry):
    assert entry["id"] not in _ids, f"duplicate id {entry['id']}"
    _ids.add(entry["id"])
    SIGNATURES.append(entry)


def add_nop(id_, label, category, rva, original_asm, desc, risk="low", already_rva=False):
    abs_addr = (REF_BASE + rva) if already_rva else rva
    original = asm(original_asm, abs_addr)
    add(id="".join(id_) if isinstance(id_, list) else id_, label=label, category=category,
        source="MT", desc=desc, patch_type="nop",
        historical_rva=(rva if already_rva else rva - REF_BASE),
        hook_len=len(original), verify_bytes=hx(original), risk=risk)


add_nop("crash_tunnel_of_pain", "Fix: Tunnel of Pain crash", "Crash Fixes",
        0x0121D23B, "cmp word ptr [esi], dx",
        "Prevents the Tunnel of Pain / Coastal Rush stage crash.")

add_nop("crash_chicago_a", "Fix: Chicago Interstate crash (A)", "Crash Fixes",
        0x00E4EB60, "mov [eax+0x90], edx",
        "First of two patches preventing the Chicago Interstate action-level crash.")

add_nop("crash_chicago_b", "Fix: Chicago Interstate crash (B)", "Crash Fixes",
        0x00E50F0E, "mov [edi+0x90], eax",
        "Second of two patches preventing the Chicago Interstate action-level crash.")

add_nop("timer_checkpoint_disable_a", "Disable checkpoint timer (1/2)", "Timers",
        0x008FBF06, "movss [ecx+0x580], xmm0",
        "Part of disabling the per-checkpoint countdown timer. WARNING: this "
        "NOPs the *write* of the live timer/progress value rather than "
        "gating the downstream fail-check, so the field it writes never "
        "updates again -- confirmed to also freeze the distance-to-finish "
        "and stage-leader-timer HUD, and to break overtake / 'clean pass' "
        "detection, since those evidently read the same struct field. This "
        "is inherent to the source cheat (byte-identical to Master Table's "
        "own 'Checkpoint Timer Disable'), not a bug in this tool -- a real "
        "fix would require finding and gating the downstream fail-condition "
        "compare/branch instead of the write, which needs a disassembler "
        "against this exact build (not available in this project).")

add_nop("timer_checkpoint_disable_b", "Disable checkpoint timer (2/2)", "Timers",
        0x013DB998, "movss [eax+0x4], xmm0",
        "Part of disabling the per-checkpoint countdown timer. Same write-"
        "hazard caveat as timer_checkpoint_disable_a above -- see that entry.")

add_nop("timer_reset_oob_disable", "Disable out-of-bounds reset timer", "Timers",
        0x007FAA8C, "fld dword ptr [ecx+0x68]",
        "Stops the game from force-resetting your car after going out of bounds.")

add_nop("timer_wrong_way_respawn_disable", "Disable wrong-way respawn", "Timers",
        0x00408915, "fld dword ptr [esi+0x2924]",
        "Stops the automatic respawn triggered by driving the wrong way.",
        already_rva=True)

add_nop("timer_rival_getting_away_disable", "Disable 'rival getting away' timer", "Timers",
        0x008CFB6E, "movss xmm0, [esi+0x24]",
        "Stops the timer that fails a race when a rival pulls too far ahead. "
        "Investigated as a suspect for a reported distance/pass-detection "
        "freeze and cleared: this NOPs a *read* at a different address than "
        "the checkpoint-timer writes, and disabling it alone does not "
        "reproduce the freeze -- see timer_checkpoint_disable_a's note for "
        "the confirmed cause.")

add_nop("assist_drift_forces_disable", "Disable drift assist forces", "Assists",
        0x0181AA64, "call 0x0181A8E0",
        "Part of 'Disable All Vehicle Assists' -- NOPs the call that applies "
        "drift-correcting forces. `original_asm` here is a CALL to an "
        "absolute target, so it's position-dependent -- add_nop() assembles "
        "it at its real hook address (0x181AA64) rather than address 0. An "
        "earlier version of this file didn't, which silently produced the "
        "wrong rel32 (E8 DB A8 81 01 instead of the correct E8 77 FE FF FF) "
        "and made this entry fail live byte verification 100% of the time.")


add(id="ui_show_hidden_options", label="Show hidden UI options / unlock vehicle list gate",
    category="UI", source="MT / EUO",
    desc="Flips the visibility check so hidden menu items (and the full vehicle "
         "list gate) are always shown. 'Researched and discovered by _mRally2'.",
    patch_type="jcc_force_jmp", historical_rva=0x00968F50 - REF_BASE,
    verify_bytes=None, risk="medium")

add(id="assist_align_to_road", label="Disable Align-To-Road assist", category="Assists",
    source="MT", desc="Part of 'Disable All Vehicle Assists'.",
    patch_type="jcc_invert", historical_rva=0x0069B167 - REF_BASE,
    verify_bytes="75", risk="low")

add(id="assist_override_drift_intent", label="Disable Override-Drift-Intent assist",
    category="Assists", source="MT", desc="Part of 'Disable All Vehicle Assists'.",
    patch_type="jcc_invert", historical_rva=0x0069B5E2 - REF_BASE,
    verify_bytes="74", risk="low")

add(id="assist_drift_physics_enhance", label="Enhanced drift physics", category="Assists",
    source="MT", desc="Flips a single jcc that gates an alternate drift-physics code path.",
    patch_type="jcc_invert", historical_rva=0x0069AF4D - REF_BASE,
    verify_bytes="74", risk="low")

add(id="assist_rla_calc_skip", label="Skip Race Line Assist calculation", category="Assists",
    source="MT", desc="Part of 'Disable All Vehicle Assists': converts a conditional "
         "'ja' into an unconditional jump so the RLA calculation is always skipped.",
    patch_type="jcc_force_jmp", historical_rva=0x018199A6 - REF_BASE,
    verify_bytes="0F87", risk="medium")

add(id="assist_rla_forces_disable", label="Disable Race Line Assist forces", category="Assists",
    source="MT", desc="Part of 'Disable All Vehicle Assists'.",
    patch_type="jcc_invert", historical_rva=0x01819AB1 - REF_BASE,
    verify_bytes="0F84", risk="medium")

add(id="assist_drift_intents_skip", label="Skip Drift Intents calculation", category="Assists",
    source="MT", desc="Part of 'Disable All Vehicle Assists'.",
    patch_type="jcc_force_jmp", historical_rva=0x01828E73 - REF_BASE,
    verify_bytes="0F84", risk="medium")

add(id="game_unlock_all_vehicles", label="Unlock all vehicles", category="Game",
    source="MT", desc="Forces the vehicle-ownership gate to always pass. The source "
         "CT does this via a code cave that writes a flag then falls through to "
         "the *same* conditional jump; forcing that jump directly reaches the "
         "identical end state without needing a cave.",
    patch_type="jcc_force_jmp",


    historical_rva=0x0053D629 + 3,
    verify_bytes=None, risk="medium")

add(id="game_unlock_all_challenges", label="Unlock all Challenge Series events", category="Game",
    source="MT", desc="Forces the challenge-unlocked gate to always pass, by making "
         "the 'je' that gates it unconditional.",
    patch_type="jcc_force_jmp",


    historical_rva=0x0045B162 + 4,
    verify_bytes=None, risk="medium")


def add_byte_write(id_, label, category, rva, on_asm, off_asm, desc, risk="medium",
                     aob=None, aob_off=None):
    en = on_asm if isinstance(on_asm, (bytes, bytearray)) else asm(on_asm)
    de = off_asm if isinstance(off_asm, (bytes, bytearray)) else asm(off_asm)
    assert len(en) == len(de), f"{id_}: enabled/disabled length mismatch"
    kwargs = dict(id=id_, label=label, category=category, source="MT", desc=desc,
                   patch_type="byte_write", hook_len=len(en),
                   enabled_bytes=hx(en), disabled_bytes=hx(de),
                   verify_bytes=hx(de), risk=risk)
    if aob:
        kwargs["aob"] = aob
        kwargs["aob_result_offset"] = aob_off
    else:
        kwargs["historical_rva"] = rva - REF_BASE
    add(**kwargs)


add_byte_write("assist_rla_status_off", "Force Race Line Assist status = Off", "Assists",
    0x01819981, "mov dword ptr [edi+0x50], 0", "mov dword ptr [edi+0x50], 2",
    "Part of 'Disable All Vehicle Assists' (sets RaceLineAssist_Off).", risk="low")

add_byte_write("vehicle_blown_tires_flag", "Force blown-tire flag", "Vehicle",
    0x0069B0E1, "mov byte ptr [esi+0x110], 1", "mov byte ptr [esi+0x114], 0",
    "Directly sets the blown-tire flag byte. The source CT's enable/disable "
    "blocks target two different offsets (+110 / +114) at the same address. "
    "An earlier version of this file 'fixed' that by using +110 for both -- "
    "but +0x114,0 is what's actually sitting at this address in an unpatched "
    "game (compare assist_rla_status_off below, same pattern: the disable "
    "state is the vanilla instruction, not a toggled-off value), so unifying "
    "it to +110 replaced verify_bytes with an instruction the live game never "
    "has, and the signature failed calibration 100% of the time. Reverted to "
    "match source: enable forces the blown-tire flag on; disable restores the "
    "exact original instruction rather than clearing +110 itself, so the tire "
    "may stay flagged blown until the game's own logic clears it (e.g. pit/ "
    "level reload) -- a real limitation of the source cheat, not a bug here.")

add_byte_write("vehicle_engine_blown_flag", "Force engine-blown flag", "Vehicle",
    0x0069B09D, "mov byte ptr [esi+0x10D], 1", "mov byte ptr [esi+0x10D], 0",
    "Directly sets the blown-engine flag byte.")


def make_cave_bytes(new_asm, original_asm) -> tuple[bytes, int, int, bytes]:
    original = asm(original_asm)
    body = asm(new_asm) + original
    body += b"\x90" * 5
    return body, len(body) - 5, len(original), original


_REG_FAMILIES = {
    "eax": {"eax", "ax", "al", "ah"}, "ebx": {"ebx", "bx", "bl", "bh"},
    "ecx": {"ecx", "cx", "cl", "ch"}, "edx": {"edx", "dx", "dl", "dh"},
    "esi": {"esi", "si"}, "edi": {"edi", "di"},
}
_REG_FAMILY_OF = {alias: fam for fam, aliases in _REG_FAMILIES.items() for alias in aliases}


def _stack_delta(asm_lines) -> int:
    delta = 0
    for line in asm_lines:
        w = line.strip().lower().split()
        if not w:
            continue
        if w[0] == "push":
            delta += 1
        elif w[0] == "pop":
            delta -= 1
    return delta


def _forced_dest_register(new_asm) -> str | None:
    dest = None
    for line in new_asm:
        m = re.match(r"mov\s+(\w+)\s*,\s*\[\s*ebx\s*\]", line.strip(), re.I)
        if m:
            dest = _REG_FAMILY_OF.get(m.group(1).lower())
    return dest


def _check_no_register_hazard(id_, new_asm, replay_lines):
    dest = _forced_dest_register(new_asm)
    if dest is None or not replay_lines:
        return
    first = replay_lines[0].lower()


    bracket_match = re.search(r"\[([^\]]*)\]", first)
    if not bracket_match:
        return
    inside = bracket_match.group(1)
    tokens = re.findall(r"[a-z]+", inside)
    for t in tokens:
        if _REG_FAMILY_OF.get(t) == dest:
            raise AssertionError(
                f"{id_}: register hazard -- '{dest}' receives the forced value "
                f"in new_asm, but the first replayed instruction ({replay_lines[0]!r}) "
                f"still uses '{t}' for addressing. Replaying it will read from "
                f"[forced_value + offset] instead of the real object. Use "
                f"replay_asm= to skip/adjust the hazardous instruction."
            )


def add_codecave(id_, label, category, rva, new_asm, original_asm, desc,
                   value_offset_marker=None, value_type=None, risk="medium",
                   internal=False, replay_asm=None):
    forced = asm(new_asm)
    original = asm(original_asm)
    replay_lines = replay_asm if replay_asm is not None else original_asm
    to_replay = asm(replay_lines)


    combined_delta = _stack_delta(new_asm) + _stack_delta(replay_lines)
    original_delta = _stack_delta(original_asm)
    assert combined_delta == original_delta, (
        f"{id_}: stack imbalance -- new_asm+replay net push/pop = "
        f"{combined_delta}, but the real original instructions being "
        f"replaced have net effect {original_delta}. A mismatch here means "
        f"this hook will misalign the stack every time it fires."
    )
    _check_no_register_hazard(id_, new_asm, replay_lines)

    body = forced + to_replay + b"\x90" * 5
    return_off = len(body) - 5

    value_offset = None
    if value_offset_marker is not None:
        occurrences = body.count(value_offset_marker)
        assert occurrences == 1, (
            f"{id_}: value marker {value_offset_marker.hex()} found "
            f"{occurrences} times in assembled cave body (need exactly 1)"
        )
        value_offset = body.find(value_offset_marker)

    add(id=id_, label=label, category=category, source="MT", desc=desc,
        patch_type="codecave", historical_rva=rva,
        cave_body=hx(body), return_jmp_offset=return_off,
        hook_len=len(original), verify_bytes=hx(original),
        value_offset=value_offset, value_type=value_type,
        risk=risk, internal=internal)


_marker = struct.pack("<I", 0x40000000)
add_codecave("traffic_density_scale", "Traffic density scale", "Traffic",
    0x00E5EEF6,
    new_asm=["push ebx", "lea ebx, [ecx]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "movss xmm0, [ebx]", "and eax, -4", "pop ebx"],
    original_asm=["movss xmm0, [ecx]", "and eax, -4"],
    desc="Default game value scaled by this factor; lower = less traffic density. "
         "Adjustable -- default patch value 0.05.",
    value_offset_marker=_marker, value_type="float", risk="medium")

_marker = struct.pack("<I", 0x40000000)
add_codecave("traffic_max_density", "Traffic max density", "Traffic",
    0x00E5EEE9,
    new_asm=["push ebx", "lea ebx, [eax+0x1C]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "movss xmm2, [ebx]", "pop ebx"],
    original_asm=["movss xmm2, [eax+0x1C]"],
    desc="Adjustable -- default patch value 0.15.",
    value_offset_marker=_marker, value_type="float", risk="medium")

_marker = struct.pack("<I", 0x7fffffff)
add_codecave("traffic_vehicle_limit", "Traffic vehicle limit", "Traffic",
    0x00E5A9A3,
    new_asm=["push ebx", "lea ebx, [eax+0x60]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "mov eax, [ebx]", "pop ebx"],
    original_asm=["mov eax, [eax+0x60]", "cmp eax, 0x19"],


    replay_asm=["cmp eax, 0x19"],
    desc="Adjustable -- default patch value 25.",
    value_offset_marker=_marker, value_type="int", risk="medium")


_marker = struct.pack("<I", 0x7fffffff)
add_codecave("ai_difficulty_expert", "Force AI difficulty", "AI / Race Setup",
    0x0044A6C5,
    new_asm=["push ebx", "lea ebx, [eax+0x2C]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "mov edi, [ebx]", "test ecx, ecx", "pop ebx"],
    original_asm=["mov edi, [eax+0x2C]", "test ecx, ecx"],
    desc="Adjustable -- default patch value 3 (Expert).",
    value_offset_marker=_marker, value_type="int", risk="medium")

add_codecave("ai_enable_in_events", "Force-enable AI in events", "AI / Race Setup",
    0x00FCC0B9,
    new_asm=["push ebx", "lea ebx, [ecx+0x7D]", "mov byte ptr [ebx], 1",
              "mov dl, [ebx]", "pop ebx", "mov [esi+0x5C3], dl"],
    original_asm=["mov dl, [ecx+0x7D]", "mov [esi+0x5C3], dl"],
    desc="Ensures AI opponents are present even in events that default to none.",
    risk="medium")

_marker = struct.pack("<I", 0x7fffffff)
add_codecave("ai_number_of_players", "Number of opponents override", "AI / Race Setup",
    0x00FCC0D1,
    new_asm=["push ebx", "lea ebx, [ecx+0x70]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "mov edx, [ebx]", "pop ebx", "mov [esi+0x5C8], edx"],
    original_asm=["mov edx, [ecx+0x70]", "mov [esi+0x5C8], edx"],
    desc="Adjustable -- includes the player in the count. Some events break if "
         "increased too far (source warning).",
    value_offset_marker=_marker, value_type="int", risk="medium")

_marker = struct.pack("<I", 0x7fffffff)
add_codecave("ai_player_grid_position", "Player starting grid position", "AI / Race Setup",
    0x00FCC0DD,
    new_asm=["push ebx", "lea ebx, [eax+0x74]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "mov ecx, [ebx]", "pop ebx", "mov [esi+0x5CC], ecx"],
    original_asm=["mov ecx, [eax+0x74]", "mov [esi+0x5CC], ecx"],
    desc="Adjustable -- 1-based starting position.",
    value_offset_marker=_marker, value_type="int", risk="medium")

add_codecave("game_no_vehicle_event_restriction", "Remove vehicle event restrictions",
    "Game", 0x0048D46C,
    new_asm=["push ebx", "lea ebx, [esi+0x48]", "mov dword ptr [ebx], 0",
              "mov ecx, [ebx]", "pop ebx"],


    original_asm=["mov ecx, [esi+0x48]", "push 0"],
    desc="Lets any vehicle enter any event by nulling the CarFilter restriction pointer.",
    risk="medium")

_marker = struct.pack("<I", 0x40a00000)
add_codecave("game_difficulty_scalar", "Difficulty scalar", "AI / Race Setup",
    0x00E61ED9,
    new_asm=["push ebx", "lea ebx, [eax]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "movss xmm0, [ebx]", "movss xmm1, [esi+0x0C]", "pop ebx"],
    original_asm=["movss xmm0, [eax]", "movss xmm1, [esi+0x0C]"],
    desc="Adjustable -- default patch value 5.0.",
    value_offset_marker=_marker, value_type="float", risk="medium")

_marker = struct.pack("<I", 0x3f333333)
add_codecave("game_glue_scalar", "Glue (traction) scalar", "AI / Race Setup",
    0x00E61EA1,
    new_asm=["push ebx", "lea ebx, [eax]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "movss xmm0, [ebx]", "movss xmm1, [esi+0x08]", "pop ebx"],
    original_asm=["movss xmm0, [eax]", "movss xmm1, [esi+0x08]"],
    desc="Adjustable -- default patch value 0.7.",
    value_offset_marker=_marker, value_type="float", risk="medium")

_marker = struct.pack("<I", 0x42ca0000)
add_codecave("vehicle_damage_threshold", "Vehicle damage / detach threshold", "Vehicle",
    0x00BDF4B0,
    new_asm=["push ebx", "lea ebx, [edi+eax*4+0x10]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "movss xmm2, [ebx]", "pop ebx"],
    original_asm=["movss xmm2, [edi+eax*4+0x10]"],
    desc="Values above 100 make parts effectively undetachable -- a cosmetic "
         "'reduced damage' effect. Adjustable, default patch value 101.",
    value_offset_marker=_marker, value_type="float", risk="medium")

_marker = struct.pack("<I", 0x4)
add_codecave("tod_career_challenge", "Time of Day (Career / Challenge Series)", "World",
    0x0059BF25,
    new_asm=["push ebx", "lea ebx, [eax+0x64]", f"mov dword ptr [ebx], {int.from_bytes(_marker,'little')}",
              "mov ecx, [ebx]", "pop ebx"],


    original_asm=["mov ecx, [eax+0x64]", "push 1"],
    desc="Adjustable TOD preset index -- default patch value 4. WARNING: "
         "valid preset indices are level-specific, not a universal 0-5 "
         "range -- confirmed against the source repo's own Time-of-Day-"
         "Randomizer script, which keys a per-level whitelist off each "
         "level's GUID (e.g. one level only supports {0,3}, another only "
         "{0,1,4}, etc). Forcing an index the current level doesn't support "
         "is the confirmed cause of the sky turning solid blue with broken "
         "reflections/lighting -- and because the field is only consumed "
         "once per lighting setup, reverting to a valid value afterward "
         "does not re-trigger that setup; the corruption persists until the "
         "next level/stage load. 4 is the value the source cheat itself "
         "defaults to and is broadly safe; treat 1/2/3/5 as level-specific "
         "and expect to reload the stage if the sky corrupts.",
    value_offset_marker=_marker, value_type="int", risk="medium")


_placeholder = b"\x44\x33\x22\x11"


def add_data_slot_cave(id_, label, category, rva, new_asm, original_asm, desc, risk="medium"):
    forced = asm(new_asm)
    original = asm(original_asm)
    body = forced + original + b"\x90" * 5
    return_off = len(body) - 5
    occurrences = body.count(_placeholder)
    assert occurrences == 1, f"{id_}: data-slot placeholder found {occurrences} times (need exactly 1)"
    add(id=id_, label=label, category=category, source="MT", desc=desc,
        patch_type="codecave", historical_rva=rva,
        cave_body=hx(body), return_jmp_offset=return_off,
        hook_len=len(original), verify_bytes=hx(original),
        data_slot_size=4, internal=True, risk=risk)


ph_int = int.from_bytes(_placeholder, "little")
add_data_slot_cave("cave_gametime_hook", "(internal) GameTime pointer hook", "internal",
    0x00A607F7,
    new_asm=["push edi", "lea edi, [eax+0x40]", f"mov dword ptr [{hex(ph_int)}], edi", "pop edi"],
    original_asm=["mov cl, [eax+0x40]", "mov eax, [ebx+0x08]"],
    desc="Exposes the live GameTime struct pointer. Drives "
         "'perf_unlock_framerate' below -- has no toggle of its own.")

add_data_slot_cave("cave_player_control_hook", "(internal) Player-vehicle-control hook", "internal",
    0x003F6C73,
    new_asm=["push ebx", "lea ebx, [esi+0x04]", f"mov dword ptr [{hex(ph_int)}], ebx", "pop ebx"],
    original_asm=["cmp byte ptr [esi+0x04], 0", "push edi"],
    desc="Exposes a pointer to the 'does the player currently have vehicle "
         "control' byte; surfaced as a read-only status indicator, not a toggle.")


add(id="perf_variable_tick_enable", label="(internal, currently unused) variable simulation tick",
    category="internal", source="MT", desc="Not forced by anything -- see comment above.",
    patch_type="cave_field_freeze", cave_ref="cave_gametime_hook",
    field_offset=0x00, value_type="int", internal=True, risk="medium")

add(id="perf_unlock_framerate", label="Unlock gameplay framerate", category="Performance",
    source="MT", desc="Removes the 30fps gameplay cap by continuously writing the "
         "desired value into MaxVariableFps once the GameTime struct is captured "
         "(happens automatically the moment gameplay reaches that code -- typically "
         "immediately after loading into a race). Only touches MaxVariableFps -- "
         "does not force VariableSimTickTimeEnable (see the comment above; an "
         "earlier version did, which is the suspected cause of a reported "
         "camera side effect).",
    patch_type="cave_field_freeze", cave_ref="cave_gametime_hook",
    field_offset=-0x18, value_type="float", risk="medium")


add(id="vehicle_swap_car_object", label="Swap current car (Car Object)", category="Vehicle",
    source="MT", desc="Writes a vehicle hash ID through the static Car Object "
         "pointer chain. Works reliably in single-player Challenge Series/story "
         "events (source note: does not work in multiplayer). See "
         "data/vehicles.json for the full real vehicle hash list.",

    patch_type="pointer_write", historical_rva=0x023B8D58,
    offsets=[0x3C8], risk="medium")

add(id="ui_hud_toggle", label="HUD visibility (poke value)", category="UI", source="EUO",
    desc="Two-level pointer chain to the in-race HUD visibility byte. The source "
         "CT exposes this as a plain editable value (not a scripted on/off "
         "pair), so which raw byte means 'hidden' vs 'visible' isn't confirmed -- "
         "try 0 and 1 in a race and see which does what.",
    patch_type="pointer_write",
    historical_rva=0x0288B55C - REF_BASE, offsets=[0x5B8, 0x0C],
    value_type="u8", risk="low")


def self_check():
    for e in SIGNATURES:
        pt = e["patch_type"]
        if pt == "codecave":
            body = bytes.fromhex(e["cave_body"])
            off = e["return_jmp_offset"]
            assert body[off:off + 5] == b"\x90" * 5, f"{e['id']}: bad jmp-back placeholder"
            if e.get("value_offset") is not None:
                assert 0 <= e["value_offset"] < len(body) - 3, f"{e['id']}: bad value_offset"
        if pt == "cave_field_freeze":
            assert e["cave_ref"] in _ids, f"{e['id']}: unknown cave_ref"
        if e.get("aob"):
            fixed = sum(1 for p in e["aob"].split() if p != "??")
            assert fixed >= 4, f"{e['id']}: AOB pattern too weak ({e['aob']})"
        if pt in ("nop", "byte_write") and e.get("verify_bytes"):
            assert len(bytes.fromhex(e["verify_bytes"])) == e["hook_len"],                f"{e['id']}: verify_bytes length != hook_len"


def main():
    self_check()
    out_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "signatures.json"))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(SIGNATURES, f, indent=1)
    print(f"Wrote {len(SIGNATURES)} signatures -> {out_path}")
    by_type: dict[str, int] = {}
    for e in SIGNATURES:
        by_type[e["patch_type"]] = by_type.get(e["patch_type"], 0) + 1
    for k, v in sorted(by_type.items()):
        print(f"  {k:<18} {v}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
midi_cues.py (v4 - regression fix)

Fixes:
- Default to CUES mode at startup (prevents jukebox surprise)
- Program Change uses +1 offset (OnSong PC 0 => cue 1)
- Debounce for program changes + note actions
- Optional MIDI debug logging (set MIDI_DEBUG=1)

Plays:
- wav/mp3: mpv (preferred) or aplay/mpg123 fallback
- mid/midi: aplaymidi -> ALSA port from config.json

Control:
- Web control via /home/fc/showbox/control.json (one-shot command)
- State/Now Playing via /home/fc/showbox/state.json
"""

import json
import os
import random
import shutil
import subprocess
import threading
import time
from pathlib import Path
import mido

# ---- Paths ----
BASE = Path("/home/fc/showbox")
CUES_DIR = BASE / "cues"
JUKE_SONGS = BASE / "jukebox" / "songs"
JUKE_LISTS = BASE / "jukebox" / "playlists"
CFG_PATH = BASE / "config.json"
STATE_PATH = BASE / "state.json"
CONTROL_PATH = BASE / "control.json"

# ---- Supported media ----
AUDIO_EXTS = {".wav", ".mp3"}
MIDI_EXTS = {".mid", ".midi"}
ALL_EXTS = AUDIO_EXTS | MIDI_EXTS

# ---- MIDI mapping (your proven note numbers) ----
NOTE_ACTIONS = {
    24: "go",    # C1
    25: "back",  # C#1
    26: "fire",  # D1
    27: "stop",  # D#1
}

# IMPORTANT: OnSong Program Change is 0-based. We want cue numbers 1-based.
PROGRAM_CHANGE_OFFSET = 1

# ---- Debounce ----
PC_DEBOUNCE_SEC = 0.20
NOTE_DEBOUNCE_SEC = 0.25
GO_DEBOUNCE_SEC = 0.4   # adjust if needed
_last_go_time = 0.0

# ---- MIDI port selection ----
PORT_NAME_HINT = "Midi Through"  # fallback search
# Better: set "midi_in_port" in config.json to exact mido port string

# ---- Runtime state ----
current_cue = None
playlist_index = 0

running_proc = None
running_lock = threading.Lock()
playback_watcher = None
stop_watcher = threading.Event()

# debouncing
_last_pc_time = 0.0
_last_pc_val = None
_last_action_time = {}  # action -> timestamp

# ---- Binaries ----
APLAY = shutil.which("aplay")
APLAYMIDI = shutil.which("aplaymidi")
MPV = shutil.which("mpv")
MPG123 = shutil.which("mpg123")

MIDI_DEBUG = os.environ.get("MIDI_DEBUG", "").strip() in ("1", "true", "yes", "on")


def go_debounced() -> bool:
    global _last_go_time
    now = time.time()
    if now - _last_go_time < GO_DEBOUNCE_SEC:
        return True
    _last_go_time = now
    return False


def log(msg: str) -> None:
    print(msg, flush=True)


def ensure_dirs() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    CUES_DIR.mkdir(parents=True, exist_ok=True)
    JUKE_SONGS.mkdir(parents=True, exist_ok=True)
    JUKE_LISTS.mkdir(parents=True, exist_ok=True)


def _default_cfg() -> dict:
    return {
        "mode": "cues",
        "midi_in_port": "",         # optional exact mido port name
        "midi_out_port": "14:0",
        "jukebox": {"play_mode": "random", "playlist": "default.json"},
    }


def load_cfg() -> dict:
    if not CFG_PATH.exists():
        cfg = _default_cfg()
        CFG_PATH.write_text(json.dumps(cfg, indent=2))
        return cfg

    try:
        cfg = json.loads(CFG_PATH.read_text())
    except Exception as e:
        log(f"WARNING: config.json invalid, restoring defaults: {e}")
        cfg = _default_cfg()
        CFG_PATH.write_text(json.dumps(cfg, indent=2))
        return cfg

    # ensure required structure
    if "jukebox" not in cfg or not isinstance(cfg.get("jukebox"), dict):
        cfg["jukebox"] = {"play_mode": "random", "playlist": "default.json"}

    if "midi_out_port" not in cfg:
        cfg["midi_out_port"] = "14:0"

    if "mode" not in cfg:
        cfg["mode"] = "cues"

    if "midi_in_port" not in cfg:
        cfg["midi_in_port"] = ""

    return cfg


def save_cfg(cfg: dict) -> None:
    try:
        CFG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception as e:
        log(f"WARNING: failed writing config.json: {e}")


def force_startup_defaults() -> None:
    # Stage-safe: always boot into cues mode.
    cfg = load_cfg()
    if cfg.get("mode") != "cues":
        cfg["mode"] = "cues"
        save_cfg(cfg)
    write_state(False, None)


def write_state(playing: bool, now_playing: dict | None) -> None:
    cfg = load_cfg()
    state = {
        "mode": cfg.get("mode", "cues"),
        "playing": bool(playing),
        "now_playing": now_playing,
        "midi_out_port": cfg.get("midi_out_port", ""),
        "timestamp": time.time(),
        "current_cue": current_cue,
    }
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log(f"error writing state.json: {e}")


def read_control() -> dict | None:
    if not CONTROL_PATH.exists():
        return None
    try:
        data = json.loads(CONTROL_PATH.read_text())
    except Exception as e:
        log(f"ignoring malformed control.json: {e}")
        try:
            CONTROL_PATH.unlink()
        except Exception:
            pass
        return None
    try:
        CONTROL_PATH.unlink()
    except Exception:
        pass
    return data


def find_input_port(cfg: dict) -> str:
    ports = mido.get_input_names()
    if not ports:
        raise RuntimeError("mido sees no MIDI input ports (install python3-rtmidi)")

    want = (cfg.get("midi_in_port") or "").strip()
    if want:
        for p in ports:
            if p == want or want.lower() in p.lower():
                return p
        raise RuntimeError(f"configured midi_in_port not found: {want}; available: {ports}")

    # Prefer Midi Through
    for p in ports:
        if "midi through" in p.lower():
            return p

    # Fallback hint
    for p in ports:
        if PORT_NAME_HINT.lower() in p.lower():
            return p

    return ports[0]


def load_playlist(name: str) -> dict:
    p = JUKE_LISTS / name
    if not p.exists():
        return {"name": name, "tracks": []}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"name": name, "tracks": []}


def list_jukebox_media() -> list[Path]:
    if not JUKE_SONGS.exists():
        return []
    items = []
    for p in JUKE_SONGS.iterdir():
        if p.is_file() and p.suffix.lower() in ALL_EXTS:
            items.append(p)
    return sorted(items)


def pick_random_track() -> Path | None:
    tracks = list_jukebox_media()
    return random.choice(tracks) if tracks else None


def pick_playlist_track(cfg: dict) -> Path | None:
    global playlist_index
    pl_name = cfg.get("jukebox", {}).get("playlist", "default.json")
    pl = load_playlist(pl_name)
    tracks = pl.get("tracks", [])
    if not tracks:
        return None

    if playlist_index >= len(tracks):
        playlist_index = 0

    chosen = JUKE_SONGS / tracks[playlist_index]
    playlist_index = (playlist_index + 1) % max(1, len(tracks))

    if chosen.exists() and chosen.suffix.lower() in ALL_EXTS:
        return chosen
    return None


def find_cue_file(cue_num: int) -> Path | None:
    # strict naming per your convention
    for ext in (".wav", ".mp3", ".mid", ".midi"):
        p = CUES_DIR / f"{cue_num:02d}_workcue{ext}"
        if p.exists():
            return p
    return None


def stop_playback() -> None:
    global running_proc, playback_watcher
    with running_lock:
        if running_proc:
            try:
                log(f"stopping pid={running_proc.pid}")
                running_proc.terminate()
                try:
                    running_proc.wait(timeout=2)
                except Exception:
                    running_proc.kill()
            except Exception as e:
                log(f"error stopping process: {e}")
            running_proc = None

        stop_watcher.set()
        if playback_watcher and playback_watcher.is_alive():
            playback_watcher.join(timeout=1)
        stop_watcher.clear()
        playback_watcher = None

    write_state(False, None)


def _start_and_watch(cmd: list[str], now_playing: dict, on_exit_cb) -> None:
    global running_proc, playback_watcher

    with running_lock:
        if running_proc:
            stop_playback()

        log(f"starting playback: {cmd}")
        running_proc = subprocess.Popen(cmd)
        write_state(True, now_playing)
        stop_watcher.clear()

        def watcher():
            try:
                while True:
                    if stop_watcher.is_set():
                        return
                    ret = running_proc.poll()
                    if ret is not None:
                        log(f"playback ended with code {ret}")
                        break
                    time.sleep(0.1)
                try:
                    on_exit_cb()
                except Exception as e:
                    log(f"on_exit_cb error: {e}")
            finally:
                time.sleep(0.05)

        playback_watcher = threading.Thread(target=watcher, daemon=True)
        playback_watcher.start()


def play_media(path: Path, cfg: dict, is_jukebox: bool, on_exit_cb) -> None:
    ext = path.suffix.lower()
    now = {
        "name": path.name,
        "path": str(path),
        "ext": ext,
        "is_jukebox": bool(is_jukebox),
        "start_time": time.time(),
    }

    if ext in MIDI_EXTS:
        port = cfg.get("midi_out_port", "14:0")
        if not APLAYMIDI:
            log("ERROR: aplaymidi not found (install: sudo apt-get install -y alsa-utils)")
            write_state(False, None)
            return
        cmd = [APLAYMIDI, "-p", port, str(path)]
        _start_and_watch(cmd, now, on_exit_cb)
        return

    if ext in AUDIO_EXTS:
        if MPV:
            cmd = [MPV, "--no-video", "--really-quiet", str(path)]
            _start_and_watch(cmd, now, on_exit_cb)
            return

        if ext == ".wav":
            if not APLAY:
                log("ERROR: aplay not found (install: sudo apt-get install -y alsa-utils)")
                write_state(False, None)
                return
            cmd = [APLAY, "-q", str(path)]
            _start_and_watch(cmd, now, on_exit_cb)
            return

        if ext == ".mp3":
            if not MPG123:
                log("ERROR: mpg123 not found (install: sudo apt-get install -y mpg123) OR install mpv")
                write_state(False, None)
                return
            cmd = [MPG123, "-q", str(path)]
            _start_and_watch(cmd, now, on_exit_cb)
            return

    log(f"unsupported file type: {path}")
    write_state(False, None)


def run_cue(cue_num: int, cfg: dict) -> None:
    p = find_cue_file(cue_num)
    if not p:
        log(f"no cue file found for cue {cue_num:02d}")
        write_state(False, None)
        return

    def no_auto():
        log("cue finished")
        write_state(False, None)

    play_media(p, cfg, is_jukebox=False, on_exit_cb=no_auto)


def jukebox_play_next(cfg: dict) -> None:
    mode = cfg.get("jukebox", {}).get("play_mode", "random")
    if mode == "random":
        p = pick_random_track()
    else:
        p = pick_playlist_track(cfg)

    if not p:
        log("no jukebox tracks available")
        write_state(False, None)
        return

    def advance():
        time.sleep(0.1)
        jukebox_play_next(load_cfg())

    play_media(p, cfg, is_jukebox=True, on_exit_cb=advance)


def select_cue(cue: int) -> None:
    global current_cue
    current_cue = cue
    log(f"cue selected: {current_cue:02d}")


def cue_go(cfg: dict) -> None:
    # SIMPLE, GLOBAL debounce
    if go_debounced():
        return

    if cfg.get("mode", "cues") == "jukebox":
        log("jukebox GO -> start")
        jukebox_play_next(cfg)
        return

    if current_cue is None:
        log("go ignored (no cue selected)")
        return

    log(f"GO cue {current_cue:02d}")

    # HARD stop anything already playing BEFORE starting new cue
    stop_playback()

    run_cue(current_cue, cfg)


def cue_back(cfg: dict) -> None:
    global current_cue, playlist_index

    if cfg.get("mode", "cues") == "jukebox":
        playlist_index = max(0, playlist_index - 2)
        log(f"jukebox back -> next index {playlist_index}")
        return

    if current_cue is None:
        current_cue = 1
    else:
        current_cue = max(1, current_cue - 1)
    log(f"cue selected: {current_cue:02d}")


def cue_fire(cfg: dict) -> None:
    cue_go(cfg)


def cue_stop() -> None:
    log("STOP -> stopping playback")
    stop_playback()


def process_control_command(cmd: dict | None) -> None:
    if not cmd or "cmd" not in cmd:
        return
    c = cmd["cmd"]
    cfg = load_cfg()

    if c == "mode_cues":
        cfg["mode"] = "cues"
        save_cfg(cfg)
        log("control: mode_cues")
        write_state(False, None)
    elif c == "mode_jukebox":
        cfg["mode"] = "jukebox"
        save_cfg(cfg)
        log("control: mode_jukebox")
        write_state(False, None)

    elif c == "jukebox_start":
        log("control: jukebox_start")
        cfg["mode"] = "jukebox"
        save_cfg(cfg)
        jukebox_play_next(cfg)
    elif c == "jukebox_stop":
        log("control: jukebox_stop")
        stop_playback()
    elif c == "jukebox_next":
        log("control: jukebox_next")
        stop_playback()
        jukebox_play_next(cfg)
    else:
        log(f"unknown control command: {c}")


def control_watcher() -> None:
    while True:
        try:
            cmd = read_control()
            if cmd:
                process_control_command(cmd)
        except Exception as e:
            log(f"control watcher error: {e}")
        time.sleep(0.5)


def _debounced(key: str, window_sec: float) -> bool:
    now = time.time()
    last = _last_action_time.get(key, 0.0)
    if (now - last) < window_sec:
        return True
    _last_action_time[key] = now
    return False


def handle_midi(msg, cfg: dict) -> None:
    global _last_pc_time, _last_pc_val

    if MIDI_DEBUG:
        log(f"RX: {msg}")

    if msg.type == "program_change":
        now = time.time()
        pc = int(msg.program)

        # debounce program changes (OnSong often repeats)
        if _last_pc_val == pc and (now - _last_pc_time) < PC_DEBOUNCE_SEC:
            return
        _last_pc_val = pc
        _last_pc_time = now

        new_cue = pc + PROGRAM_CHANGE_OFFSET
        if new_cue < 1:
            new_cue = 1

        if new_cue != current_cue:
            select_cue(new_cue)
        return

    # Note on (treat velocity 0 as note_off)
    if msg.type == "note_on" and int(getattr(msg, "velocity", 0)) > 0:
        note = int(msg.note)
        action = NOTE_ACTIONS.get(note)
        if not action:
            return

        if _debounced(action, NOTE_DEBOUNCE_SEC):
            return

        if action == "go":
            cue_go(cfg)
        elif action == "back":
            cue_back(cfg)
        elif action == "fire":
            cue_fire(cfg)
        elif action == "stop":
            cue_stop()
        return


def sanity_log_tools() -> None:
    log("tooling check:")
    log(f"  aplay:     {'ok' if APLAY else 'missing'}")
    log(f"  aplaymidi: {'ok' if APLAYMIDI else 'missing'}")
    log(f"  mpv:       {'ok' if MPV else 'missing'}")
    log(f"  mpg123:    {'ok' if MPG123 else 'missing'}")


def main() -> None:
    ensure_dirs()
    sanity_log_tools()

    # stage-safe boot behavior
    force_startup_defaults()

    threading.Thread(target=control_watcher, daemon=True).start()

    cfg = load_cfg()
    port = find_input_port(cfg)
    log(f"listening on MIDI input: {port}")

    with mido.open_input(port) as inp:
        for msg in inp:
            try:
                handle_midi(msg, load_cfg())
            except Exception as e:
                log(f"error handling {msg}: {e}")


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            log(f"midicues fatal: {e}")
            time.sleep(2)

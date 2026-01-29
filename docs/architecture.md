# Architecture

This document explains how ShowBox is wired and why the design is stage-safe.

---

## Design goals

- Deterministic behavior on stage
- Headless operation (SSH-only is enough)
- Observable MIDI transport (debuggable with ALSA tools)
- Web UI cannot break playback timing
- Reboots and RTP reconnects must be recoverable

---

## MIDI path

```text
OnSong (iPad)
  → RTP-MIDI
    → rtpmidid
      → ALSA sequencer
        → Midi Through Port-0 (14:0)
          → midi_cues.py
```

### Why Midi Through?

RTP peers (e.g., “iPad”) can appear on different ALSA client/port numbers after reconnects. Routing the active RTP port to **Midi Through Port-0** provides a stable destination that the cue engine can listen on forever.

---

## Control flow

### MIDI → cue engine

- **Program Change** selects cue number  
  Rule: `cue = program + 1` (PC 0 → cue 01)
- **Note On** triggers actions (GO/BACK/FIRE/STOP)
- **Global debounce** prevents double-fires and stacked playback

### Web UI → cue engine

The web UI communicates with the engine via a file-based “command mailbox”:

- Web UI writes a JSON object to: `/home/fc/showbox/control.json`
- Cue engine polls for this file, executes the command once, then deletes it

This avoids sockets, avoids racey multi-threading, and is easy to debug over SSH.

---

## Playback model

- Only one playback process at a time
- Starting a new cue stops the previous playback first
- GO is globally debounced (stage safety)

Supported playback:
- `.wav`, `.mp3` via `mpv` (preferred) or `aplay`/`mpg123` fallback
- `.mid`, `.midi` via `aplaymidi` to an ALSA destination port

---

## Startup safety

On boot:
- Mode defaults to **cues**
- A selected cue defaults to **01**
- Jukebox will not start accidentally

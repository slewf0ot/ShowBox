# ShowBox

**ShowBox** is a headless, stage-safe MIDI-driven cue and jukebox system designed for live performance.

It allows an iPad running **OnSong** to trigger audio and MIDI cues on a Raspberry Pi over RTP-MIDI, with deterministic behavior and zero GUI dependencies.

---

## Core Features

- 🎹 MIDI cue triggering via RTP-MIDI (OnSong → Raspberry Pi)
- 🎧 Plays WAV / MP3 / MIDI files
- 🎙 Offline neural TTS cue generation (Piper TTS)
- 🎛 Web UI for cue + jukebox management
- 🧠 Deterministic “show-safe” behavior (debounce, exclusive playback)
- 🔁 Fully rebuildable from a fresh OS install

---

## High-Level Architecture

OnSong (iPad)
→ RTP-MIDI
→ rtpmidid
→ ALSA Midi Through (14:0)
→ midi_cues.py
→ audio / midi playback


The web UI communicates with the cue engine via **file-based IPC**, not sockets.

---

## Repository Layout

showbox/
README.md
docs/
architecture.md
headless-rebuild.md
web-ui.md
troubleshooting.md
midi-mapping.md
services/
midicues.service
showbox-web.service
scripts/
install.sh
status.sh
midi_connect.sh
createcue
webapp/
app.py
player/
midi_cues.py
config/
config.json.example


---

## Quick Start (Existing System)

```bash
sudo systemctl status midicues
sudo systemctl status showbox-web

Web UI:

http://<pi-ip>:8080

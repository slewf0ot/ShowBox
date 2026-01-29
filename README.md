# ShowBox

**ShowBox** is a headless, stage-safe MIDI-driven cue and jukebox system for live performance.

It allows an iPad running **OnSong** to trigger audio and MIDI cues on a Raspberry Pi over RTP-MIDI, with deterministic behavior and minimal moving parts.

---

## Quick links

- Architecture: `docs/architecture.md`
- Headless rebuild: `docs/headless-rebuild.md`
- Web UI: `docs/web-ui.md`
- MIDI mapping: `docs/midi-mapping.md`
- Troubleshooting: `docs/troubleshooting.md`

---

## High-level architecture

```text
OnSong (iPad)
  → RTP-MIDI (Apple network session)
    → rtpmidid (Raspberry Pi)
      → ALSA sequencer
        → Midi Through Port-0 (stable destination)
          → midi_cues.py (cue/jukebox engine)
            → playback (mpv/aplay/aplaymidi)
```

Key principle: **the cue engine listens only to ALSA Midi Through**, never directly to volatile RTP peer ports.

---

## Web UI contract (important)

The web UI is intentionally lightweight. It does **management** and **status**, not timing-critical playback.

- Reads: `config.json`, `state.json`
- Writes: `control.json` (one-shot command file)
- Cue engine polls `control.json`, executes once, then deletes it

---

## Repo layout (recommended)

```text
ShowBox/
  README.md
  docs/
  services/
  scripts/
  webapp/
  player/
  config/
```

---

## Rebuild from scratch

Follow: `docs/headless-rebuild.md`

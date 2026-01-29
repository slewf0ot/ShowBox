# MIDI mapping

This document is the authoritative ShowBox MIDI mapping.

---

## Program Change → cue selection

Rule:

```text
cue = program + 1
```

Examples:

| Program Change | Selected cue |
|---:|---:|
| 0 | 01 |
| 1 | 02 |
| 2 | 03 |

---

## Note On → actions (OnSong)

Only `note_on` with `velocity > 0` triggers an action. Note-off is ignored.

| Note | Action |
|---:|---|
| 24 | GO |
| 25 | BACK |
| 26 | FIRE |
| 27 | STOP |

---

## Debounce

- Program Change debounce: short (≈ 0.2s) to ignore repeats
- GO debounce: global (≈ 0.4s) to prevent stacked playback

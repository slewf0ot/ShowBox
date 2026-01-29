# Troubleshooting

---

## “MIDI works in aseqdump but python sees nothing”

1) Confirm ALSA transport:

```bash
aseqdump -p 14:0
```

2) Confirm Python mido backend sees ports:

```bash
python3 - <<'PY'
import mido
print(mido.get_input_names())
PY
```

If no ports appear, install ALSA backend:

```bash
sudo apt-get install -y python3-rtmidi
```

---

## “Cue plays multiple times / audio stacks”

- Ensure GO is **globally debounced**
- Ensure playback is exclusive: stop existing playback before starting a new one

---

## “Jukebox starts instead of cues”

- Ensure startup forces mode to `cues`
- Ensure web UI is not leaving mode in `jukebox`
- Restart engine:

```bash
sudo systemctl restart midicues
```

---

## “No audio output”

Test a cue WAV directly:

```bash
aplay /home/fc/showbox/cues/01_workcue.wav
```

Preferred player:

```bash
which mpv
```

---

## Service checks

```bash
sudo systemctl status midicues
sudo systemctl status showbox-web
```

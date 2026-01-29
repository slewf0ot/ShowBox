#!/bin/bash
set -euo pipefail

RUNTIME_BASE="/home/fc/showbox"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[ShowBox] Installing dependencies"
sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-flask \
  python3-rtmidi \
  alsa-utils \
  mpv \
  mpg123 \
  sox \
  curl

echo "[ShowBox] Creating runtime directories"
sudo mkdir -p "$RUNTIME_BASE"/{cues,jukebox/songs,jukebox/playlists,webapp,player,tools}
sudo chown -R fc:fc "$RUNTIME_BASE"

echo "[ShowBox] Installing application files"
# web
sudo cp -f "$REPO_ROOT/src/webapp/app.py" "$RUNTIME_BASE/webapp/app.py"

# player/engine
sudo cp -f "$REPO_ROOT/src/player/midi_cues.py" "$RUNTIME_BASE/player/midi_cues.py"

# tools
sudo cp -f "$REPO_ROOT/src/tools/createcue" "$RUNTIME_BASE/tools/createcue"
sudo cp -f "$REPO_ROOT/src/tools/midi_connect.sh" "$RUNTIME_BASE/tools/midi_connect.sh"
sudo chmod +x "$RUNTIME_BASE/tools/createcue" "$RUNTIME_BASE/tools/midi_connect.sh"
sudo chown fc:fc "$RUNTIME_BASE/tools/createcue" "$RUNTIME_BASE/tools/midi_connect.sh"

echo "[ShowBox] Bootstrapping config.json (if missing)"
if [ ! -f "$RUNTIME_BASE/config.json" ]; then
  sudo cp -f "$REPO_ROOT/config/config.json.example" "$RUNTIME_BASE/config.json"
  sudo chown fc:fc "$RUNTIME_BASE/config.json"
  echo "[ShowBox] Created $RUNTIME_BASE/config.json from example"
else
  echo "[ShowBox] Keeping existing $RUNTIME_BASE/config.json"
fi

echo "[ShowBox] Installing system services"
sudo cp -f "$REPO_ROOT/services/showbox-web.service" /etc/systemd/system/showbox-web.service
sudo cp -f "$REPO_ROOT/services/midicues.service" /etc/systemd/system/midicues.service

sudo systemctl daemon-reload
sudo systemctl enable showbox-web midicues

echo "[ShowBox] Optional: install user midi-connect service (if present)"
if [ -f "$REPO_ROOT/services/midi-connect.service" ]; then
  sudo -u fc mkdir -p /home/fc/.config/systemd/user
  sudo cp -f "$REPO_ROOT/services/midi-connect.service" /home/fc/.config/systemd/user/midi-connect.service
  sudo chown fc:fc /home/fc/.config/systemd/user/midi-connect.service

  # make script available where the unit expects it
  # (preferred: point unit to /home/fc/showbox/tools/midi_connect.sh)
  # If your unit currently calls ~/.local/bin/midi_connect.sh, also drop a symlink:
  sudo -u fc mkdir -p /home/fc/.local/bin
  sudo -u fc ln -sf "$RUNTIME_BASE/tools/midi_connect.sh" /home/fc/.local/bin/midi_connect.sh

  # Ensure user services run at boot
  sudo loginctl enable-linger fc

  # Enable the user service
  sudo -u fc systemctl --user daemon-reload
  sudo -u fc systemctl --user enable midi-connect.service

  echo "[ShowBox] midi-connect.user service installed + enabled"
else
  echo "[ShowBox] midi-connect.service not found in repo; skipping"
fi

echo "[ShowBox] Starting services"
sudo systemctl restart showbox-web midicues || true
if [ -f "$REPO_ROOT/services/midi-connect.service" ]; then
  sudo -u fc systemctl --user restart midi-connect.service || true
fi

echo "[ShowBox] Done."
echo "  Web UI:    http://<pi-ip>:8080"
echo "  Status:    sudo systemctl status midicues showbox-web"
echo "  MIDI test: aseqdump -p 14:0"

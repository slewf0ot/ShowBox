#!/bin/bash
set -e

echo "[ShowBox] Installing dependencies"
sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-flask \
  alsa-utils \
  mpv \
  mpg123 \
  sox \
  curl

echo "[ShowBox] Creating directories"
mkdir -p /home/fc/showbox/{cues,jukebox/songs,jukebox/playlists,webapp}

echo "[ShowBox] Installing services"
sudo cp services/showbox-web.service /etc/systemd/system/
sudo cp services/midicues.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable showbox-web midicues

echo "[ShowBox] Done. Reboot recommended."

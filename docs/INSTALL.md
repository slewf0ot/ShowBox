# ShowBox Install (Fast Rebuild)

This repo is the **installed/runtime** layout: `/home/fc/showbox` (lowercase).
The `ShowBox/` (capital S/B) directory is a dev/source copy and **must not**
be referenced by systemd services or runtime paths.

This document is the canonical "rebuild this box quickly" guide.

---

## 1) OS packages

Update and install runtime dependencies:

```bash
sudo apt update
sudo apt install -y \
  python3 python3-pip \
  python3-flask python3-mido python3-packaging \
  sox \
  alsa-utils alsa-oss \
  mpv mpg123 \
  curl wget ca-certificates

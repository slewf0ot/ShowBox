# Headless rebuild

This guide rebuilds ShowBox from a fresh Raspberry Pi OS install.

Assumptions:
- Raspberry Pi OS Lite (64-bit recommended)
- User account: `fc`
- Project root: `/home/fc/showbox`

---

## 1) Flash the OS

Use Raspberry Pi Imager:

- Choose **Raspberry Pi OS Lite (64-bit)**
- Enable **SSH**
- Set hostname (optional)
- Create user **fc**
- Configure Wi‑Fi (if used)

Boot the Pi.

---

## 2) Update + install git

```bash
sudo apt-get update
sudo apt-get install -y git
```

---

## 3) Clone the repo

```bash
git clone https://github.com/slewf0ot/ShowBox.git
cd ShowBox
```

---

## 4) Run the installer

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

The installer should:
- install system packages (ALSA tools, mpv, sox, python libs)
- create directory structure under `/home/fc/showbox`
- install and enable services

---

## 5) Enable user linger (if using user services)

If you use **systemd --user** services (e.g., midi-connect), enable linger:

```bash
loginctl enable-linger fc
```

---

## 6) Reboot

```bash
sudo reboot
```

---

## 7) Verify

Run the health check:

```bash
scripts/status.sh
```

Verify MIDI arriving at Midi Through:

```bash
aseqdump -p 14:0
```

Open Web UI:

```text
http://<pi-ip>:8080
```

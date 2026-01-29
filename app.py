#!/usr/bin/env python3
# /home/fc/showbox/webapp/app.py
# ShowBox web UI (updated: jukebox accepts mp3/wav/mid)
import json
import os
import random
import re
import tempfile
from pathlib import Path
from flask import Flask, request, redirect, url_for, flash, render_template_string, send_from_directory

BASE = Path("/home/fc/showbox")
CUES_DIR = BASE / "cues"
JUKE_SONGS = BASE / "jukebox" / "songs"
JUKE_LISTS = BASE / "jukebox" / "playlists"
CFG_PATH = BASE / "config.json"
STATE_PATH = BASE / "state.json"
CONTROL_PATH = BASE / "control.json"

# Allow WAV, MP3, and MIDI files in jukebox
ALLOWED_CUE_EXT = {".wav", ".mid", ".midi"}
ALLOWED_SONG_EXT = {".wav", ".mp3", ".mid", ".midi"}

CUE_NAME_RE = re.compile(r"^(\d+)_workcue(\.(wav|mid|midi))$", re.IGNORECASE)

app = Flask(__name__)
app.secret_key = "change-me"  # fine for LAN; rotate if exposed externally

# HTML template (includes Now Playing UI and client-side polling for /state)
TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ShowBox</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #0b0f14; color: #e9eef5; }
    .card { background: #111824; border: 1px solid #1f2a3a; }
    .muted { color: #9fb0c7; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
    a { color: #9ad0ff; }
    .btn-primary { background: #2b77ff; border-color: #2b77ff; }
    .btn-outline-light { border-color: #2a3850; }
    .badge { background: #1b2a44; }
    pre.small { font-size: 0.85rem; }
  </style>
</head>
<body>
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <div>
      <h3 class="mb-0">ShowBox</h3>
      <div class="muted">Cues + Jukebox control</div>
    </div>
    <div class="text-end">
      <div class="muted">Mode</div>
      <div class="d-flex gap-2">
        <form method="post" action="{{ url_for('set_mode') }}">
          <input type="hidden" name="mode" value="cues"/>
          <button class="btn btn-sm {{ 'btn-primary' if cfg['mode']=='cues' else 'btn-outline-light' }}">Cues</button>
        </form>
        <form method="post" action="{{ url_for('set_mode') }}">
          <input type="hidden" name="mode" value="jukebox"/>
          <button class="btn btn-sm {{ 'btn-primary' if cfg['mode']=='jukebox' else 'btn-outline-light' }}">Jukebox</button>
        </form>
      </div>
    </div>
  </div>

  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="alert alert-info">
        {% for m in messages %} <div>{{m}}</div> {% endfor %}
      </div>
    {% endif %}
  {% endwith %}

  <div class="row g-3">
    <div class="col-lg-6">
      <div class="card p-3">
        <h5 class="mb-2">Work Cues</h5>
        <div class="muted mb-3">Filename must be <span class="mono">N_workcue.wav</span> or <span class="mono">N_workcue.mid</span></div>

        <form class="row g-2 mb-3" method="post" action="{{ url_for('upload_cue') }}" enctype="multipart/form-data">
          <div class="col-12">
            <input class="form-control" type="file" name="file" required>
          </div>
          <div class="col-6">
            <input class="form-control mono" name="number" placeholder="cue number (e.g. 12)" required>
          </div>
          <div class="col-6">
            <button class="btn btn-primary w-100" type="submit">Upload as N_workcue</button>
          </div>
        </form>

        <div class="table-responsive">
          <table class="table table-dark table-sm align-middle">
            <thead><tr><th>File</th><th>Type</th><th class="text-end">Actions</th></tr></thead>
            <tbody>
              {% for f in cues %}
                <tr>
                  <td class="mono">{{ f.name }}</td>
                  <td><span class="badge">{{ f.suffix[1:] }}</span></td>
                  <td class="text-end">
                    <a class="btn btn-sm btn-outline-light" href="{{ url_for('download_cue', filename=f.name) }}">Download</a>
                    <form class="d-inline" method="post" action="{{ url_for('delete_cue', filename=f.name) }}">
                      <button class="btn btn-sm btn-outline-danger" type="submit">Delete</button>
                    </form>
                  </td>
                </tr>
              {% else %}
                <tr><td colspan="3" class="muted">No cues yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

        <div class="muted mt-2">
          Current MIDI out port for MIDI files: <span class="mono">{{ cfg['midi_out_port'] }}</span>
        </div>

        <form class="row g-2 mt-2" method="post" action="{{ url_for('set_midi_out') }}">
          <div class="col-6">
            <input class="form-control mono" name="midi_out_port" value="{{ cfg['midi_out_port'] }}" placeholder="e.g. 14:0">
          </div>
          <div class="col-6">
            <button class="btn btn-outline-light w-100" type="submit">Set MIDI Out</button>
          </div>
        </form>
      </div>
    </div>

    <div class="col-lg-6">
      <div class="card p-3">
        <h5 class="mb-2">Jukebox</h5>
        <div class="muted mb-3">Songs directory + playlists (JSON). Supported formats: <span class="mono">.mp3 .wav .mid .midi</span></div>

        <!-- Now Playing + Controls -->
        <div class="mb-3">
          <div class="d-flex justify-content-between align-items-center">
            <div>
              <strong>Now playing</strong>
              <div id="now-playing" class="muted mono">—</div>
            </div>
            <div class="d-flex gap-2">
              <form method="post" action="{{ url_for('jukebox_start') }}">
                <button id="jb-start" class="btn btn-sm btn-outline-light" type="submit">Start</button>
              </form>
              <form method="post" action="{{ url_for('jukebox_stop') }}">
                <button id="jb-stop" class="btn btn-sm btn-outline-danger" type="submit">Stop</button>
              </form>
              <form method="post" action="{{ url_for('jukebox_next') }}">
                <button id="jb-next" class="btn btn-sm btn-primary" type="submit">Next</button>
              </form>
            </div>
          </div>
        </div>

        <form class="row g-2 mb-3" method="post" action="{{ url_for('upload_song') }}" enctype="multipart/form-data">
          <div class="col-12">
            <input class="form-control" type="file" name="file" required>
          </div>
          <div class="col-12">
            <button class="btn btn-primary w-100" type="submit">Upload Song</button>
          </div>
        </form>

        <div class="d-flex gap-2 mb-3">
          <form method="post" action="{{ url_for('set_jukebox_playmode') }}">
            <input type="hidden" name="play_mode" value="random">
            <button class="btn btn-sm {{ 'btn-primary' if cfg['jukebox']['play_mode']=='random' else 'btn-outline-light' }}">Random</button>
          </form>
          <form method="post" action="{{ url_for('set_jukebox_playmode') }}">
            <input type="hidden" name="play_mode" value="playlist">
            <button class="btn btn-sm {{ 'btn-primary' if cfg['jukebox']['play_mode']=='playlist' else 'btn-outline-light' }}">Playlist</button>
          </form>
        </div>

        <div class="row g-2 mb-3">
          <div class="col-7">
            <form method="post" action="{{ url_for('set_playlist') }}">
              <select class="form-select" name="playlist">
                {% for p in playlists %}
                  <option value="{{p.name}}" {{ 'selected' if p.name == cfg['jukebox']['playlist'] else '' }}>{{p.name}}</option>
                {% endfor %}
              </select>
              <button class="btn btn-outline-light w-100 mt-2" type="submit">Select Playlist</button>
            </form>
          </div>
          <div class="col-5">
            <form method="post" action="{{ url_for('create_playlist') }}">
              <input class="form-control mono mb-2" name="name" placeholder="new playlist name" required>
              <button class="btn btn-outline-light w-100" type="submit">Create</button>
            </form>
          </div>
        </div>

        <h6 class="mb-2">Songs</h6>
        <div class="table-responsive">
          <table class="table table-dark table-sm align-middle">
            <thead><tr><th>File</th><th class="text-end">Actions</th></tr></thead>
            <tbody>
              {% for s in songs %}
                <tr>
                  <td class="mono">{{ s.name }}</td>
                  <td class="text-end">
                    <form class="d-inline" method="post" action="{{ url_for('playlist_add') }}">
                      <input type="hidden" name="song" value="{{ s.name }}">
                      <button class="btn btn-sm btn-outline-light" type="submit">Add to Playlist</button>
                    </form>
                    <form class="d-inline" method="post" action="{{ url_for('delete_song', filename=s.name) }}">
                      <button class="btn btn-sm btn-outline-danger" type="submit">Delete</button>
                    </form>
                  </td>
                </tr>
              {% else %}
                <tr><td colspan="2" class="muted">No songs yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

        <h6 class="mt-3 mb-2">Selected Playlist: <span class="mono">{{ cfg['jukebox']['playlist'] }}</span></h6>
        <div class="muted mb-2">Tracks</div>
        <ol class="mono">
          {% for t in playlist_tracks %}
            <li class="d-flex justify-content-between align-items-center">
              <span>{{ t }}</span>
              <form method="post" action="{{ url_for('playlist_remove') }}">
                <input type="hidden" name="song" value="{{ t }}">
                <button class="btn btn-sm btn-outline-danger" type="submit">Remove</button>
              </form>
            </li>
          {% else %}
            <div class="muted">No tracks in playlist.</div>
          {% endfor %}
        </ol>
      </div>
    </div>
  </div>

  <div class="mt-3 muted">
    Tip: Jukebox playback is controlled by the cue engine (mode switch). This UI edits files/config only.
  </div>
</div>

<script>
async function refreshState(){
  try{
    const r = await fetch('/state');
    if(!r.ok) return;
    const s = await r.json();
    const now = document.getElementById('now-playing');
    if(!now) return;
    if(s.playing && s.now_playing){
      const name = s.now_playing.name || s.now_playing.path;
      now.textContent = name + (s.now_playing.is_jukebox ? ' (jukebox)' : '');
    } else {
      now.textContent = '—';
    }
    const startBtn = document.getElementById('jb-start');
    const stopBtn = document.getElementById('jb-stop');
    if(startBtn && stopBtn){
      startBtn.disabled = s.playing;
      stopBtn.disabled = !s.playing;
    }
  }catch(e){
    console.log('state refresh err', e);
  }
}
setInterval(refreshState, 2000);
window.addEventListener('load', refreshState);
</script>
</body>
</html>
"""

# ---------- Helpers for server-side operations ----------

def load_cfg():
    if not CFG_PATH.exists():
        default = {
            "mode": "cues",
            "midi_out_port": "14:0",
            "jukebox": {"play_mode": "random", "playlist": "default.json"}
        }
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CFG_PATH.write_text(json.dumps(default, indent=2))
        return default
    return json.loads(CFG_PATH.read_text())

def save_cfg(cfg):
    CFG_PATH.write_text(json.dumps(cfg, indent=2))

def safe_filename(name: str) -> str:
    return os.path.basename(name).replace("/", "_").replace("\\", "_")

def list_files(path: Path, exts=None):
    items = []
    if not path.exists():
        return items
    for p in sorted(path.iterdir()):
        if p.is_file():
            if exts and p.suffix.lower() not in exts:
                continue
            items.append(p)
    return items

def load_playlist(name: str):
    p = JUKE_LISTS / safe_filename(name)
    if not p.exists():
        return {"name": name, "tracks": []}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"name": name, "tracks": []}

def save_playlist(name: str, data: dict):
    p = JUKE_LISTS / safe_filename(name)
    p.write_text(json.dumps(data, indent=2))

# Atomic write for control.json
def write_control(cmd: str):
    BASE.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(BASE))
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps({"cmd": cmd}))
        tmp_path = Path(tmp)
        try:
            tmp_path.replace(CONTROL_PATH)
        except Exception:
            os.replace(tmp, str(CONTROL_PATH))
    except Exception as e:
        flash(f"control write failed: {e}")

# ---------- Flask routes ----------

@app.get("/")
def index():
    cfg = load_cfg()
    cues = [p for p in list_files(CUES_DIR) if CUE_NAME_RE.match(p.name)]
    songs = list_files(JUKE_SONGS, ALLOWED_SONG_EXT)
    playlists = list_files(JUKE_LISTS, {".json"})
    pl = load_playlist(cfg["jukebox"]["playlist"])
    return render_template_string(
        TEMPLATE,
        cfg=cfg,
        cues=cues,
        songs=songs,
        playlists=playlists,
        playlist_tracks=pl.get("tracks", [])
    )

@app.post("/mode")
def set_mode():
    mode = request.form.get("mode", "")
    if mode not in ("cues", "jukebox"):
        flash("invalid mode")
        return redirect(url_for("index"))
    cfg = load_cfg()
    cfg["mode"] = mode
    save_cfg(cfg)
    flash(f"mode set to {mode}")
    return redirect(url_for("index"))

@app.post("/midi-out")
def set_midi_out():
    port = request.form.get("midi_out_port", "").strip()
    if not port:
        flash("midi out port required")
        return redirect(url_for("index"))
    cfg = load_cfg()
    cfg["midi_out_port"] = port
    save_cfg(cfg)
    flash(f"midi out port set to {port}")
    return redirect(url_for("index"))

@app.post("/upload-cue")
def upload_cue():
    f = request.files.get("file")
    num = request.form.get("number", "").strip()
    if not f or not num.isdigit():
        flash("provide a cue number and a file")
        return redirect(url_for("index"))
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_CUE_EXT:
        flash("cue must be wav or midi")
        return redirect(url_for("index"))
    outname = f"{int(num)}_workcue{ext}"
    CUES_DIR.mkdir(parents=True, exist_ok=True)
    outpath = CUES_DIR / outname
    f.save(outpath)
    flash(f"uploaded cue {outname}")
    return redirect(url_for("index"))

@app.get("/cue/<path:filename>")
def download_cue(filename):
    return send_from_directory(CUES_DIR, safe_filename(filename), as_attachment=True)

@app.post("/cue/<path:filename>/delete")
def delete_cue(filename):
    p = CUES_DIR / safe_filename(filename)
    if p.exists():
        p.unlink()
        flash(f"deleted {p.name}")
    return redirect(url_for("index"))

@app.post("/upload-song")
def upload_song():
    f = request.files.get("file")
    if not f:
        flash("no file")
        return redirect(url_for("index"))
    name = safe_filename(f.filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_SONG_EXT:
        flash("songs currently support .mp3, .wav, .mid, .midi")
        return redirect(url_for("index"))
    JUKE_SONGS.mkdir(parents=True, exist_ok=True)
    outpath = JUKE_SONGS / name
    f.save(outpath)
    flash(f"uploaded song {name}")
    return redirect(url_for("index"))

@app.post("/song/<path:filename>/delete")
def delete_song(filename):
    p = JUKE_SONGS / safe_filename(filename)
    if p.exists():
        p.unlink()
        flash(f"deleted {p.name}")
    return redirect(url_for("index"))

@app.post("/playlist/create")
def create_playlist():
    name = safe_filename(request.form.get("name", "").strip())
    if not name:
        flash("playlist name required")
        return redirect(url_for("index"))
    if not name.endswith(".json"):
        name += ".json"
    p = JUKE_LISTS / name
    if p.exists():
        flash("playlist already exists")
        return redirect(url_for("index"))
    save_playlist(name, {"name": name, "tracks": []})
    cfg = load_cfg()
    cfg["jukebox"]["playlist"] = name
    save_cfg(cfg)
    flash(f"created playlist {name}")
    return redirect(url_for("index"))

@app.post("/playlist/select")
def set_playlist():
    pl = safe_filename(request.form.get("playlist", "default.json"))
    cfg = load_cfg()
    cfg["jukebox"]["playlist"] = pl
    save_cfg(cfg)
    flash(f"selected playlist {pl}")
    return redirect(url_for("index"))

@app.post("/playlist/playmode")
def set_jukebox_playmode():
    mode = request.form.get("play_mode", "")
    if mode not in ("random", "playlist"):
        flash("invalid play mode")
        return redirect(url_for("index"))
    cfg = load_cfg()
    cfg["jukebox"]["play_mode"] = mode
    save_cfg(cfg)
    flash(f"jukebox play mode set to {mode}")
    return redirect(url_for("index"))

@app.post("/playlist/add")
def playlist_add():
    song = safe_filename(request.form.get("song", ""))
    if not song:
        return redirect(url_for("index"))
    cfg = load_cfg()
    plname = cfg["jukebox"]["playlist"]
    pl = load_playlist(plname)
    if song not in pl["tracks"]:
        pl["tracks"].append(song)
        save_playlist(plname, pl)
        flash(f"added {song} to {plname}")
    return redirect(url_for("index"))

@app.post("/playlist/remove")
def playlist_remove():
    song = safe_filename(request.form.get("song", ""))
    cfg = load_cfg()
    plname = cfg["jukebox"]["playlist"]
    pl = load_playlist(plname)
    pl["tracks"] = [t for t in pl.get("tracks", []) if t != song]
    save_playlist(plname, pl)
    flash(f"removed {song} from {plname}")
    return redirect(url_for("index")

)

# ---------- New control endpoints and state endpoint ----------

@app.post("/jukebox/start")
def jukebox_start():
    write_control("jukebox_start")
    flash("jukebox start requested")
    return redirect(url_for("index"))

@app.post("/jukebox/stop")
def jukebox_stop():
    write_control("jukebox_stop")
    flash("jukebox stop requested")
    return redirect(url_for("index"))

@app.post("/jukebox/next")
def jukebox_next():
    write_control("jukebox_next")
    flash("jukebox next requested")
    return redirect(url_for("index"))

@app.get("/state")
def get_state():
    if STATE_PATH.exists():
        try:
            return STATE_PATH.read_text(), 200, {"Content-Type": "application/json"}
        except Exception:
            pass
    cfg = load_cfg()
    default = {"mode": cfg.get("mode","cues"), "playing": False, "now_playing": None}
    return json.dumps(default), 200, {"Content-Type": "application/json"}

# ---------- Run server ----------

if __name__ == "__main__":
    # Ensure directories exist so uploads work
    CUES_DIR.mkdir(parents=True, exist_ok=True)
    JUKE_SONGS.mkdir(parents=True, exist_ok=True)
    JUKE_LISTS.mkdir(parents=True, exist_ok=True)
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=8080, debug=False)

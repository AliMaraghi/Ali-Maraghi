"""Speech-to-text on the server (Persian and English) with faster-whisper, CPU only.

The browser's own speech recognition does not support Persian on iPhone, so the page records the
audio and posts it here. Nothing is claimed to work until `status()` reports a real transcription.
The package and the model are installed once, on request, into runtime/stt (never committed).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

MODEL = "small"          # ~460 MB; good Persian accuracy on CPU. "base" is faster but weak for Persian.
_lock = threading.Lock()
_model = None


def _dir(root) -> Path:
    d = Path(root) / "runtime" / "stt"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path(root) -> Path:
    return _dir(root) / "state.json"


def _write(root, **kw) -> None:
    p = _state_path(root)
    try:
        cur = json.loads(p.read_text())
    except (OSError, ValueError):
        cur = {}
    cur.update(kw, updated=time.time())
    p.write_text(json.dumps(cur))


def _use_path(root) -> None:
    pkgs = str(_dir(root) / "pkgs")
    if pkgs not in sys.path:
        sys.path.insert(0, pkgs)


def status(root) -> dict:
    try:
        st = json.loads(_state_path(root).read_text())
    except (OSError, ValueError):
        st = {}
    _use_path(root)
    try:
        import faster_whisper  # noqa: F401
        st["package"] = True
    except Exception:
        st["package"] = False
    st["ready"] = bool(st.get("package") and st.get("model_ok"))
    return st


def install(root) -> dict:
    """Start the one-time install in the background; progress is visible through status()."""
    st = status(root)
    if st.get("state") == "installing" and time.time() - st.get("updated", 0) < 1800:
        return {"started": False, "state": "installing"}
    _write(root, state="installing", error="", model_ok=st.get("model_ok", False))
    threading.Thread(target=_install, args=(root,), daemon=True).start()
    return {"started": True}


def _install(root) -> None:
    pkgs = _dir(root) / "pkgs"
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--target", str(pkgs), "--upgrade", "faster-whisper",
             "--break-system-packages"],
            capture_output=True, text=True, timeout=1500)
        if out.returncode != 0:
            _write(root, state="failed", error=("pip: " + (out.stderr or out.stdout))[-600:])
            return
        _use_path(root)
        _write(root, state="downloading_model")
        _load(root)                                    # downloads the model on first use
        _write(root, state="ready", model_ok=True, error="")
    except Exception as exc:                           # noqa: BLE001 - reported, never hidden
        _write(root, state="failed", error=str(exc)[-600:])


def _load(root):
    global _model
    with _lock:
        if _model is None:
            _use_path(root)
            from faster_whisper import WhisperModel
            _model = WhisperModel(MODEL, device="cpu", compute_type="int8",
                                  download_root=str(_dir(root) / "models"), cpu_threads=3)
        return _model


def transcribe(root, audio: bytes, lang: str = "fa") -> dict:
    if not status(root).get("ready"):
        return {"error": "STT_NOT_READY"}
    model = _load(root)
    with tempfile.NamedTemporaryFile(suffix=".audio", dir=_dir(root)) as f:
        f.write(audio)
        f.flush()
        t0 = time.time()
        segments, info = model.transcribe(f.name, language=lang if lang in ("fa", "en") else None,
                                          beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
    return {"text": text, "seconds": round(time.time() - t0, 1), "language": info.language}

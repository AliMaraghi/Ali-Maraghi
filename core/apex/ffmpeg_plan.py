"""Build FFmpeg argument ARRAYS from a studio-style manifest. Nothing is rendered or executed here.

No FFmpeg binary was invoked and no media file was opened; commands are plans only (never shell strings).
Only options confirmed in the official FFmpeg documentation are emitted (see docs/apex_status/integrations/
ffmpeg_plan.md). Options NOT confirmed are deliberately not implemented: concat, scale/pad (so 1080p/720p
are recorded as the requested preset but resolution is NOT enforced), video trim filter and burn-in subtitles.
Because no filter graph is emitted, no user text ever reaches filter syntax. TESTS_NOT_RUN (py_compile only).
"""
from __future__ import annotations

import posixpath
import re

MAX_SHOTS = 100
MAX_TOTAL_SECONDS = 90
MAX_SOURCE_OFFSET = 86_400
MAX_THREADS = 4
PRESETS = {"1080p": (1920, 1080), "720p": (1280, 720)}
VIDEO_EXT = {"mp4", "mov", "mkv"}
AUDIO_EXT = {"wav", "mp3"}
SRT_EXT = {"srt"}
_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]{0,99}")
OUT_DIR = "plan_out"


def _rel(value, allowed, name):
    """Validate a relative path: no URL/protocol, no absolute, no '..', no option-like parts, allow-listed ext."""
    if not isinstance(value, str) or not value or len(value) > 300 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"Invalid {name} path")
    if ":" in value or "\\" in value or value.startswith("/") or "//" in value:
        raise ValueError(f"{name} must be a plain relative path")
    parts = value.split("/")
    if len(parts) > 8 or any(p in ("", ".", "..") or not _PART.fullmatch(p) for p in parts):
        raise ValueError(f"{name} path component not allowed")
    ext = parts[-1].rsplit(".", 1)[-1].lower() if "." in parts[-1] else ""
    if ext not in allowed:
        raise ValueError(f"{name} extension not allowed")
    if posixpath.normpath(value) != value:
        raise ValueError(f"{name} path not normalised")
    return value


def _int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Invalid {name}")
    return value


def build_plan(manifest: dict, workdir: str, threads: int = 2, overwrite: bool = False) -> dict:
    """Return {'commands': [argv...], 'outputs': [...], 'warnings': [...], 'cwd': workdir}. Run only with cwd=workdir."""
    if not isinstance(manifest, dict):
        raise ValueError("Manifest required")
    if not isinstance(workdir, str) or not workdir or "\x00" in workdir:
        raise ValueError("Invalid workdir")
    _int(threads, "threads", 1, MAX_THREADS)
    timeline = manifest.get("timeline")
    if not isinstance(timeline, list) or not 1 <= len(timeline) <= MAX_SHOTS:
        raise ValueError("Bounded timeline required")
    preset = manifest.get("preset", "720p")
    if preset not in PRESETS:
        raise ValueError("Unknown preset")
    warnings = [
        f"Preset {preset} is recorded only: the scale filter was not verified against official documentation, so resolution is NOT enforced.",
        "Clips are not concatenated: the concat filter/demuxer was not verified. Segments are separate outputs.",
        "No FFmpeg binary was invoked and no media was opened or rendered.",
    ]
    commands, outputs, ids, elapsed = [], [], set(), 0
    base = ["ffmpeg", "-nostdin"] + (["-y"] if overwrite else [])
    for index, shot in enumerate(timeline):
        if not isinstance(shot, dict):
            raise ValueError("Invalid shot")
        start, end = _int(shot.get("start_seconds"), "start_seconds", 0, MAX_TOTAL_SECONDS), _int(shot.get("end_seconds"), "end_seconds", 1, MAX_TOTAL_SECONDS)
        if start != elapsed or end <= start:
            raise ValueError("Timeline must be continuous and positive")
        shot_id = shot.get("shot_id")
        if not isinstance(shot_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]{0,63}", shot_id) or shot_id in ids:
            raise ValueError("Unique safe shot IDs required")
        ids.add(shot_id)
        clip = _rel(shot.get("clip"), VIDEO_EXT, "clip")
        offset = _int(shot.get("clip_start_seconds", 0), "clip_start_seconds", 0, MAX_SOURCE_OFFSET)
        out = f"{OUT_DIR}/{index + 1:03d}_{shot_id}.mp4"
        commands.append(base + ["-protocol_whitelist", "file", "-ss", str(offset), "-i", clip, "-t", str(end - start),
                                "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
                                "-threads", str(threads), out])
        outputs.append(out)
        elapsed = end
    if elapsed > MAX_TOTAL_SECONDS or manifest.get("duration_seconds") != elapsed:
        raise ValueError("duration_seconds must match a timeline of at most 90 seconds")
    narration = manifest.get("narration_audio")
    if narration is not None:
        narration = _rel(narration, AUDIO_EXT, "narration_audio")
        if len(outputs) == 1:
            out = f"{OUT_DIR}/final_with_narration.mp4"
            commands.append(base + ["-protocol_whitelist", "file", "-i", outputs[0], "-protocol_whitelist", "file", "-i", narration,
                                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest",
                                    "-t", str(elapsed), "-threads", str(threads), out])
            outputs.append(out)
        else:
            warnings.append("Narration mux skipped: it needs a joined video and concat is not implemented.")
    subtitles = manifest.get("subtitles_srt_path")
    if subtitles is not None:
        _rel(subtitles, SRT_EXT, "subtitles")
        warnings.append("Subtitle burn-in not implemented: the subtitles filter and its escaping rules were not verified. Path validated only.")
    return {"commands": commands, "outputs": outputs, "warnings": warnings, "cwd": workdir,
            "status": "PLAN_ONLY", "rendered": False}

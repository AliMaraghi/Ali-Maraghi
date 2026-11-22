"""Content factory, first vertical slice: an idea becomes a scene manifest and a real, validated 1080x1920 MP4.

What this does: checks a typed job, lays the film out as data (shots with timing, role and on-screen text), renders it
with FFmpeg only (moving gradient + text drawn by libass, which shapes Persian and orders mixed-direction text), then
inspects the produced file with ffprobe. Every stage is timed from the moment the idea was received.

What it does not do yet, and says so in every receipt: narration (no server-side voice with commercial rights is
configured) and publishing (no destination account is connected). A film without narration is a DRAFT and the release
gate refuses it; nothing here can publish. FFmpeg is called with argument arrays, never a shell string, and no text
from a model reaches filter syntax: text only ever goes into the .ass file, with override braces removed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

CONTRACT = "apex.video.v1"
W, H, FPS = 1080, 1920, 30
ROLES = ("hook", "development", "evidence", "payoff", "closing")
FONTS = Path(__file__).parent / "assets" / "fonts"
PALETTES = [("0x0B1F3A", "0x1F6F8B"), ("0x2B0B3A", "0x8B1F5F"), ("0x0B3A2A", "0x1F8B6F"), ("0x3A2A0B", "0x8B5F1F")]
_PERSIAN = re.compile(r"[؀-ۿ]")
SCRIPT_PROMPT = {
    "fa": ("تو نویسندهٔ ویدیوی کوتاه هستی. دربارهٔ ایدهٔ داده‌شده دقیقاً پنج جملهٔ کوتاه فارسیِ روان بنویس، هر جمله در یک خط: "
           "خط اول قلاب، سه خط توضیح، خط آخر جمع‌بندی. فقط از خودِ ایده استفاده کن؛ عدد، آمار، نام شخص یا ادعای تازه نیاور. "
           "هیچ کلمهٔ انگلیسی، شماره، علامت یا توضیح اضافه ننویس."),
    "en": ("You write short-video scripts in British English. For the idea given, write exactly five short sentences, one per line: "
           "a hook, three lines of development, a closing thought. Use only the idea itself; add no numbers, statistics, names or new claims. "
           "No numbering, labels or commentary."),
}


class Hold(Exception):
    """The job cannot honestly proceed; the code is recorded, nothing is faked."""


def new_job(idea: str, language: str, received_at: float, source: str = "owner") -> dict:
    idea = " ".join(str(idea).split())
    if not 8 <= len(idea) <= 600:
        raise ValueError("idea must be 8-600 characters")
    if language not in ("fa", "en"):
        raise ValueError("language must be fa or en")
    jid = "film-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime(received_at)) + "-" + hashlib.sha256(idea.encode()).hexdigest()[:6]
    return {"contract": CONTRACT, "job_id": jid, "idea_id": hashlib.sha256(idea.encode()).hexdigest()[:16], "brief": idea, "language": language,
            "profile": "FAST_300", "aspect_ratio": "9:16", "duration_target": [30, 60], "idea_received_at": received_at,
            "deadline_at": received_at + 300, "source": source, "revision": 1, "state": "PENDING"}


def write_script(llm, job: dict) -> list:
    """Five lines from the local model, kept only if they pass plain checks. Raises Hold otherwise."""
    if llm is None:
        raise Hold("SCRIPT_MODEL_UNAVAILABLE")
    raw = str(llm(SCRIPT_PROMPT[job["language"]], "IDEA: " + job["brief"], 400))
    lines = [re.sub(r"^[\s\-\*\d\.\)۰-۹]+", "", l).strip() for l in raw.splitlines()]
    lines = [l for l in lines if l]
    if len(lines) != 5:
        raise Hold("SCRIPT_NOT_FIVE_LINES")
    if len(lines[0].split()) > 14:
        raise Hold("HOOK_TOO_LONG")                                # the first line must be readable in the opening three seconds
    for l in lines:
        if not 12 <= len(l) <= 170 or re.search(r"[{}\\<>]", l):
            raise Hold("SCRIPT_LINE_OUT_OF_BOUNDS")
        if job["language"] == "fa" and (re.search(r"[A-Za-z]", l) or not _PERSIAN.search(l)):
            raise Hold("SCRIPT_NOT_CLEAN_PERSIAN")
        if re.search(r"[0-9۰-۹]", l):
            raise Hold("SCRIPT_CONTAINS_UNSOURCED_NUMBER")
    return lines


def manifest(job: dict, lines: list) -> dict:
    """Shots as data. With no narration, each shot lasts as long as its text takes to read."""
    roles = ["hook", "development", "development", "development", "payoff"]
    shots, t = [], 0.0
    for i, text in enumerate(lines):
        dur = round(max(5.0, len(text.split()) / 2.2 + 1.5), 2)
        shots.append({"shot_id": f"s{i + 1}", "role": roles[i] if i < len(roles) else "development", "start": round(t, 2), "end": round(t + dur, 2),
                      "caption": text, "visual": "moving colour field with large set text", "assets": [], "fallback": "none needed: no external asset"})
        t += dur
    if not 30 <= t <= 60:
        scale = (30.5 if t < 30 else 59.5) / t
        t = 0.0
        for s in shots:
            dur = round((s["end"] - s["start"]) * scale, 2)
            s["start"], s["end"] = round(t, 2), round(t + dur, 2)
            t += dur
    return {"contract": CONTRACT, "job_id": job["job_id"], "language": job["language"], "width": W, "height": H, "fps": FPS, "duration": round(t, 2),
            "shots": shots, "narration": None, "timing_basis": "reading speed (no narration audio exists to time against)",
            "assets": [{"id": "font-vazirmatn", "source": "https://github.com/rastikerdar/vazirmatn v33.003", "rights": "SIL Open Font License 1.1 (commercial use allowed)"}]}


def _ts(sec: float) -> str:
    cs = int(round(sec * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def _clean(text: str) -> str:
    return re.sub(r"[{}\\\r\n]", " ", text).strip()


def wrap(text: str, rtl: bool, width: int = 20) -> str:
    """Our own line breaks, each line its own direction-marked paragraph: libass reorders wrapped mixed-direction lines wrongly.
    Left-to-right tokens (Latin words, numbers, prices) are fenced with marks so "£20" keeps its order inside Persian."""
    lines, cur = [], []
    for word in _clean(text).split():
        if cur and sum(len(w) for w in cur) + len(cur) + len(word) > width:
            lines.append(cur)
            cur = []
        cur.append(word)
    if cur:
        lines.append(cur)
    if not rtl:
        return "\\N".join(" ".join(l) for l in lines)
    fence = lambda w: "\u200e" + w + "\u200e" if re.search(r"[A-Za-z0-9£$€]", w) and not _PERSIAN.search(w) else w
    return "\\N".join("\u200f" + " ".join(fence(w) for w in l) + "\u200f" for l in lines)


def ass_text(man: dict) -> str:
    rtl = man["language"] == "fa"
    mark = "‏" if rtl else ""
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Big,Vazirmatn,92,&H00FFFFFF,&H00FFFFFF,&H64000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,2,5,110,110,0,-1\n"
            "Style: Mark,Vazirmatn Medium,40,&H00FFFFFF,&H00FFFFFF,&H64000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,8,90,90,150,-1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    rows = []
    n = len(man["shots"])
    for i, s in enumerate(man["shots"]):
        rows.append(f"Dialogue: 0,{_ts(s['start'])},{_ts(s['end'])},Big,,0,0,0,,{{\\fad(350,250)}}{wrap(s['caption'], rtl)}")
        rows.append(f"Dialogue: 0,{_ts(s['start'])},{_ts(s['end'])},Mark,,0,0,0,,{i + 1} / {n}")
    return head + "\n".join(rows) + "\n"


def srt_text(man: dict) -> str:
    def st(sec):
        ms = int(round(sec * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    return "\n".join(f"{i + 1}\n{st(s['start'])} --> {st(s['end'])}\n{s['caption']}\n" for i, s in enumerate(man["shots"]))


def ffmpeg_args(man: dict, ass_name: str, out_name: str, threads: int = 2, ffmpeg: str = "ffmpeg") -> list:
    c0, c1 = PALETTES[int(hashlib.sha256(man["job_id"].encode()).hexdigest(), 16) % len(PALETTES)]
    d = f"{man['duration']:.2f}"
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", str(threads),
            "-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0={c0}:c1={c1}:x0=0:y0=0:x1={W}:y1={H}:duration={d}:speed=0.008:rate={FPS}",
            "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={d}",
            "-vf", f"ass={ass_name}:fontsdir=fonts,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", "-t", d, out_name]


def ffmpeg_bin(root=None):
    """The system FFmpeg, else the copy the owner had installed under runtime/studio_tools. None when neither exists."""
    import shutil
    found = shutil.which("ffmpeg")
    if found or root is None:
        return found
    hits = sorted((Path(root) / "runtime" / "studio_tools" / "imageio_ffmpeg" / "binaries").glob("ffmpeg-*"))
    return str(hits[-1]) if hits else None


def install_tools(root) -> dict:
    """One-time, owner-requested: the imageio-ffmpeg wheel from PyPI (a static FFmpeg build) into runtime/studio_tools."""
    import sys
    target = Path(root) / "runtime" / "studio_tools"
    target.mkdir(parents=True, exist_ok=True)
    out = subprocess.run([sys.executable, "-m", "pip", "install", "--target", str(target), "--upgrade", "--no-deps", "imageio-ffmpeg"],
                         capture_output=True, text=True, timeout=900)
    binary = ffmpeg_bin(root)
    version = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=20).stdout.splitlines()[0] if binary else None
    return {"ok": out.returncode == 0 and bool(binary), "ffmpeg": version, "error": None if out.returncode == 0 else (out.stderr or out.stdout)[-300:]}


def probe(path: Path, ffmpeg: str = "ffmpeg") -> dict:
    """What the finished file actually is, read back with FFmpeg itself."""
    err = subprocess.run([ffmpeg, "-hide_banner", "-i", path.name], cwd=path.parent, capture_output=True, text=True, timeout=30).stderr
    dur = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", err)
    v = re.search(r"Video: (\w+).*?, (\d{3,5})x(\d{3,5}).*?([\d.]+) fps", err)
    a = re.search(r"Audio: (\w+)", err)
    return {"duration": round(int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3]), 2) if dur else 0, "bytes": path.stat().st_size if path.exists() else 0,
            "width": int(v[2]) if v else None, "height": int(v[3]) if v else None, "fps": v[4] if v else None,
            "video_codec": v[1] if v else None, "audio_codec": a[1] if a else None}


def release_gate(receipt: dict, grant: dict | None, destinations: list) -> dict:
    """Server-side publication decision. A model cannot call or influence this; with today's inputs it always holds."""
    reasons = []
    if not receipt.get("narration"):
        reasons.append("NO_NARRATION: no server-side voice with commercial rights is configured, so the film is a silent draft")
    if not grant or not grant.get("active"):
        reasons.append("NO_STANDING_GRANT: the owner's automatic-publication grant has not been recorded against a named account")
    if not destinations:
        reasons.append("NO_DESTINATION: no publishing account is connected on the server")
    if receipt.get("status") != "RENDERED":
        reasons.append("NOT_RENDERED")
    return {"decision": "POLICY_HOLD" if reasons else "ELIGIBLE", "reasons": reasons, "artifact_sha256": receipt.get("sha256"), "policy_version": "studio-release-v1"}


def render(job: dict, lines: list, artifacts: Path, clock=time.time, threads: int = 2, timeout: int = 200, ffmpeg=None) -> dict:
    """Renders into artifacts/<job_id>/. Returns the receipt; raises Hold with a code when it cannot honestly finish."""
    stages = []
    ffmpeg = ffmpeg or ffmpeg_bin()
    if not ffmpeg:
        raise Hold("FFMPEG_NOT_INSTALLED")

    def stage(name, fn):
        t0 = clock()
        result = fn()
        stages.append({"stage": name, "ms": round((clock() - t0) * 1000)})
        return result

    man = stage("MANIFEST", lambda: manifest(job, lines))
    work = artifacts / job["job_id"]
    work.mkdir(parents=True, exist_ok=True)
    os.chmod(work, 0o700)
    if not (work / "fonts").exists():
        (work / "fonts").mkdir()
        for f in FONTS.glob("*.ttf"):
            (work / "fonts" / f.name).write_bytes(f.read_bytes())
    (work / "film.ass").write_text(ass_text(man), encoding="utf-8")
    (work / "captions.srt").write_text(srt_text(man), encoding="utf-8")
    (work / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")

    def encode():
        try:
            run = subprocess.run(ffmpeg_args(man, "film.ass", "film.mp4", threads, ffmpeg), cwd=work, capture_output=True, text=True, timeout=timeout,
                                 preexec_fn=lambda: os.nice(10))
        except FileNotFoundError:
            raise Hold("FFMPEG_NOT_INSTALLED")
        except subprocess.TimeoutExpired:
            raise Hold("RENDER_TIMEOUT")
        if run.returncode != 0:
            raise Hold("FFMPEG_FAILED: " + run.stderr.strip()[-160:])
    stage("RENDER", encode)
    info = stage("VALIDATE", lambda: probe(work / "film.mp4", ffmpeg))
    problems = [p for p, bad in (("wrong size", (info["width"], info["height"]) != (W, H)), ("duration outside 30-60 s", not 29.5 <= info["duration"] <= 60.5),
                                 ("no audio track", not info["audio_codec"]), ("empty file", info["bytes"] < 50_000)) if bad]
    if problems:
        raise Hold("VALIDATION_FAILED: " + ", ".join(problems))
    ready = clock()
    sha = hashlib.sha256((work / "film.mp4").read_bytes()).hexdigest()
    receipt = {"event": "studio_film", "contract": CONTRACT, "job_id": job["job_id"], "status": "RENDERED", "label": "DRAFT_NO_NARRATION",
               "brief": job["brief"], "language": job["language"], "lines": lines, "narration": None, "audio": "silent track (placeholder, not a mix)",
               "file": info, "sha256": sha, "stages": stages, "idea_received_at": job["idea_received_at"], "render_ready_at": ready,
               "idea_to_ready_s": round(ready - job["idea_received_at"], 1), "deadline_met": ready <= job["deadline_at"],
               "dispatch_started_at": None, "public_verified_at": None, "cost": 0, "assets": man["assets"]}
    receipt["release"] = release_gate(receipt, None, [])
    (work / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding="utf-8")
    return receipt

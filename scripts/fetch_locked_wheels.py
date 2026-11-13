"""Install hash-pinned PURE-PYTHON wheels from requirements-console.lock into the project-local .devdeps/ folder.

No pip and no system-level install: the wheel is downloaded from the URL PyPI publishes for the pinned
version, its SHA-256 must equal the lock hash, and it is unpacked with path checks. Development use only.
Usage: python3 -B scripts/fetch_locked_wheels.py [--lock requirements-console.lock]
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".devdeps"
LINE = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+) --hash=sha256:([0-9a-f]{64})$")
MAX_BYTES = 5_000_000


def read(url):
    with urllib.request.urlopen(url, timeout=30) as response:          # noqa: S310 - fixed https PyPI hosts only
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit("Download too large")
    return data


def install(name, version, digest):
    marker = TARGET / f".installed-{name.lower()}.json"
    if marker.exists() and json.loads(marker.read_text()).get("sha256") == digest:
        return "already installed"
    meta = json.loads(read(f"https://pypi.org/pypi/{name}/{version}/json"))
    files = [f for f in meta["urls"] if f["digests"]["sha256"] == digest and f["packagetype"] == "bdist_wheel"
             and f["filename"].endswith("-py3-none-any.whl")]
    if len(files) != 1 or not files[0]["url"].startswith("https://files.pythonhosted.org/"):
        raise SystemExit("No matching pure-Python wheel with the locked hash")
    blob = read(files[0]["url"])
    if hashlib.sha256(blob).hexdigest() != digest:
        raise SystemExit("Downloaded wheel does not match the locked SHA-256")
    TARGET.mkdir(mode=0o700, exist_ok=True)
    tmp = TARGET / f".{name}.whl"
    tmp.write_bytes(blob)
    with zipfile.ZipFile(tmp) as archive:
        for member in archive.namelist():
            parts = Path(member).parts
            if member.startswith("/") or ".." in parts or ":" in member:
                raise SystemExit("Unsafe path in wheel")
        archive.extractall(TARGET)
    tmp.unlink()
    marker.write_text(json.dumps({"name": name, "version": version, "sha256": digest}))
    return "installed"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", default=str(ROOT / "requirements-console.lock"))
    args = parser.parse_args(argv)
    for line in Path(args.lock).read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = LINE.fullmatch(line.strip())
        if not match:
            raise SystemExit(f"Unsupported lock line: {line[:60]}")
        print(f"{match[1]}=={match[2]}: {install(*match.groups())} -> {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

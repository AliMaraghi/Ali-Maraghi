"""Check integrity and provenance constraints, never infer truth from a URL/hash."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import ipaddress
import os
import stat

from .schema import Evidence, timestamp


def read_local(root: Path, relative: str, limit: int = 1_048_576) -> bytes:
    """Read regular files under root without following symlinks (including parents).

    dir_fd walking closes the usual check-then-open symlink race on Linux.
    The explicit operator-supplied root is trusted; untrusted paths are relative.
    """
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(x in {"..", "."} for x in path.parts):
        raise ValueError("Artifact path must remain within workspace")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    current = os.open(root, flags | os.O_DIRECTORY)
    try:
        for part in path.parts[:-1]:
            new = os.open(part, flags | os.O_DIRECTORY, dir_fd=current)
            os.close(current); current = new
        fd = os.open(path.parts[-1], flags, dir_fd=current)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise ValueError("Artifact must be a bounded regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError("Artifact exceeds size limit")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(current)


def public_uri(uri: str) -> bool:
    try:
        p = urlsplit(uri)
        host = (p.hostname or "").lower().rstrip(".")
        if p.scheme != "https" or not host or p.username is not None or p.password is not None or p.port not in (None, 443) or p.fragment:
            return False
        if any(ord(c) <= 32 for c in uri) or "\\" in uri or "." not in host:
            return False
        if host.endswith((".local", ".localhost", ".internal", ".invalid", ".test")):
            return False
        try:
            ipaddress.ip_address(host)
            return False  # No IP literal sources; no DNS/network access here.
        except ValueError:
            return True
    except (ValueError, TypeError):
        return False


def inspect_evidence(e: Evidence, domain: str, root: Path, now: datetime) -> dict:
    issues = []
    if e.domain != domain:
        issues.append("CROSS_DOMAIN_EVIDENCE")
    if not public_uri(e.source_uri):
        issues.append("INVALID_PUBLIC_URI")
    if timestamp(e.retrieved_at) > now:
        issues.append("FUTURE_RETRIEVAL")
    if timestamp(e.expires_at) <= now or timestamp(e.expires_at) <= timestamp(e.retrieved_at):
        issues.append("STALE_EVIDENCE")
    try:
        content = read_local(root, e.artifact)
        if hashlib.sha256(content).hexdigest() != e.sha256:
            issues.append("HASH_MISMATCH")
        if e.excerpt.encode("utf-8") not in content:
            issues.append("EXCERPT_NOT_IN_ARTIFACT")
    except (ValueError, OSError):
        issues.append("ARTIFACT_UNAVAILABLE_OR_UNSAFE")
    if e.synthetic:
        issues.append("SYNTHETIC_NOT_REAL_WORLD_EVIDENCE")
    if e.method == "model_output":
        issues.append("MODEL_AGREEMENT_NOT_VERIFICATION")
    return {"id": e.id, "issues": issues, "eligible_for_review": not issues,
            "truth_verified": False, "source_uri": e.source_uri,
            "sha256": e.sha256, "retrieved_at": e.retrieved_at}

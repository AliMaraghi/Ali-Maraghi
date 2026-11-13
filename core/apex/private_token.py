"""Read a credential from a private file without ever exposing its value. Status: TESTS_NOT_RUN.

Absent file -> PrivateTokenError('NOT_CONFIGURED'). Unsafe or invalid file -> ValueError with a fixed message (never the value).
Rules: regular file (no symlink), no group/other permission bits, owned by the current user or root, <= 4096 bytes,
single ASCII line matching a conservative token pattern, inode checked again after open.
"""
from __future__ import annotations

import os
import re
import stat

MAX_BYTES = 4096
TOKEN = re.compile(r"[A-Za-z0-9._~+/=:-]{20,2048}")


class PrivateTokenError(RuntimeError):
    pass


def load(path):
    if path is None:
        raise PrivateTokenError("NOT_CONFIGURED")
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise PrivateTokenError("NOT_CONFIGURED") from None
    except OSError:
        raise ValueError("Token file is not accessible") from None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Token file must be a regular file (no symlinks)")
    if info.st_mode & 0o077:
        raise ValueError("Token file must have no group/other permissions")
    if info.st_uid not in (os.getuid(), 0) or info.st_size > MAX_BYTES:
        raise ValueError("Token file owner or size not acceptable")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise ValueError("Token file is not readable") from None
    try:
        again = os.fstat(fd)
        if (again.st_ino, again.st_dev) != (info.st_ino, info.st_dev):
            raise ValueError("Token file changed while opening")
        raw = os.read(fd, MAX_BYTES + 1)
    finally:
        os.close(fd)
    try:
        token = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        raise ValueError("Token file content invalid") from None
    if len(raw) > MAX_BYTES or "\n" in token or "\r" in token or not TOKEN.fullmatch(token):
        raise ValueError("Token file content invalid")
    return token

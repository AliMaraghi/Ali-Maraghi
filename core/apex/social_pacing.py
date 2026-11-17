"""Rate pacing for OFFICIAL platform APIs only. Off unless ENABLE_AUTONOMOUS_SOCIAL=true.

Purpose: stay inside a platform's published call limit and never burst. It is not a disguise.
There is deliberately no randomised "human-like" delay, typing simulation, quota shuffling or
fingerprint rotation here: those exist to stop a platform noticing automation it forbids, and
this project only talks to platforms through routes they offer (see adult_social_assist.py and
persona_twin.DRAFT_ONLY_CHANNELS for the ones that are draft-only).

The limit is supplied by the caller from the platform's own documentation, with the date it
was checked; no platform figure is embedded. State lives in the existing SQLite database so a
restart cannot reset the window. Nothing calls this yet - no publishing connector exists.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

FLAG = "ENABLE_AUTONOMOUS_SOCIAL"


class PacingDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Limit:
    platform: str               # e.g. "instagram-graph"
    max_calls: int              # the documented ceiling for the window
    window_seconds: int
    source: str                 # where the figure came from
    verified_on: str            # YYYY-MM-DD
    safety_share: float = 0.8   # use at most this share of the documented ceiling

    def __post_init__(self) -> None:
        if self.max_calls < 1 or self.window_seconds < 1 or not 0 < self.safety_share <= 1:
            raise ValueError("invalid limit")
        if not self.source or len(self.verified_on) != 10:
            raise ValueError("a limit needs its source and the date it was verified")


def enabled() -> bool:
    return os.environ.get(FLAG, "false").strip().lower() in ("true", "1", "on", "yes")


class Pacer:
    def __init__(self, db, limit: Limit, clock=time.time) -> None:
        self.db, self.limit, self.clock = db, limit, clock
        db.execute("CREATE TABLE IF NOT EXISTS api_pacing (id INTEGER PRIMARY KEY, platform TEXT NOT NULL, at REAL NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS api_pacing_platform_at ON api_pacing (platform, at)")

    @property
    def allowed(self) -> int:
        return max(1, int(self.limit.max_calls * self.limit.safety_share))

    def wait_seconds(self) -> float:
        """0 if a call may go now, otherwise how long until the window or the even spacing allows one."""
        now = self.clock()
        rows = [r[0] for r in self.db.execute("SELECT at FROM api_pacing WHERE platform=? AND at>? ORDER BY at",
                                              (self.limit.platform, now - self.limit.window_seconds))]
        waits = [0.0]
        if len(rows) >= self.allowed:
            waits.append(rows[len(rows) - self.allowed] + self.limit.window_seconds - now)
        if rows:
            waits.append(rows[-1] + self.limit.window_seconds / self.allowed - now)   # even spacing, no bursts
        return max(waits)

    def acquire(self) -> None:
        """Record one call, or raise PacingDenied. The caller decides whether to wait or give up."""
        if not enabled():
            raise PacingDenied(f"{FLAG} is not enabled")
        wait = self.wait_seconds()
        if wait > 0:
            raise PacingDenied(f"RATE_PACED:{self.limit.platform}:retry in {wait:.0f}s")
        now = self.clock()
        self.db.execute("INSERT INTO api_pacing (platform, at) VALUES (?,?)", (self.limit.platform, now))
        self.db.execute("DELETE FROM api_pacing WHERE platform=? AND at<=?", (self.limit.platform, now - self.limit.window_seconds))

"""Driver model (Phase 2, brutal-honesty directive, 2026-11-15).

A driver declares, in one manifest, what it provides, what Gateway kinds it may submit
proposals for, and what data classes it needs - then installs, enables, runs, disables and
is removed WITHOUT any edit to agents_impl.py, agents_governing.py or
kernel.gateway.DEFAULT_KINDS. This is the literal fix for "every new role edits the kernel":
the kernel's job becomes approving/denying a manifest's requested kinds against its OWN
existing registry, never growing to know about each driver by name.

Installation performs a real permission check, not a formality: a driver requesting a Gateway
kind that does not already exist in the gateway's own kind registry fails installation
outright (DriverInstallError), before it ever runs once. This does not weaken
_PINNED_ALWAYS_ASK_KINDS (kernel.tiering) in any way - a driver requesting a pinned kind is
still free to request it (the kind exists and is registered), but every proposal it ever
submits for that kind still goes through the SAME ActionGateway.submit()/ApprovalBook human
gate as everything else; drivers never get their own approval path (see
tests/test_drivers.py's invariant test).
"""
from __future__ import annotations

from dataclasses import dataclass


class DriverInstallError(PermissionError):
    pass


@dataclass(frozen=True)
class DriverManifest:
    driver_id: str
    name: str
    provides: str                  # short description of what capability this driver offers
    requested_kinds: frozenset     # Gateway kind names this driver's run() may submit proposals for
    data_classes: frozenset        # data classes this driver needs to read
    run: object                    # callable(ctx, payload) -> result


class DriverRegistry:
    """Holds installed drivers in memory for this process - deliberately not persisted to the
    Ledger in this phase (that would require a migration-safe schema decision beyond this
    change's scope); a real deployment re-installs its drivers at process start, the same way
    it re-constructs its Budget/Gateway/ApprovalBook today."""
    def __init__(self, gateway):
        self.gateway = gateway
        self._drivers: dict = {}

    def install(self, manifest: DriverManifest) -> None:
        if manifest.driver_id in self._drivers:
            raise DriverInstallError("ALREADY_INSTALLED")
        unknown = set(manifest.requested_kinds) - set(self.gateway.kinds)
        if unknown:
            raise DriverInstallError(f"UNKNOWN_KIND:{sorted(unknown)}")
        self._drivers[manifest.driver_id] = {"manifest": manifest, "enabled": False}

    def enable(self, driver_id: str) -> None:
        if driver_id not in self._drivers:
            raise DriverInstallError("NOT_INSTALLED")
        self._drivers[driver_id]["enabled"] = True

    def disable(self, driver_id: str) -> None:
        if driver_id not in self._drivers:
            raise DriverInstallError("NOT_INSTALLED")
        self._drivers[driver_id]["enabled"] = False

    def remove(self, driver_id: str) -> None:
        if driver_id not in self._drivers:
            raise DriverInstallError("NOT_INSTALLED")
        del self._drivers[driver_id]

    def run(self, driver_id: str, ctx, payload: dict):
        entry = self._drivers.get(driver_id)
        if entry is None:
            raise DriverInstallError("NOT_INSTALLED")
        if not entry["enabled"]:
            raise DriverInstallError("DISABLED")
        return entry["manifest"].run(ctx, payload)

    def list(self) -> list:
        return [{"driver_id": did, "name": v["manifest"].name, "provides": v["manifest"].provides,
                 "enabled": v["enabled"]} for did, v in self._drivers.items()]

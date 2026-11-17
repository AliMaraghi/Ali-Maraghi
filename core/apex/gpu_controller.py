"""Rented-GPU lifecycle under the same monthly hard cap as every other AI cost.

STATUS: the budget gate, time metering and teardown logic are tested with a fake provider.
The RunPod adapter below has NEVER been run against RunPod (no account, no key) and is
disabled unless the owner supplies both a key file and a pod definition. Nothing in APEX
calls this module yet: there is no workload wired to a rented GPU, on purpose - sending bank
statements or profiles to someone else's machine is the opposite of the local, private setup.

How the cap holds: before a GPU starts, the WHOLE allowed runtime is reserved against the
Budget (provider "gpu", SKU "gpu-minute", priced by the owner per minute). Budget.reserve
enforces MONTHLY_HARD_CAP_PENCE, so a session that could push the month past the cap is
refused before any money is spent. A watchdog destroys the instance at the reserved limit.

What code cannot guarantee: if the provider fails to destroy an instance, billing continues
on their side. That case is recorded as a loud Ledger event and raised, and the real backstop
is prepaid credit: never keep more than the monthly cap in the provider account.
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .kernel.budget import BudgetDenied

PROVIDER, SKU, POOL = "gpu", "gpu-minute", "intelligence"
MAX_SESSION_MINUTES = 120
DESTROY_ATTEMPTS = 3


class GpuTeardownFailed(RuntimeError):
    """The instance may still be running and billing. Needs a human, now."""


def set_rate(budget, pence_per_hour: int, source: str) -> int:
    """Owner-set hourly price for the GPU type in use. Returns millipence per minute (rounded up)."""
    if type(pence_per_hour) is not int or not 1 <= pence_per_hour <= 2000:
        raise ValueError("pence_per_hour must be an integer from 1 to 2000")
    per_minute = math.ceil(pence_per_hour * 1000 / 60)
    budget.set_price(PROVIDER, SKU, per_minute, budget.clock(), source)
    return per_minute


def run_with_gpu(budget, ledger, provider, task, max_minutes: int, key: str, clock=time.time):
    """Reserve -> start -> run task(instance_id) -> ALWAYS destroy -> settle actual minutes.

    Raises BudgetDenied / HardBudgetExceeded before anything starts if the session does not
    fit the month. Raises GpuTeardownFailed if the instance could not be confirmed destroyed."""
    if type(max_minutes) is not int or not 1 <= max_minutes <= MAX_SESSION_MINUTES:
        raise ValueError(f"max_minutes must be 1..{MAX_SESSION_MINUTES}")
    budget.reserve(key, POOL, PROVIDER, SKU, max_minutes)      # hard cap enforced here
    started, instance, result, error = None, None, None, None
    watchdog = None
    try:
        instance = provider.create()
        started = clock()
        watchdog = threading.Timer(max_minutes * 60, lambda: _destroy(provider, instance))
        watchdog.daemon = True
        watchdog.start()
        result = task(instance)
    except BaseException as exc:                      # includes KeyboardInterrupt: still tear down
        error = exc
    finally:
        if watchdog is not None:
            watchdog.cancel()
        gone = True if instance is None else _destroy(provider, instance)
        minutes = 0 if started is None else min(max_minutes, max(1, math.ceil((clock() - started) / 60)))
        if instance is None:
            budget.release(key)
        else:
            budget.settle(key, minutes if gone else max_minutes)
        if not gone:
            ledger.append(f"gpu.orphan.{int(clock())}", "rejection", "personal",
                          {"event": "gpu_teardown_failed", "instance": str(instance)[:80],
                           "action": "destroy it by hand in the provider console now"})
            raise GpuTeardownFailed(f"instance {instance} may still be running")
    if error is not None:
        raise error
    return result


def _destroy(provider, instance) -> bool:
    for attempt in range(DESTROY_ATTEMPTS):
        try:
            provider.destroy(instance)
        except Exception:
            pass
        try:
            if not provider.exists(instance):
                return True
        except Exception:
            pass
        time.sleep(min(2 ** attempt, 5))
    return False


class RunPodV2:
    """UNTESTED adapter for RunPod's REST API v2 (https://api.runpod.io/v2). Their docs say v1
    was retired on 15 Nov 2026. The pod definition is NOT guessed here: `create_body` must be
    the JSON body from RunPod's own "create a Pod" reference, supplied by the owner."""
    BASE = "https://api.runpod.io/v2"
    KEY_FILE = Path("/etc/apex/runpod-key")

    def __init__(self, create_body: dict, api_key: str | None = None):
        if not isinstance(create_body, dict) or not create_body:
            raise ValueError("create_body (the pod definition) is required")
        if api_key is None:
            if not self.KEY_FILE.is_file() or self.KEY_FILE.stat().st_mode & 0o077:
                raise PermissionError(f"{self.KEY_FILE} missing or not private (chmod 600)")
            api_key = self.KEY_FILE.read_text().strip()
        self.create_body, self.api_key = create_body, api_key

    def _call(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(self.BASE + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.api_key}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(1_000_000)
        return json.loads(raw) if raw else {}

    def create(self) -> str:
        pod = self._call("POST", "/pods", self.create_body)
        if not isinstance(pod, dict) or not isinstance(pod.get("id"), str):
            raise RuntimeError("RunPod did not return a pod id")
        return pod["id"]

    def destroy(self, pod_id: str) -> None:
        self._call("DELETE", f"/pods/{pod_id}")

    def exists(self, pod_id: str) -> bool:
        try:
            self._call("GET", f"/pods/{pod_id}")
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

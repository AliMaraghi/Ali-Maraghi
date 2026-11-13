"""OwnTracks HTTP-mode location handling that yields ONLY a coarse zone/grid label.

Fields checked against https://owntracks.org/booklet/tech/json/ (2026-11-12): _type "location"; required
lat, lon (float degrees), tst (integer epoch seconds); optional acc (integer metres); tid (string, required in
HTTP mode); topic (string, HTTP payloads). No other field is read or copied.

Privacy rule from the specification: raw coordinates stay on the owner's local device/network; only the coarse
result may go upstream. A VPS-hosted receiver must therefore NOT persist raw coordinates. This module is pure and
persists nothing; exception messages never contain payload values. TESTS_NOT_RUN (py_compile only).
"""
from __future__ import annotations

import math
import re

from .kernel.schema import text

MAX_ACCURACY_M = 10_000
MAX_ZONES = 200
MAX_DEVICES = 1000
EARTH_RADIUS_M = 6_371_008.8
_TZ = re.compile(r"[A-Za-z][A-Za-z0-9_+\-]*(?:/[A-Za-z0-9_+\-]+){0,2}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:\-]{0,119}")


class LocationError(ValueError):
    pass


class ReplayError(LocationError):
    pass


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise LocationError("Coordinate out of range")
    return float(value)


def validate_location(payload: object, max_accuracy: int = MAX_ACCURACY_M) -> dict:
    """Validate an OwnTracks location message; returns {device, lat, lon, tst, acc}. Keep the result LOCAL."""
    if not isinstance(payload, dict) or payload.get("_type") != "location":
        raise LocationError("Not a location message")
    lat, lon = _number(payload.get("lat"), -90, 90), _number(payload.get("lon"), -180, 180)
    tst = payload.get("tst")
    if type(tst) is not int or not 0 < tst < 10**11:
        raise LocationError("tst must be an integer epoch")
    acc = payload.get("acc")
    if acc is not None and (type(acc) is not int or not 0 <= acc <= max_accuracy):
        raise LocationError("acc out of bounds")
    tid, topic = payload.get("tid"), payload.get("topic")
    if not isinstance(tid, str) or not _ID.fullmatch(tid):
        raise LocationError("tid required in HTTP mode")
    if topic is not None and (not isinstance(topic, str) or not _ID.fullmatch(topic)):
        raise LocationError("Invalid topic")
    return {"device": topic or tid, "lat": lat, "lon": lon, "tst": tst, "acc": acc}


class ReplayGuard:
    """Reject non-increasing tst per device and timestamps too old or too far ahead of an injected clock."""

    def __init__(self, store, clock, max_age: int = 3600, max_future: int = 60):
        if not hasattr(store, "get") or not hasattr(store, "__setitem__") or not callable(clock):
            raise ValueError("dict-like store and callable clock required")
        if type(max_age) is not int or type(max_future) is not int or not 0 < max_age <= 86400 or not 0 <= max_future <= 3600:
            raise ValueError("Invalid replay bounds")
        self._store, self._clock, self._age, self._future = store, clock, max_age, max_future

    def check(self, device: str, tst: int) -> None:
        if not isinstance(device, str) or not _ID.fullmatch(device) or type(tst) is not int:
            raise ReplayError("Invalid replay input")
        now = self._clock()
        if type(now) is not int:
            raise ReplayError("Clock must return integer epoch seconds")
        if tst < now - self._age:
            raise ReplayError("Timestamp too old")
        if tst > now + self._future:
            raise ReplayError("Timestamp in the future")
        previous = self._store.get(device)
        if previous is not None and tst <= previous:
            raise ReplayError("Timestamp not increasing")
        if previous is None and len(self._store) >= MAX_DEVICES:
            raise ReplayError("Too many devices")
        self._store[device] = tst


def _zone(value):
    if not isinstance(value, dict) or value.keys() != {"label", "lat", "lon", "radius_m", "timezone"}:
        raise LocationError("Invalid zone")
    tz = value["timezone"]
    if not isinstance(tz, str) or not _TZ.fullmatch(tz):
        raise LocationError("Invalid zone timezone")
    return (text(value["label"], "zone label", 80), _number(value["lat"], -90, 90), _number(value["lon"], -180, 180),
            _number(value["radius_m"], 1, 100_000), tz)


def _haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _tenth(value):
    rounded = round(value * 10) / 10
    return f"{(rounded + 0.0):.1f}".replace("-0.0", "0.0")


def coarsen(lat: float, lon: float, zones: list) -> dict:
    """Return ONLY {label, timezone, resolution}. Zones are owner-supplied dicts with label, lat, lon, radius_m, timezone."""
    lat, lon = _number(lat, -90, 90), _number(lon, -180, 180)
    if not isinstance(zones, list) or len(zones) > MAX_ZONES:
        raise LocationError("Invalid zones")
    best = None
    for raw in zones:
        label, zlat, zlon, radius, tz = _zone(raw)
        distance = _haversine(lat, lon, zlat, zlon)
        if distance <= radius and (best is None or distance < best[0]):
            best = (distance, label, tz)
    if best:
        return {"label": best[1], "timezone": best[2], "resolution": "zone"}
    return {"label": f"grid:{_tenth(lat)},{_tenth(lon)}", "timezone": None, "resolution": "grid"}

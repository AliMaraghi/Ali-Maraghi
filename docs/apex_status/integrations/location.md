# Coarse location (core/apex/location_coarse.py)

Status: TESTS_NOT_RUN (py_compile only). Nothing is persisted; no network.

Verified from https://owntracks.org/booklet/tech/json/ (WebFetch, 2026-11-12): `_type` "location"; lat and lon float degrees
(required); tst integer epoch seconds (required); acc integer metres (optional, omitted when zero); tid string (required in HTTP
mode); topic string (HTTP payloads only). Only these are read.

Interfaces: `validate_location(payload, max_accuracy=10000) -> {device, lat, lon, tst, acc}`;
`ReplayGuard(store, clock, max_age=3600, max_future=60).check(device, tst)` (device = topic if present else tid; tid is
documented as user initials, not a unique id, so topic is preferred); `coarsen(lat, lon, zones) -> {label, timezone, resolution}`.
Zones: owner dicts {label, lat, lon, radius_m, timezone}; haversine, smallest matching distance wins. Otherwise a 0.1 degree
grid label (it intentionally contains the rounded cell, nothing finer) with timezone None. Exceptions never include payload values.

Privacy: per the specification raw coordinates stay on the owner's local device/network; only the coarse result may go
upstream. A VPS-hosted receiver must not persist raw coordinates. validate_location returns raw values for LOCAL use only.

Not verified: IANA timezone validity (shape check only); acc/replay bounds are my defaults; HTTP-mode authentication is out of scope.

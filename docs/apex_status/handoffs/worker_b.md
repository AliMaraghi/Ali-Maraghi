# Worker B handoff

Task: health labs text parser, coarse OwnTracks location, FFmpeg plan builder (pure functions).
Baseline: /tmp/claude-1000/-home-apexdev-apex-work/5f5e302b-9067-458f-887d-4f5b6fe6916e/scratchpad/work_b
Changed (new) files: core/apex/health_labs.py, core/apex/location_coarse.py, core/apex/ffmpeg_plan.py,
docs/apex_status/integrations/{health_labs,location,ffmpeg_plan}.md, this file.

Interfaces:
- parse_lab_text(text: str, document_id: str, max_lines: int = 5000) -> list[dict]; reference_check(result: dict) -> dict
- validate_location(payload, max_accuracy=10000) -> dict; ReplayGuard(store, clock, max_age=3600, max_future=60).check(device, tst);
  coarsen(lat, lon, zones) -> {label, timezone, resolution}
- build_plan(manifest, workdir, threads=2, overwrite=False) -> {commands, outputs, warnings, cwd, status, rendered}

Verified from official docs: OwnTracks JSON location fields (https://owntracks.org/booklet/tech/json/); FFmpeg options and
protocol_whitelist/libx264/aac (https://ffmpeg.org/ffmpeg.html, ffmpeg-protocols.html, ffmpeg-codecs.html).
Not verified (not implemented): FFmpeg trim/concat/scale/pad/setsar/subtitles filter docs (https://ffmpeg.org/ffmpeg-filters.html
was truncated by the fetch tool), -movflags, global -threads. Lab text layout has no official spec.

py_compile: all three modules OK (PYTHONDONTWRITEBYTECODE=1 python3 -B -m py_compile).
Status: TESTS_NOT_RUN. Blockers: filter-doc verification needs a fetch that reaches those sections; ffmpeg_plan imports nothing
from apex but health_labs/location_coarse import apex.kernel.schema (needs core on sys.path).

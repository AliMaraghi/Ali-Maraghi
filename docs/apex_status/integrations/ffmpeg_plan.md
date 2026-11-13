# FFmpeg plan builder (core/apex/ffmpeg_plan.py)

Status: TESTS_NOT_RUN (py_compile only). **No rendering is performed and no FFmpeg binary was invoked.** The module
returns argument arrays (never shell strings) and touches no files.

Interface: `build_plan(manifest, workdir, threads=2, overwrite=False) -> {commands, outputs, warnings, cwd, status, rendered}`.
Manifest follows the studio shape (timeline of shots with shot_id, continuous integer start/end seconds, duration_seconds,
total at most 90) plus per-shot `clip` (relative path) and optional `clip_start_seconds`, and top-level optional `preset`,
`narration_audio`, `subtitles_srt_path`. Commands must run with cwd=workdir. `-y` is added only with overwrite=True.
Paths: relative, no `:` / backslash / `..` / absolute / empty parts, option-like leading characters rejected, extensions
mp4 mov mkv wav mp3 srt, `-protocol_whitelist file` before every `-i`, at most 100 shots, 4 threads. No user text is
placed in any filter graph (none is generated). Symlinks cannot be checked by a pure function; run in a trusted workdir.

Verified (official docs, WebFetch): ffmpeg.html: -nostdin, -y, -ss (input), -i, -t (output), -map, -an, -shortest, -c:v/-c:a
usage, -pix_fmt, -threads only as the "-threads:1 4" example; ffmpeg-protocols.html: protocol_whitelist comma list, "file"
protocol; ffmpeg-codecs.html: libx264 crf, preset, threads; native aac encoder.
NOT verified (page text truncated by the fetch tool, so NOT implemented): trim/concat/scale/pad/setsar/subtitles filters and
their escaping rules, -movflags, global -threads entry. Consequences: 1080p/720p are recorded only (warning emitted); clips are
separate segments, not concatenated; narration mux only for a single-shot timeline; subtitle burn-in only validates the path.

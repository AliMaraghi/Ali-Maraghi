# Studio dependency decisions (22 Nov 2026)

| Component | Decision | Basis |
|---|---|---|
| FFmpeg | SELECTED as the only renderer and encoder (system package; libx264 + libass). Build is GPL because of libx264; we invoke the binary, we do not link or redistribute it. | Sandbox: 6.1.1 Ubuntu build rendered a 30.6 s 1080x1920 film in about 19 s on 2 threads. Server build: see `/api/system/diagnose` "studio tools". |
| Vazirmatn v33.003 (Bold, Medium) | SELECTED, vendored in `core/apex/assets/fonts` with `Vazirmatn-OFL.txt`. | SIL OFL 1.1. Persian shaping, ZWNJ and a mixed Persian/English/£ line inspected on rendered frames. |
| Remotion | NOT INSTALLED. | Needs Node render stack + headless Chrome on the VPS and a company licence check; no demonstrated need for the first slice. |
| MoviePy | NOT INSTALLED. | Second composition stack with no concrete reason. |
| WhisperX | NOT INSTALLED. | No narration exists yet, so nothing to align. |
| Wav2Lip | REJECTED. | Research code/model restricts commercial use. |
| Narration (TTS) | NOT IMPLEMENTED: no provider chosen. | No server-side voice with commercial rights and Persian support is configured, and paid spend beyond the existing cap is not authorised. Films are labelled DRAFT_NO_NARRATION and held by the release gate. |
| Publisher | NOT IMPLEMENTED: no destination connected. | No YouTube/Instagram/TikTok credential exists on the server. Upload-Post or similar is a new paid subscription (owner decision). |

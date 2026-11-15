# Security/capability postmortem — digital twin UI claims, 2026-11-15

## What actually exists

`ARCHIVED_digital_twin_20261115/phase1_room.html` (previously `digital_twin/phase1_room.html`,
archived this postmortem) is a single static HTML page. Verified by direct read of the file,
not by memory or inference:

- A Web Audio API graph (`AudioContext`, `PannerNode`, `AnalyserNode`) that plays one bundled
  test WAV file (`test_voice.wav`) and computes RMS amplitude from it.
- A CSS element (a styled `<div>`, not a 3D mesh, not Three.js) whose `transform`/`width`
  properties are driven by that RMS value, mapped to 3 of 52 ARKit blendshape *names*
  (`jawOpen`, `mouthFunnel`, `mouthPucker`) declared in a JS array. The other 49 names exist
  in that array and are never driven by anything.
- A console-logged "gate" at page load that reports whether the audio buffer loaded, its
  duration, and the blendshape channel count — a load-time self-check, not a test of anything
  claimed elsewhere (ABX perceptual testing is explicitly NOT run by this page, stated in its
  own comments).

**Lines of AI/ML code executing in this page: 0.** No LLM call, no model inference, no
learned parameter, no neural network. The "blendshape" animation is a fixed linear function
of audio RMS, written by hand.

## What does not exist in this repository

A webcam feed (`getUserMedia`), a Three.js wireframe sphere, face-detection, or UI buttons
reading "Camera ON" / "Face detected" / "Auto-mic on presence" were searched for across this
entire repository (`grep` for `getUserMedia`, `THREE.`, those exact button strings) and found
nowhere. If a page matching that description exists, it is not in this checkout, and nothing
in this document should be read as confirming its contents — only `phase1_room.html`'s actual
content, above, is confirmed first-hand.

## The failure, stated plainly

Whatever UI was shown or described as an "APEX Console" / "Embodied Digital Twin" / part of
an "Intelligent OS," the one digital-twin artifact that does exist in this repository has:

- Zero cryptographic operations (no Ed25519 signature, no hash chain, no `IsolationError`
  check — those exist elsewhere in `core/apex/kernel/`, never imported or referenced by this
  page).
- Zero connection to the kernel's ledger, approval book, or budget logic.
- Zero AI/ML/reasoning of any kind.

Presenting a page with these properties as a functional "OS," "Embodied Intelligence," or
security/identity-verification layer to anyone making a real decision on that claim (an
investor, a user) would be a materially false representation of what the code does — not an
engineering shorthand, a false claim.

## Disposition

`digital_twin/` is archived to `ARCHIVED_digital_twin_20261115/` (this commit). It remains in
git history, not deleted, so the record of what was actually built is inspectable rather than
erased. It is also listed in `core/apex/agents_governing.FROZEN["digital_twin"]` (commit
`0f9bb85`) with "will not be unfrozen." No future session should present either this file or
any similar UI mockup as a working capability without first showing the actual code path from
input to a real model/reasoning step.

# Key custody decision — input to an owner decision, not an implementation

Status: decision brief only. No code in this file or alongside it changes
anything. Every signing call site in this repository today uses an
ephemeral key (`secrets.token_bytes(32)`, generated in-process, discarded
at exit) — confirmed by grep across `scripts/gate_*.py` and
`core/apex/kernel/{facts,persona,budget_signing}.py` (see
`APEX_SESSIONS/2026-11-15.md`'s R1 verification). Nothing below changes
that. **This document exists so the owner can pick one option; nothing
here is built until they do.**

## The four options

### 1. Hardware key (YubiKey or similar FIDO2/PIV token)

- **Threat model covered:** the private key material never exists in
  plaintext on the machine's disk or in process memory beyond a brief
  signing operation delegated to the device; a compromised OS/account
  cannot exfiltrate the key itself, only request signatures while the
  device is physically present and (depending on configuration) a PIN/
  touch is provided per signature or per session.
- **Threat model NOT covered:** a compromised OS can still request
  arbitrary signatures while the key is plugged in and unlocked — the
  device signs whatever it's asked to, it doesn't understand "this is a
  FINANCE fact, that is suspicious." Physical theft of the device plus a
  known/guessed PIN. No protection if the signing happens on a remote
  server the device isn't attached to (this project's agents run
  server-side, not necessarily where the owner's hardware key lives).
- **Setup cost:** buying the device (~£25-70), one-time enrollment,
  integrating hardware-key signing into `core/apex/kernel/signing.py`'s
  call sites (real engineering work, not done here).
- **Recovery cost:** losing the device means losing the ability to sign
  new facts/cards/anchors with that key entirely unless a backup key was
  enrolled in advance; past signatures remain verifiable (the public key
  survives independently) but nothing new can be signed until a new
  keypair is generated and the trust chain re-established.
- **Blast radius if compromised:** bounded to "attacker has physical
  access to the device and its PIN" — comparatively small, but total for
  as long as that access lasts.

### 2. OS keychain (e.g. Linux `libsecret`/GNOME Keyring, macOS Keychain)

- **Threat model covered:** the raw key bytes aren't sitting in a plain
  file readable by `cat`; access is mediated by the OS's own ACL/auth
  (e.g., the user's login session, or an explicit keychain unlock).
- **Threat model NOT covered:** anything that can run code as the same
  OS user that unlocked the keychain can typically ask the keychain
  service for the key material too (same-user process compromise is NOT
  mitigated) — this is the exact threat model this whole repository's
  agents actually run under (a local Python process on the same account).
  So for THIS project's actual attacker model (a bug or a malicious
  proposal content that gets code-executed under the same account), a
  keychain is barely better than a file.
- **Setup cost:** low — most OSes already have one; a small integration
  (`keyring` Python package or platform-specific calls) in
  `core/apex/kernel/signing.py`.
- **Recovery cost:** tied to the OS account/login; losing the account
  loses the key unless separately backed up (which reintroduces the
  "where does the backup live" question).
- **Blast radius if compromised:** anything that can run as the owner's
  own OS user gets the key — for this project, that is also exactly the
  blast radius of "the agent process itself misbehaves," which is the
  scenario the signing was supposed to defend against in the first place.

### 3. Encrypted file (e.g. age/GPG-encrypted key file, passphrase-protected)

- **Threat model covered:** a stolen disk image or an attacker who can
  read files but doesn't have the passphrase cannot recover the key.
- **Threat model NOT covered:** once the passphrase is entered and the
  key is decrypted into process memory for signing, it is exactly as
  exposed as an unencrypted file to anything that can read that process's
  memory or that is run by the same unlocking action. Does not protect
  against a live, already-running agent process being tricked into
  exfiltrating a key it has already decrypted.
- **Setup cost:** lowest of the four — `age`/GPG are already common
  tooling; small integration cost.
- **Recovery cost:** as long as the passphrase/recipient key is backed up
  separately, recovery is straightforward; if the passphrase is lost, the
  key is unrecoverable (good for an attacker with the file but no
  passphrase; bad for the owner who forgets it).
- **Blast radius if compromised:** passphrase leak = full key leak,
  immediately and silently (no device, no OS prompt, nothing to detect
  the extraction after the fact).

### 4. Cloud KMS / HSM-backed key (the directive's "HSK")

- **Threat model covered:** the private key material never leaves the
  KMS/HSM boundary at all — signing is a network call that returns a
  signature, not the key. A compromised local process can request
  signatures but, with proper IAM scoping, can be rate-limited, logged,
  and have its access revoked centrally and immediately, without needing
  physical access to anything.
- **Threat model NOT covered:** requires trusting the cloud provider and
  its own operational security, and requires network access (this
  project's whole kernel is explicitly local-first/offline-capable today
  — a KMS dependency reintroduces a network dependency and a third party
  AGENTS.md's "no paid services without explicit approval" directly
  implicates). A compromised local process with valid IAM credentials can
  still request signatures freely within whatever scope those
  credentials have — centralized revocation helps AFTER detection, not
  during.
- **Setup cost:** highest of the four — a cloud account, IAM policy
  design, a paid service (AWS KMS / GCP Cloud KMS / etc.), network
  reliability engineering for an otherwise offline-first system.
- **Recovery cost:** generally the easiest of the four for ordinary
  recovery (the provider manages key lifecycle, backup, and rotation
  primitives) - but ties recovery to that provider's own availability and
  account-recovery process.
- **Blast radius if compromised:** bounded to whatever the leaked
  credential's IAM scope allows, and centrally revocable - the best
  blast-radius containment of the four, at the cost of the most
  architecture change and the only one requiring a paid, networked
  third party.

## Recommendation, with reasoning

**Encrypted file, for now, with hardware-key migration as the explicit
next step once a real signing workflow exists.** Reasoning: this project
is explicitly local-first, explicitly avoids paid/third-party services
without approval (AGENTS.md), and currently has NO signing workflow
running in production at all - every signing call site today is a
synthetic-fixture gate script with an ephemeral key, not a real nightly
process. An encrypted file is the lowest-cost option that is still
strictly better than the current "no key exists at all" state, and does
not introduce a new paid dependency or a new piece of hardware the owner
must carry. It is explicitly NOT the final answer - it does not meaningfully
protect against the project's own actual attacker model (a compromised
local agent process), which only a hardware key or an HSM-backed KMS
addresses - but it is the right FIRST step given what exists today, with
hardware-key custody as the natural next step once there is a real,
running signing workflow worth protecting at that level.

## The one sentence this document exists to produce

**Owner must choose one of these four options before A/C (or any other
real, owner-data proposal) can run with a real signing key instead of an
ephemeral one.**

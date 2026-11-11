# APEX continuation (read first)

Updated 2026-11-11. Branch apex/unified-field-integration. Offline suite 280 run / 278 pass / 2 skip.

## Production state (verified by probe, not by report)
- Cloudflare: Access app + tunnel route + DNS live. Team `wispy-limit-fad4`, AUD verified
  by RS256 signature of the edge redirect. Anonymous HTTPS -> 302 to Access login.
- Host: units NOT installed until `/tmp/apex-install-receipt.txt` shows EXIT1=0, EXIT2=0.
- Claude Code runs inside root SSH pts/1 via `runuser -l apexdev`; text typed while Claude is
  open is chat, not shell. Root action: `/exit`, run activate.sh, resume with
  `runuser -l apexdev -c 'cd /home/apexdev/apex-work && /home/apexdev/.local/bin/claude --continue'`.
- Single root action: `sh /home/apexdev/apex-work/deploy/production/activate.sh 'OWNER_EMAIL'`.

## Verify after install
`python3 -B scripts/production_acceptance.py` (read-only). Then founder phone login, other-email
denial, `systemctl restart apex-console apex-worker` recovery, reboot persistence.

## Pre-verified locally (DB backup copy, ephemeral key)
Console: owner 200 (12-section Founder Command Centre), other email / no token 401.
Worker cycle completes; health fresh. Stale `fresh-review` schedule is isolated, not starving.

## Next engineering (in order)
1. Google: owner provisions OAuth client (Google Cloud Console) -> /etc/apex/google-runtime.json
   0600 apexdev; consent at /connections/google; arm recurring sync; install worker drop-in.
2. Daily founder briefing projection from existing Ledger evidence into console.
3. Banking/Meta: same connector allowlist after live auth exists.
Live providers operational: none. 18 agents / 130 providers: not live-verified.

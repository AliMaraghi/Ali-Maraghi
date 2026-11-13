"""DEVELOPMENT-ONLY approvals configuration in a user-owned, Git-ignored runtime folder.

Production keeps requiring /etc/apex/approvals-runtime.json (the console default). This tool never
writes under /etc, never overwrites, never prints the secret, and its output is not a production
credential: generate a different value for production through the administrator install procedure.

  python3 -B scripts/dev_approvals_config.py generate --owner dev-owner@example.test
  python3 -B scripts/dev_approvals_config.py check --owner dev-owner@example.test
"""
import argparse
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

DEFAULT = ROOT / "runtime" / "dev" / "approvals-runtime.dev.json"


def target(path):
    path = Path(path).resolve()
    allowed = (ROOT / "runtime").resolve()
    if allowed not in path.parents:
        raise SystemExit("Development configuration must live under the repository runtime/ folder")
    return path


def generate(path, owner):
    path = target(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"owner": owner, "approval_secret": secrets.token_urlsafe(48), "environment": "DEVELOPMENT_ONLY"}, stream)
    return path


def check(path, owner):
    from apex.approvals_web import ApprovalRoutes
    path = target(path)
    ApprovalRoutes(ROOT, path, owner)         # same loader and validation as production
    return path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["generate", "check"])
    parser.add_argument("--owner", required=True)
    parser.add_argument("--path", default=str(DEFAULT))
    args = parser.parse_args(argv)
    path = (generate if args.operation == "generate" else check)(args.path, args.owner)
    print(f"{args.operation}: OK {path} (development only; production /etc/apex file remains required)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

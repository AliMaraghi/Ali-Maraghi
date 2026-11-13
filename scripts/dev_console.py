"""DEVELOPMENT-ONLY console listener on 127.0.0.1 with a LOCAL dev Access configuration.

Not production: the Access snapshot is signed by a throw-away key kept under runtime/dev (Git-ignored, 0600),
it is not a Cloudflare configuration, and the listener is never exposed through the tunnel by this script.
  python3 -B scripts/dev_console.py prepare --owner dev-owner@example.test
  python3 -B scripts/dev_console.py run [--port 18765]          (foreground; waitress from .devdeps/)
  python3 -B scripts/dev_console.py token --owner dev-owner@example.test   (prints a short-lived LOCAL dev token)
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / "runtime" / "dev"
KEY, ACCESS, APPROVALS = DEV / "access-dev-private.pem", DEV / "access-origin.dev.json", DEV / "approvals-runtime.dev.json"
ISSUER = "https://apex-dev.cloudflareaccess.com"
AUDIENCE = hashlib.sha256(b"apex-dev-only").hexdigest()
sys.path[:0] = [str(ROOT / "core"), str(ROOT / ".devdeps")]


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def prepare(owner):
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    DEV.mkdir(mode=0o700, parents=True, exist_ok=True)
    if KEY.exists():
        key = serialization.load_pem_private_key(KEY.read_bytes(), None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_write(KEY, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="dev-1", alg="RS256", use="sig")
    now = int(time.time())
    config = {"issuer": ISSUER, "audience": AUDIENCE, "owner_email": owner, "retrieved_at": now,
              "expires_at": now + 86000, "source_url": ISSUER + "/cdn-cgi/access/certs", "jwks": {"keys": [jwk]},
              "environment": "DEVELOPMENT_ONLY"}
    private_write(ACCESS, json.dumps(config).encode())
    return ACCESS


def token(owner):
    import jwt
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key(KEY.read_bytes(), None)
    now = int(time.time())
    return jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "sub": "dev-subject", "email": owner, "iat": now, "exp": now + 900},
                      key, algorithm="RS256", headers={"kid": "dev-1"})


def run(port):
    if not 1024 <= port <= 65535:
        raise SystemExit("Unprivileged port required")
    from apex import console_server
    # ConsoleApp takes ONE root for both the evidence documents (docs/, .git) and the journal (root/runtime), so the dev
    # listener necessarily shares the project's local, Git-ignored runtime journal: sessions and approval tables are written there.
    sys.argv = ["console_server", "--root", str(ROOT), "--access-config", str(ACCESS), "--port", str(port),
                "--approvals-config", str(APPROVALS)]
    console_server.main()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["prepare", "run", "token"])
    parser.add_argument("--owner", default="dev-owner@example.test")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args(argv)
    if args.operation == "prepare":
        print("prepared", prepare(args.owner), "(development only)")
    elif args.operation == "token":
        print(token(args.owner))
    else:
        run(args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())

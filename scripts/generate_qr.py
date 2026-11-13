#!/usr/bin/env python3
"""Write apex_qr.png: a QR code for the Apex Command Center URL. Status: TESTS_NOT_RUN. Self-contained; needs ONE of: the `qrcode` package (with Pillow), `segno`, or the `qrencode` program.

The QR code contains only the public console address. Scanning it opens the Cloudflare Access login first: the dashboard stays behind Access, no token or secret is embedded.
  python3 generate_qr.py [--url https://console.apexcorelab.uk/] [--out apex_qr.png]
"""
import argparse
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

DEFAULT_URL = "https://console.apexcorelab.uk/"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default="apex_qr.png")
    args = parser.parse_args()
    parts = urlsplit(args.url)
    if parts.scheme != "https" or not (parts.hostname or "").endswith("apexcorelab.uk") or parts.username or parts.query or parts.fragment:
        sys.exit("Refusing: use a plain https://*.apexcorelab.uk address with no credentials or query string")
    try:
        import qrcode
        qrcode.make(args.url).save(args.out)
    except ImportError:
        try:
            import segno
            segno.make(args.url, error="m").save(args.out, scale=10)
        except ImportError:
            if not shutil.which("qrencode"):
                sys.exit("No QR library found. Install one on the laptop:  pip install qrcode[pil]   (or: brew install qrencode / apt install qrencode)")
            subprocess.run(["qrencode", "-s", "10", "-o", args.out, args.url], check=True)
    print(f"Wrote {args.out} for {args.url}")
    print("Scan this QR code with your iPhone to open the Apex Command Center.")


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Checks the legal pages locally and from the public internet. Read-only.
set -u
fail=0
check() {
  local url="$1" want="$2" code body
  code=$(curl -sS -m 20 -o /tmp/apex-legal-check.html -w '%{http_code}' "$url" 2>/dev/null || echo "000")
  body=$(grep -o '<title>[^<]*' /tmp/apex-legal-check.html 2>/dev/null | head -1)
  if [ "$code" = "200" ] && echo "$body" | grep -q "$want"; then
    echo "OK    $url  $code  $body"
  else
    echo "FAIL  $url  $code  ${body:-no title}"; fail=1
  fi
}
check http://127.0.0.1:8787/privacy/ "Privacy Policy"
check http://127.0.0.1:8787/terms/ "Terms of Service"
check https://apexcorelab.uk/privacy "Privacy Policy"
check https://apexcorelab.uk/terms "Terms of Service"
exit $fail

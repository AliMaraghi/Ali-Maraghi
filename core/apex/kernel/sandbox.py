"""Process-level sandbox for untrusted capability-proposal draft code (Phase F).

HONEST LIMITS, stated up front because AGENTS.md forbids root/sudo/Docker in this
workspace: this is NOT kernel-level isolation. There is no container, no Linux
namespace, no seccomp filter. It is defense-in-depth built from three ordinary,
unprivileged mechanisms, each verified empirically against the actual Python on
this machine before being written here (see tests/test_sandbox.py):

  1. A scrubbed environment: the child process inherits no environment variables
     at all except PATH - no API key, no token, nothing this process holds can
     leak through os.environ.
  2. A CPython `sys.addaudithook` installed INSIDE the child, before the
     candidate code executes, that raises PermissionError on: any socket
     connect/bind/getaddrinfo (no network), any subprocess/exec/fork/system/popen
     call (no shelling out), and any `open()` of a path outside the sandbox's own
     throwaway scratch directory or the Python installation's own stdlib/site
     tree (no reading secrets, no reading files outside the sandbox).
  3. POSIX resource limits (`resource.setrlimit`) applied before exec: a CPU-time
     cap (killed with SIGKILL on expiry) and a virtual-address-space cap (raises
     MemoryError), plus a wall-clock subprocess timeout as a backstop.

A sufficiently adversarial script using raw ctypes syscalls, a crafted C
extension, or an undiscovered CPython audit-hook gap could still find a way
through part of this. This blocks the ordinary case - `socket`, `urllib`,
`subprocess`, `os.system`, `open()` on a real file - which is what a drafted
"pure function, no network, no secrets, reads only its arguments" capability
proposal (the exact instruction given to the LLM in propose_capability.py)
would actually attempt. It gives a real, non-fabricated "did not crash" signal
and nothing stronger than that - it is not and has never been a claim of
"safe to auto-deploy."
"""
from __future__ import annotations

import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CPU_SECONDS = 5
ADDRESS_SPACE_BYTES = 256 * 1024 * 1024
MAX_PROCS = 16
TIMEOUT_SECONDS = 10
MAX_CODE_CHARS = 20_000

_BLOCKED_NETWORK = ("socket.connect", "socket.connect_ex", "socket.bind", "socket.getaddrinfo", "socket.sendto")
_BLOCKED_SHELL = ("subprocess.Popen", "os.exec", "os.fork", "os.posix_spawn", "os.system", "os.popen",
                   "os.spawn", "ctypes.dlopen", "ctypes.dlsym")

_PREAMBLE = """
import sys, os
_ALLOWED = {allowed!r}
def _hook(event, args):
    if event in {network!r}:
        raise PermissionError("SANDBOX_NETWORK_DENIED:" + event)
    if event in {shell!r}:
        raise PermissionError("SANDBOX_SUBPROCESS_DENIED:" + event)
    if event == "open":
        try:
            real = os.path.realpath(os.fspath(args[0]))
        except TypeError:
            return
        if not any(real.startswith(p) for p in _ALLOWED):
            raise PermissionError("SANDBOX_FS_DENIED:" + real)
sys.addaudithook(_hook)
"""


def _limits():
    def _set():
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES))
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCS, MAX_PROCS))
        except (ValueError, OSError):
            pass    # platform-dependent; CPU/AS limits above are the load-bearing ones
    return _set


def run_in_sandbox(code: str, timeout: float = TIMEOUT_SECONDS) -> dict:
    """Runs `code` as the entire body of a throwaway subprocess with no network,
    no inherited secrets and filesystem access confined to a fresh scratch
    directory plus the Python installation's own stdlib. Returns a dict with a
    hard pass/fail "did not crash" signal - this is Phase F's one and only claim;
    it is never upgraded to "safe to auto-deploy" anywhere in this codebase."""
    if not isinstance(code, str) or not code.strip():
        return {"crashed": True, "reason": "EMPTY_CODE", "exit_code": None, "stdout": "", "stderr": "", "duration_s": 0.0}
    if len(code) > MAX_CODE_CHARS:
        return {"crashed": True, "reason": "CODE_TOO_LARGE", "exit_code": None, "stdout": "", "stderr": "", "duration_s": 0.0}
    with tempfile.TemporaryDirectory(prefix="apex-sandbox-") as sandbox_dir:
        real_dir = str(Path(sandbox_dir).resolve())
        candidate_path = Path(sandbox_dir) / "candidate.py"
        candidate_path.write_text(code, encoding="utf-8")
        allowed = (real_dir, sys.base_prefix, sys.prefix, sys.exec_prefix)
        preamble = _PREAMBLE.format(allowed=allowed, network=_BLOCKED_NETWORK, shell=_BLOCKED_SHELL)
        wrapper_path = Path(sandbox_dir) / "_run.py"
        wrapper_path.write_text(
            preamble + f"\nexec(compile(open({str(candidate_path)!r}, encoding='utf-8').read(), "
                       f"{str(candidate_path)!r}, 'exec'))\n", encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin"}
        started = time.time()
        try:
            proc = subprocess.run([sys.executable, "-I", str(wrapper_path)], cwd=sandbox_dir, env=env,
                                   capture_output=True, text=True, timeout=timeout, preexec_fn=_limits())
        except subprocess.TimeoutExpired:
            return {"crashed": True, "reason": "TIMEOUT", "exit_code": None, "stdout": "", "stderr": "",
                    "duration_s": round(time.time() - started, 3)}
        duration = round(time.time() - started, 3)
        return {"crashed": proc.returncode != 0,
                "reason": None if proc.returncode == 0 else "NONZERO_EXIT",
                "exit_code": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:],
                "duration_s": duration}

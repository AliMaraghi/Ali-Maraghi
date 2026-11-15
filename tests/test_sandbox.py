"""Phase F smoke tests for core/apex/kernel/sandbox.py - the three things the
sandbox must prove before any capability-proposal code is treated as reviewable:
(a) a trivial script runs, (b) a network call fails, (c) a secret/file read
outside the sandbox fails. These run the REAL subprocess/audit-hook/rlimit
machinery - nothing here is mocked."""
import os
import unittest

from apex.kernel import sandbox


class SandboxSmokeTests(unittest.TestCase):
    def test_a_trivial_script_runs_and_does_not_crash(self):
        out = sandbox.run_in_sandbox("print('hello from sandbox')\nx = 1 + 1\n")
        self.assertFalse(out["crashed"])
        self.assertEqual(out["exit_code"], 0)
        self.assertIn("hello from sandbox", out["stdout"])

    def test_b_a_network_call_fails(self):
        out = sandbox.run_in_sandbox(
            "import socket\ns = socket.socket()\ns.connect(('8.8.8.8', 53))\n")
        self.assertTrue(out["crashed"])
        self.assertIn("SANDBOX_NETWORK_DENIED", out["stderr"])

    def test_b_dns_lookup_also_fails(self):
        out = sandbox.run_in_sandbox("import socket\nsocket.getaddrinfo('example.com', 80)\n")
        self.assertTrue(out["crashed"])
        self.assertIn("SANDBOX_NETWORK_DENIED", out["stderr"])

    def test_c_a_secret_or_arbitrary_file_read_fails(self):
        out = sandbox.run_in_sandbox("open('/etc/hostname').read()\n")
        self.assertTrue(out["crashed"])
        self.assertIn("SANDBOX_FS_DENIED", out["stderr"])

    def test_c_env_is_scrubbed_no_inherited_secret(self):
        os.environ["APEX_TEST_FAKE_SECRET"] = "should-never-leak-into-sandbox"
        try:
            out = sandbox.run_in_sandbox(
                "import os\nprint(os.environ.get('APEX_TEST_FAKE_SECRET'))\n")
        finally:
            del os.environ["APEX_TEST_FAKE_SECRET"]
        self.assertFalse(out["crashed"])
        self.assertIn("None", out["stdout"])

    def test_shelling_out_is_denied(self):
        out = sandbox.run_in_sandbox("import os\nos.system('echo pwned')\n")
        self.assertTrue(out["crashed"])
        self.assertIn("SANDBOX_SUBPROCESS_DENIED", out["stderr"])

    def test_subprocess_module_is_also_denied(self):
        out = sandbox.run_in_sandbox("import subprocess\nsubprocess.Popen(['echo', 'x'])\n")
        self.assertTrue(out["crashed"])
        self.assertIn("SANDBOX_SUBPROCESS_DENIED", out["stderr"])

    def test_ordinary_stdlib_use_still_works(self):
        out = sandbox.run_in_sandbox("import json, re\nprint(json.dumps({'a': 1}))\n")
        self.assertFalse(out["crashed"])
        self.assertIn('{"a": 1}', out["stdout"])

    def test_cpu_bound_infinite_loop_is_killed_not_hung(self):
        out = sandbox.run_in_sandbox("while True:\n    pass\n", timeout=8)
        self.assertTrue(out["crashed"])

    def test_memory_bomb_raises_not_oom_kills_host(self):
        out = sandbox.run_in_sandbox("x = bytearray(2 * 1024 * 1024 * 1024)\n", timeout=8)
        self.assertTrue(out["crashed"])

    def test_empty_or_oversized_code_is_refused_without_spawning(self):
        self.assertEqual(sandbox.run_in_sandbox("")["reason"], "EMPTY_CODE")
        self.assertEqual(sandbox.run_in_sandbox("x" * (sandbox.MAX_CODE_CHARS + 1))["reason"], "CODE_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()

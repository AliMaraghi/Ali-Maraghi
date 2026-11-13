"""Development-only approvals configuration: safe generation, same loader, production path untouched."""
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dev_approvals_config", ROOT / "scripts" / "dev_approvals_config.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class DevConfigTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(dir=ROOT / "runtime"))
        self.path = self.dir / "approvals-runtime.dev.json"

    def tearDown(self):
        for item in self.dir.iterdir():
            item.unlink()
        self.dir.rmdir()

    def test_generate_private_file_and_same_loader_accepts_it(self):
        tool.generate(self.path, "dev@example.test")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        tool.check(self.path, "dev@example.test")
        with self.assertRaises(PermissionError):
            tool.check(self.path, "someone-else@example.test")          # owner mismatch fails closed

    def test_never_overwrites_and_never_prints_secret(self):
        tool.generate(self.path, "dev@example.test")
        with self.assertRaises(FileExistsError):
            tool.generate(self.path, "dev@example.test")
        secret = json.loads(self.path.read_text())["approval_secret"]
        out = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "dev_approvals_config.py"), "check",
                              "--owner", "dev@example.test", "--path", str(self.path)],
                             capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn(secret, out.stdout + out.stderr)

    def test_production_rules_still_apply_to_dev_files(self):
        tool.generate(self.path, "dev@example.test")
        self.path.chmod(0o640)
        with self.assertRaises(PermissionError):
            tool.check(self.path, "dev@example.test")                   # group-readable rejected
        self.path.chmod(0o600)
        self.path.write_text(json.dumps({"owner": "dev@example.test", "approval_secret": "short"}))
        with self.assertRaises(PermissionError):
            tool.check(self.path, "dev@example.test")                   # short secret rejected

    def test_refuses_paths_outside_runtime_including_etc(self):
        for bad in ("/etc/apex/approvals-runtime.json", str(ROOT / "core" / "x.json"), "/tmp/x.json"):
            with self.assertRaises(SystemExit):
                tool.generate(bad, "dev@example.test")

    def test_dev_folder_is_git_ignored_and_production_default_unchanged(self):
        ignored = subprocess.run(["git", "check-ignore", "-q", "runtime/dev/approvals-runtime.dev.json"], cwd=ROOT)
        self.assertEqual(ignored.returncode, 0)
        source = (ROOT / "core" / "apex" / "console_server.py").read_text()
        self.assertIn("default=Path('/etc/apex/approvals-runtime.json')", source)


if __name__ == "__main__":
    unittest.main()

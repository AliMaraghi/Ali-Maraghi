"""Tests for lab-text parsing, location coarsening, the FFmpeg planner, private token/key files and the encrypted dossier. Synthetic data only."""
import base64
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from apex import agents_registry, ffmpeg_plan, health_labs, location_coarse, private_token
from apex.kernel import dossier
from apex.kernel.memory import Ledger


class LabTests(unittest.TestCase):
    TEXT = "Page 1\nHaemoglobin 14.2 g/dL 13.0 - 17.0\nGlucose 6.1 mmol/L (3.9 - 5.5)\nTSH 4.5\nNot a result line\nPage 2\nFerritin 5 ug/L 15 - 200\n"

    def test_parse_flags_provenance_and_review(self):
        rows = {r["test"]: r for r in health_labs.parse_lab_text(self.TEXT, "doc1")}
        self.assertEqual(rows["Haemoglobin"]["flag"], "NORMAL")
        self.assertFalse(rows["Haemoglobin"]["needs_review"])
        self.assertEqual(rows["Glucose"]["flag"], "HIGH")
        self.assertEqual(rows["Ferritin"]["flag"], "LOW")
        self.assertEqual((rows["Ferritin"]["page"], rows["Haemoglobin"]["page"], rows["Haemoglobin"]["document_id"]), (2, 1, "doc1"))
        self.assertTrue(rows["TSH"]["needs_review"])                         # no unit, no range: never guessed
        self.assertIsNone(rows["TSH"]["unit"])
        self.assertEqual(health_labs.reference_check(rows["Glucose"])["inside_printed_range"], False)
        self.assertIsNone(health_labs.reference_check(rows["TSH"])["inside_printed_range"])

    def test_bounds(self):
        with self.assertRaises(ValueError):
            health_labs.parse_lab_text("x\n" * 6000, "d", max_lines=5000)
        with self.assertRaises(ValueError):
            health_labs.parse_lab_text("a\x00b", "d")


class LocationTests(unittest.TestCase):
    PAYLOAD = {"_type": "location", "lat": 51.50721, "lon": -0.12776, "tst": 1_800_000_000, "tid": "ab", "acc": 12}
    ZONES = [{"label": "Home", "lat": 51.5072, "lon": -0.1277, "radius_m": 200, "timezone": "Europe/London"}]

    def test_validation(self):
        out = location_coarse.validate_location(self.PAYLOAD)
        self.assertEqual((out["device"], out["tst"]), ("ab", 1_800_000_000))
        for key, value in (("lat", 91), ("lon", "x"), ("tst", 1.5), ("acc", -1), ("tid", None), ("_type", "transition")):
            with self.assertRaises(location_coarse.LocationError):
                location_coarse.validate_location({**self.PAYLOAD, key: value})

    def test_coarsening_never_returns_raw_coordinates(self):
        zone = location_coarse.coarsen(51.50721, -0.12776, self.ZONES)
        self.assertEqual(zone, {"label": "Home", "timezone": "Europe/London", "resolution": "zone"})
        grid = location_coarse.coarsen(48.85661, 2.35222, self.ZONES)
        self.assertEqual(grid["resolution"], "grid")
        self.assertNotIn("48.85661", str(grid))
        self.assertNotIn("2.35222", str(grid))
        with self.assertRaises(location_coarse.LocationError) as ctx:
            location_coarse.coarsen(123.456, 0, [])
        self.assertNotIn("123.456", str(ctx.exception))

    def test_replay_guard(self):
        now = [1_800_000_100]
        guard = location_coarse.ReplayGuard({}, lambda: now[0], max_age=3600, max_future=60)
        guard.check("ab", 1_800_000_000)
        for tst, why in ((1_800_000_000, "not increasing"), (1_799_999_000 - 5000, "too old"), (1_800_000_300, "future")):
            with self.assertRaises(location_coarse.ReplayError, msg=why):
                guard.check("ab", tst)
        guard.check("ab", 1_800_000_050)
        guard.check("cd", 1_800_000_001)                                      # another device has its own sequence


class FfmpegTests(unittest.TestCase):
    def manifest(self, **shot):
        base = {"shot_id": "s1", "start_seconds": 0, "end_seconds": 3, "clip": "clips/a.mp4", "clip_start_seconds": 1}
        base.update(shot)
        return {"timeline": [base], "duration_seconds": base["end_seconds"], "preset": "720p"}

    def test_plan_is_argument_arrays_without_execution(self):
        plan = ffmpeg_plan.build_plan(self.manifest(), "/tmp/work")
        cmd = plan["commands"][0]
        self.assertIsInstance(cmd, list)
        self.assertTrue(all(isinstance(x, str) for x in cmd))
        self.assertEqual(cmd[:2], ["ffmpeg", "-nostdin"])
        self.assertNotIn("-y", cmd)
        self.assertIn("-protocol_whitelist", cmd)
        self.assertEqual((plan["status"], plan["rendered"]), ("PLAN_ONLY", False))
        self.assertIn("-y", ffmpeg_plan.build_plan(self.manifest(), "/tmp/work", overwrite=True)["commands"][0])

    def test_unsafe_paths_and_values_are_rejected(self):
        for clip in ("../a.mp4", "/etc/passwd.mp4", "http://x/a.mp4", "clips/a.exe", "-flag.mp4", "a b.mp4", "clips//a.mp4", "clips/a.mp4;rm"):
            with self.assertRaises(ValueError, msg=clip):
                ffmpeg_plan.build_plan(self.manifest(clip=clip), "/tmp/work")
        with self.assertRaises(ValueError):
            ffmpeg_plan.build_plan(self.manifest(shot_id="bad id;"), "/tmp/work")
        with self.assertRaises(ValueError):
            ffmpeg_plan.build_plan({**self.manifest(), "duration_seconds": 99}, "/tmp/work")
        with self.assertRaises(ValueError):
            ffmpeg_plan.build_plan(self.manifest(), "/tmp/work", threads=99)


class PrivateFileTests(unittest.TestCase):
    def test_token_file_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t")
            with self.assertRaisesRegex(private_token.PrivateTokenError, "NOT_CONFIGURED"):
                private_token.load(path)
            Path(path).write_text("x" * 40 + "\n")
            os.chmod(path, 0o644)
            with self.assertRaises(ValueError):
                private_token.load(path)
            os.chmod(path, 0o600)
            self.assertEqual(private_token.load(path), "x" * 40)
            Path(path).write_text("short")
            with self.assertRaises(ValueError) as ctx:
                private_token.load(path)
            self.assertNotIn("short", str(ctx.exception))
            link = os.path.join(tmp, "link")
            os.symlink(path, link)
            with self.assertRaises(ValueError):
                private_token.load(link)

    def test_key_file_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "k")
            Path(path).write_bytes(base64.urlsafe_b64encode(os.urandom(32)))
            os.chmod(path, 0o600)
            self.assertEqual(len(dossier.load_key(path)), 32)
            os.chmod(path, 0o640)
            with self.assertRaises(ValueError):
                dossier.load_key(path)
            os.chmod(path, 0o600)
            Path(path).write_bytes(base64.urlsafe_b64encode(os.urandom(16)))
            with self.assertRaises(ValueError):
                dossier.load_key(path)


class DossierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        self.key = os.urandom(32)
        self.d = dossier.Dossier(self.ledger, self.key, clock=lambda: 1.0, data_source="personal")
        self.cli = dossier.Requester.local_cli()
        self.d.put(self.cli, "profile.city", 1, {"city": "Londonshire"})
        self.d.put(self.cli, "career.history", 2, {"role": "engineer"})
        self.d.put(self.cli, "lang.sentence_length", 3, {"mean": 12.5})
        self.d.put(self.cli, "location.exact", 4, {"lat": 51.5})

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def agent(self, agent_id):
        return dossier.Requester.agent(agent_id)

    def test_encrypted_at_rest_and_roundtrip(self):
        raw = self.ledger.db.execute("SELECT ciphertext FROM personal_dossier WHERE key='profile.city'").fetchone()[0]
        self.assertNotIn(b"Londonshire", raw)
        self.assertEqual(self.d.get(self.agent("8-1"), "profile.city"), {"city": "Londonshire"})
        self.assertEqual(self.d.get(self.cli, "location.exact"), {"lat": 51.5})

    def test_tier_ceilings_prefixes_and_firewall(self):
        denied = (("8-1", "career.history", "TIER_ABOVE_AGENT_CEILING"), ("8-1", "location.exact", "TIER4_LOCAL_CLI_ONLY"),
                  ("8-8", "profile.city", "KEY_PREFIX_NOT_ALLOWED"), ("8-11a", "profile.city", "TIER_ABOVE_AGENT_CEILING"),
                  ("8-13", "profile.city", "AGENT_UNKNOWN_OR_UNRESOLVED"), ("8-99", "profile.city", "AGENT_UNKNOWN_OR_UNRESOLVED"))
        for agent_id, key, reason in denied:
            with self.assertRaisesRegex(dossier.DossierError, reason, msg=f"{agent_id} {key}"):
                self.d.get(self.agent(agent_id), key)
        self.assertEqual(self.d.get(self.agent("8-8"), "lang.sentence_length"), {"mean": 12.5})
        self.assertEqual(self.d.get(self.agent("8-9"), "career.history"), {"role": "engineer"})

    def test_agents_cannot_write_and_corporate_source_blocks_agents(self):
        with self.assertRaisesRegex(dossier.DossierError, "WRITE_LOCAL_CLI_ONLY"):
            self.d.put(self.agent("8-1"), "profile.x", 1, {})
        corporate = dossier.Dossier(self.ledger, self.key, data_source="corporate")
        with self.assertRaisesRegex(dossier.DossierError, "CORPORATE_SOURCE_DENIED"):
            corporate.get(self.agent("8-1"), "profile.city")
        self.assertEqual(corporate.get(self.cli, "profile.city"), {"city": "Londonshire"})

    def test_tamper_detection_binds_ciphertext_to_key_and_tier(self):
        a = self.ledger.db.execute("SELECT nonce,ciphertext FROM personal_dossier WHERE key='profile.city'").fetchone()
        self.ledger.db.execute("UPDATE personal_dossier SET nonce=?, ciphertext=? WHERE key='career.history'", a)
        with self.assertRaisesRegex(dossier.DossierError, "DECRYPTION_FAILED"):
            self.d.get(self.agent("8-9"), "career.history")
        other = dossier.Dossier(self.ledger, os.urandom(32))
        with self.assertRaisesRegex(dossier.DossierError, "DECRYPTION_FAILED"):
            other.get(self.cli, "profile.city")

    def test_every_attempt_is_logged_without_plaintext_and_log_is_append_only(self):
        self.d.get(self.agent("8-1"), "profile.city")
        with self.assertRaises(dossier.DossierError):
            self.d.get(self.agent("8-1"), "location.exact")
        log = self.d.access_log()
        outcomes = [(r["requester"], r["key"], r["outcome"], r["reason"]) for r in log[:2]]
        self.assertIn(("8-1", "location.exact", "DENIED", "TIER4_LOCAL_CLI_ONLY"), outcomes)
        self.assertIn(("8-1", "profile.city", "OK", "READ"), outcomes)
        self.assertNotIn("Londonshire", str(log))
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.db.execute("UPDATE dossier_access_log SET outcome='OK'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.db.execute("DELETE FROM dossier_access_log")
        self.assertIn("TIER4_STORED_ON_VPS", [r["reason"] for r in log])         # the tier-4 write is flagged


if __name__ == "__main__":
    unittest.main()

import base64, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import local_llm, scout_common, skin_analyzer
from apex.kernel.budget import Budget
from apex.kernel.memory import Ledger

IMAGE = base64.b64encode(b"x" * 200).decode()


class Skin(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(Path(tempfile.mkdtemp()))
        self.budget = Budget(self.ledger)
        self.budget.set_price(scout_common.PROVIDER, scout_common.SKU, 2000, 1.0, "test")
        self.budget.set_cap(scout_common.POOL, "day", 100)
        self.saved = (os.environ.get("APEX_LLM_PROVIDER"), local_llm.chat)

    def tearDown(self):
        os.environ.pop("APEX_LLM_PROVIDER", None)
        if self.saved[0] is not None:
            os.environ["APEX_LLM_PROVIDER"] = self.saved[0]
        local_llm.chat = self.saved[1]
        self.ledger.close()

    def test_a_face_photo_never_goes_to_a_hosted_model(self):
        os.environ.pop("APEX_LLM_PROVIDER", None)
        with self.assertRaises(skin_analyzer.SkinError):
            skin_analyzer.suggest(self.budget, IMAGE, "image/jpeg")

    def test_local_model_gets_the_image_and_bad_input_is_refused(self):
        os.environ["APEX_LLM_PROVIDER"] = "ollama"
        seen = {}
        def fake(system, messages, max_tokens=0, json_mode=False):
            seen.update(images=messages[0]["images"], system=system)
            return "Use SPF  every morning."
        local_llm.chat = fake
        self.assertEqual(skin_analyzer.suggest(self.budget, IMAGE, "image/jpeg"), "Use SPF every morning.")
        self.assertEqual(seen["images"], [IMAGE])
        self.assertIn("Do not name or suggest any medical condition", seen["system"])
        for bad in ((IMAGE, "image/gif"), ("not base64 !!" * 20, "image/png"), (None, "image/png")):
            with self.assertRaises(ValueError):
                skin_analyzer.suggest(self.budget, *bad)


if __name__ == "__main__":
    unittest.main()

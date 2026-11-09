"""Run all available tests without installing dependencies or touching services."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["PYTHONPATH"] = str(ROOT / "core")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def main():
    (ROOT / "work").mkdir(exist_ok=True)
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        functions = [node.name for node in ast.parse(path.read_text()).body
                     if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
        missing = [x for x in ("fastapi", "httpx") if importlib.util.find_spec(x) is None] if path.name == "test_app.py" else []
        if missing:
            for name in functions:
                def unavailable():
                    pass
                unavailable.__name__ = name
                suite.addTest(unittest.FunctionTestCase(unittest.skip("Missing optional dependencies: " + ", ".join(missing))(unavailable), description=f"{path.name}:{name}"))
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
        for name in functions:
            suite.addTest(unittest.FunctionTestCase(getattr(module, name)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"tests_run": result.testsRun, "passed": result.testsRun - len(result.skipped) - len(result.failures) - len(result.errors),
                      "skipped": len(result.skipped), "failures": len(result.failures), "errors": len(result.errors),
                      "scope": "OFFLINE_TESTS_NOT_DEPLOYMENT_OR_REAL_WORLD_VALIDATION"}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

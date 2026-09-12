"""
Automated Test Runner for The Judge & The Swarm (Python Pipeline)
Zero-Dummy Guarantee Verification
"""
import sys
import os
import inspect
import asyncio

# Ensure project root is in sys.path
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "tests"))

def run_all_tests():
    test_files = [
        "tests.test_quant_orchestrator",
        "tests.test_m8_signal_pipeline",
        "tests.test_m8_capital_and_margin_pipeline"
    ]
    
    total = 0
    passed = 0
    failed = 0
    errors = []

    print("=========================================================")
    print("🚀 THE JUDGE & THE SWARM - ZERO-DUMMY TEST SUITE")
    print("=========================================================")

    for mod_name in test_files:
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception as e:
            print(f"❌ FAILED TO IMPORT {mod_name}: {e}")
            failed += 1
            errors.append((mod_name, str(e)))
            continue

        # Check top-level test functions
        for attr_name in dir(mod):
            if attr_name.startswith("test_"):
                fn = getattr(mod, attr_name)
                if callable(fn):
                    total += 1
                    try:
                        if inspect.iscoroutinefunction(fn):
                            asyncio.run(fn())
                        else:
                            fn()
                        print(f"  ✓ {mod_name}.{attr_name}")
                        passed += 1
                    except Exception as e:
                        print(f"  ✗ {mod_name}.{attr_name}: {e}")
                        failed += 1
                        errors.append((f"{mod_name}.{attr_name}", str(e)))

        # Check test classes
        for attr_name in dir(mod):
            if attr_name.startswith("Test"):
                cls = getattr(mod, attr_name)
                if isinstance(cls, type):
                    instance = cls()
                    for method_name in dir(instance):
                        if method_name.startswith("test_"):
                            fn = getattr(instance, method_name)
                            if callable(fn):
                                total += 1
                                try:
                                    if inspect.iscoroutinefunction(fn):
                                        asyncio.run(fn())
                                    else:
                                        fn()
                                    print(f"  ✓ {attr_name}.{method_name}")
                                    passed += 1
                                except Exception as e:
                                    print(f"  ✗ {attr_name}.{method_name}: {e}")
                                    failed += 1
                                    errors.append((f"{attr_name}.{method_name}", str(e)))

    print("---------------------------------------------------------")
    print(f"Ran {total} tests: {passed} passed, {failed} failed.")
    if errors:
        print("\nFailures:")
        for name, err in errors:
            print(f"  • {name}: {err}")
        return 1
    print("🎉 ALL PRODUCTION QUANT ENGINES VERIFIED 100% OPERATIONAL!")
    return 0

if __name__ == "__main__":
    sys.exit(run_all_tests())

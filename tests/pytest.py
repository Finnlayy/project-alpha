"""
Lightweight Drop-in pytest Compatibility Shim for Environments Without External pytest Package.
Allows all tests to run seamlessly via unittest or direct python execution.
"""
import asyncio
import re
import sys
from contextlib import contextmanager

class _Mark:
    @staticmethod
    def asyncio(func):
        def wrapper(*args, **kwargs):
            return asyncio.run(func(*args, **kwargs))
        return wrapper

mark = _Mark()

def fixture(func):
    return func

@contextmanager
def raises(expected_exception, match=None):
    try:
        yield
    except expected_exception as e:
        if match:
            assert re.search(match, str(e)), f"Pattern '{match}' did not match '{str(e)}'"
        return
    except Exception as e:
        raise AssertionError(f"Expected {expected_exception.__name__}, got {type(e).__name__}: {e}")
    raise AssertionError(f"Expected exception {expected_exception.__name__} was not raised")

def main(args=None):
    import unittest
    unittest.main()

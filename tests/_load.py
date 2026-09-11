"""Test helpers for loading yar's guard scripts.

The guard scripts live at hyphenated paths (e.g. ``scripts/git-guard.py``), which
cannot be imported with a normal ``import`` statement. ``load()`` loads them from a
path under the repo root with a clean module name so their pure functions can be
unit-tested directly. Scripts whose decision logic runs at import time
(``english-guard``, ``branch-guard``, ``pre-commit``) are exercised via subprocess
instead — see the tests that use ``REPO``.
"""
import importlib.util
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)


def load(relpath, modname):
    """Load ``<REPO>/<relpath>`` as a module named ``modname`` and return it."""
    path = os.path.join(REPO, relpath)
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

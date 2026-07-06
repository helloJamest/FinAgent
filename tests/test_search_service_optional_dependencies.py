import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_search_service_imports_when_newspaper_is_missing():
    code = r"""
import builtins

real_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "newspaper" or name.startswith("newspaper."):
        raise ModuleNotFoundError("No module named 'newspaper'")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import

from src.search_service import fetch_url_content

assert fetch_url_content("https://example.invalid") == ""
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr or result.stdout

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ai_asset_governance_script_passes():
    result = subprocess.run(
        [sys.executable, "scripts/check_ai_assets.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout

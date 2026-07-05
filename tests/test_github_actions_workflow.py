from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_ANALYSIS_WORKFLOW = ROOT / ".github" / "workflows" / "daily_analysis.yml"


def test_daily_analysis_workflow_is_present_and_triggerable():
    assert DAILY_ANALYSIS_WORKFLOW.exists()

    text = DAILY_ANALYSIS_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "main.py" in text
    assert "STOCK_LIST:" in text
    assert "GEMINI_API_KEY:" in text
    assert "OPENAI_API_KEY:" in text
    assert "--force-run" in text

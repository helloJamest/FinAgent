from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_ANALYSIS_WORKFLOW = ROOT / ".github" / "workflows" / "daily_analysis.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "README.md"


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


def test_ci_workflow_matches_documented_required_gates():
    assert CI_WORKFLOW.exists()

    text = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "ai-governance" in text
    assert "backend-gate" in text
    assert "docker-build" in text
    assert "web-gate" in text
    assert "scripts/ci_gate.sh" in text
    assert "npm run lint" in text
    assert "npm run build" in text


def test_readme_ci_badge_points_to_existing_workflow():
    readme = README.read_text(encoding="utf-8")

    assert "actions/workflows/ci.yml" in readme
    assert CI_WORKFLOW.exists()

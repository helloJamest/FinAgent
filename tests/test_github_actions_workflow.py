import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_ANALYSIS_WORKFLOW = ROOT / ".github" / "workflows" / "daily_analysis.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
NETWORK_SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "network-smoke.yml"
PR_REVIEW_WORKFLOW = ROOT / ".github" / "workflows" / "pr-review.yml"
README = ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
WEB_PACKAGE = ROOT / "apps" / "finagent-web" / "package.json"
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
DOCKERFILE = ROOT / "docker" / "Dockerfile"
BACKEND_GATE_SCRIPT = ROOT / "scripts" / "ci_gate.sh"
TEST_SH = ROOT / "test.sh"


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
    web_scripts = json.loads(WEB_PACKAGE.read_text(encoding="utf-8"))["scripts"]

    assert "ai-governance" in text
    assert "backend-gate" in text
    assert "docker-build" in text
    assert "web-gate" in text
    assert "scripts/ci_gate.sh" in text
    assert DOCKERFILE.exists()
    assert "docker build -f docker/Dockerfile" in text
    assert "import api.app; import src.core.pipeline; import data_provider.base" in text
    assert "npm run lint" in text
    assert "npm test" in text
    assert "npm run build" in text
    assert {"lint", "test", "build"} <= set(web_scripts)


def test_backend_gate_script_keeps_required_phases():
    assert BACKEND_GATE_SCRIPT.exists()
    assert TEST_SH.exists()

    text = BACKEND_GATE_SCRIPT.read_text(encoding="utf-8")

    for required_text in (
        "syntax_check()",
        "flake8_checks()",
        "deterministic_checks()",
        "offline_test_suite()",
        "python -m py_compile",
        "flake8 . --count --select=E9,F63,F7,F82",
        "bash test.sh code",
        "bash test.sh yfinance",
        'python -m pytest -m "not network"',
        "syntax)",
        "flake8)",
        "deterministic)",
        "offline-tests)",
    ):
        assert required_text in text


def test_network_smoke_workflow_is_non_blocking_and_triggerable():
    assert NETWORK_SMOKE_WORKFLOW.exists()

    text = NETWORK_SMOKE_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "continue-on-error: true" in text
    assert "python -m pytest -m network" in text
    assert "bash test.sh quick --dry-run --no-notify" in text


def test_pr_review_workflow_keeps_static_checks():
    assert PR_REVIEW_WORKFLOW.exists()

    text = PR_REVIEW_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in text
    assert "python scripts/check_ai_assets.py" in text
    assert "test -f .github/PULL_REQUEST_TEMPLATE.md" in text


def test_readme_ci_badge_points_to_existing_workflow():
    readme = README.read_text(encoding="utf-8")

    assert "actions/workflows/ci.yml" in readme
    assert CI_WORKFLOW.exists()


def test_agents_ci_matrix_mentions_existing_workflows():
    agents = AGENTS.read_text(encoding="utf-8")

    for required_text in (
        "ai-governance",
        "backend-gate",
        "docker-build",
        "web-gate",
        "network-smoke",
        "pr-review",
        ".github/workflows/ci.yml",
        ".github/workflows/network-smoke.yml",
        ".github/workflows/pr-review.yml",
        "npm test",
    ):
        assert required_text in agents


def test_pr_template_keeps_required_delivery_sections():
    template = PR_TEMPLATE.read_text(encoding="utf-8")

    for heading in (
        "## PR Type",
        "## Background And Problem",
        "## Scope Of Change",
        "## Verification Commands And Results",
        "## Compatibility And Risk",
        "## Rollback Plan",
    ):
        assert heading in template

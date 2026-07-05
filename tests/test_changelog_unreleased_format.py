from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"
ALLOWED_TYPES = {"新功能", "改进", "修复", "文档", "测试", "chore"}


def _unreleased_lines() -> list[str]:
    text = CHANGELOG.read_text(encoding="utf-8")
    start = text.index("## [Unreleased]")
    rest = text[start:].splitlines()[1:]
    lines: list[str] = []
    for line in rest:
        if line.startswith("## ["):
            break
        lines.append(line)
    return lines


def test_unreleased_changelog_uses_flat_allowed_types():
    entries = [line for line in _unreleased_lines() if line.startswith("- [")]

    assert entries
    for entry in entries:
        entry_type = entry.split("]", 1)[0].removeprefix("- [")
        assert entry_type in ALLOWED_TYPES, entry


def test_unreleased_changelog_has_no_category_headings():
    headings = [line for line in _unreleased_lines() if line.startswith("### ")]

    assert headings == []

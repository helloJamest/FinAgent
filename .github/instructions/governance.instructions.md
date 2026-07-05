# Governance Instructions

Canonical source: `AGENTS.md`.

- Do not commit, tag, or push without explicit user confirmation.
- Keep `.env.example` and relevant docs in sync with new configuration.
- Update `docs/CHANGELOG.md` for user-visible, CLI/API, deployment, workflow, notification, or report changes.
- Keep `[Unreleased]` flat: `- [类型] 描述`, with type one of `新功能`, `改进`, `修复`, `文档`, `测试`, or `chore`.
- Run `python scripts/check_ai_assets.py` after changing AI collaboration assets.

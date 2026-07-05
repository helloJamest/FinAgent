# Backend Instructions

Canonical source: `AGENTS.md`.

- Put backend changes in `src/`, `data_provider/`, `api/`, or `bot/`.
- Prefer existing services, repositories, schemas, and scripts.
- Validate Python backend changes with `bash scripts/ci_gate.sh` when practical.
- For small Python edits, at minimum run `python -m py_compile <changed_python_files>`.
- Keep data-source fallback and notification failure paths fail-open unless the task explicitly says otherwise.

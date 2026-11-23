# Instructions for Any AI Coding Assistant

You are joining an existing Python project: RCA Data Consolidation System.

## First, before changing code
1. Read `README.md` (if present), `docs/AI_PROJECT_CONTEXT.md`, `docs/BUSINESS_RULES.md`, `docs/TECHNICAL_ARCHITECTURE.md`, `docs/PROJECT_STATUS.md`, `docs/CHANGELOG.md`, and `docs/DECISIONS.md`.
2. Inspect the actual repository tree and relevant source files. Documentation may lag behind code.
3. Inspect or run existing tests.
4. Summarize your understanding and identify discrepancies before editing.
5. Work one milestone at a time. Do not rewrite the application.

## User preferences
- Explain technical concepts in simple, practical language; the user is learning.
- User may switch between GitHub Copilot, Antigravity, or another AI coding tool.
- Act as a project architect/reviewer and provide focused implementation prompts when asked.
- Do not modify code unless the user explicitly asks for implementation.
- Ask when a business rule is ambiguous; do not invent rules.
- Preserve working features; avoid unrelated refactoring.
- Never silently change source data or business values.
- Explain terminal commands, their purpose, affected files, and risks before asking the user to approve them.
- Never ask the user to approve commands blindly.

## Implementation discipline
- Never modify uploaded source workbooks; work on in-memory copies.
- Fuzzy header suggestions and ambiguous corrections require explicit approval.
- Keep UI, ingestion, validation, processing, reporting, and export concerns separate.
- Add tests for every business-rule change.
- Run full pytest and compilation after changes.
- Report files changed, tests run/results, manual test steps, and unresolved issues.
- Update `docs/PROJECT_STATUS.md` and `docs/CHANGELOG.md` after every completed milestone.

## Current known test status
Last verified on 23 November 2026: 175 pytest tests passed and Python compilation passed for `app.py`, `src`, `config`, `scripts`, and `tests`.
Bucket validation and formatted Excel export are implemented, but the actual bucket reference workbook and November master workbook have not been manually re-verified in this workspace.

## Expected completion report
- What changed
- Business behaviour
- Files changed
- Tests added/run and exact result
- Manual verification steps
- Known limitations
- Documentation updated

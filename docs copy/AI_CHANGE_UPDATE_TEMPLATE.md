# Documentation Update Prompt

After every completed implementation, give the coding agent this instruction:

```text
Update the project handoff documentation to reflect ONLY changes actually implemented and verified.

Read the existing documentation first. Do not claim unfinished work is complete.

Update:
1. docs/PROJECT_STATUS.md — feature status, limitations, manual test status.
2. docs/CHANGELOG.md — add dated entry at top with behaviour, files changed, tests, and limitations.
3. docs/BUSINESS_RULES.md — only when the user explicitly changes/clarifies a business rule.
4. docs/TECHNICAL_ARCHITECTURE.md — only when actual modules/architecture change.
5. docs/DECISIONS.md — only for decisions explicitly approved by the user.
6. docs/BUCKET_REFERENCE.md — only after verifying against the actual reference workbook.

Do not fabricate dates, test counts, file paths, or implementation status. Check that documentation agrees with code and test output. Report documentation files changed.
```

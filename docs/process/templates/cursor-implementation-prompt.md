# Cursor Implementation Prompt Template

Use this to keep implementation focused, test-first, and token-efficient.

## Prompt

```text
Implement only Task {{task_id}}.

Goal:
{{task_goal}}

Allowed files:
{{allowed_files}}

Do not edit:
{{forbidden_files}}

Branch:
codex/{{feature_name}}

Rules:
- TDD required: write failing tests first, then minimum code, then refactor
- Keep PR small and reviewable (target <300 changed lines)
- Add clear comments/docstrings for non-obvious logic in simple language
- No unrelated refactors
- Keep output concise

Required steps:
1) Show test plan first (unit/integration/edge cases)
2) Add failing tests
3) Implement minimum code to pass
4) Refactor safely
5) Run checks:
   - lint
   - typecheck
   - tests
   - coverage
6) Provide final output in this format only:
   - Changed files
   - Why each change was needed
   - Commands run
   - Test results
   - Remaining risks
```


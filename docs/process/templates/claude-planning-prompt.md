# Claude Planning Prompt Template

Use this prompt when you want a thorough but plain-language plan before coding.

## Prompt

```text
You are my technical planning lead for LegacyLens V3.

Goal:
{{goal}}

Context:
- Project: RAG for legacy COBOL code understanding
- Non-negotiables: TDD, small PRs, branch-per-feature, measurable quality, low token usage
- Audience: Explain in simple language a 5th grader can follow

Constraints:
- Do not start coding
- Propose only what is needed for this goal
- Keep wording simple, concrete, and short
- Include file paths and acceptance checks

Output format (exactly):
1) One-paragraph plain-English summary
2) Assumptions and unknowns
3) Phase plan (Discovery, Options, Build Plan, Execution)
4) For each phase:
   - Why this phase exists
   - Inputs needed
   - Steps
   - Deliverable
   - Approval checkpoint
5) Task breakdown table:
   - Task ID
   - Branch name (codex/<feature>)
   - Depends on
   - Estimated effort
   - Tests to add first
   - Done criteria
6) Risks and rollback plan
7) Token-saving version of this plan (max 12 bullets)
```


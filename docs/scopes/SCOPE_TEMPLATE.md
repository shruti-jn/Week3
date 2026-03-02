# Scope Document Template

Copy this file and fill it in before starting any medium or large feature branch.
Save it as `docs/scopes/feature-<name>.md` and attach it to the PR.
Delete after the feature is merged.

---

## Branch Name
`feature/<scope>-<description>`

## WHAT ARE WE BUILDING?
<!-- Explain it like you're describing it to a 10-year-old. No jargon allowed.
     Use an analogy if the concept is abstract.
     Example: "We're building a tool that reads a COBOL file and breaks it into chapters,
     like a table of contents, so the AI can find the right piece later." -->

## WHY DOES IT MATTER?
<!-- One sentence: what breaks or can't happen if we skip this? -->

## WHAT DOES "DONE" LOOK LIKE?
<!-- Write the acceptance criteria. These become your test cases.
     Use checkboxes — you'll tick them off during code review. -->

- [ ] Given [input], the system [does what]
- [ ] Given [edge case input], the system [handles it how]
- [ ] Given [failure input], the system [fails gracefully how]
- [ ] All unit tests pass (`pytest -m "not integration"`)
- [ ] Coverage ≥ 80% for new code

## WHAT COULD GO WRONG?
<!-- List 2-3 risks and how we'll handle them -->

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| [risk description] | High/Med/Low | [how we handle it] |

## WHAT ARE THE DEPENDENCIES?
<!-- What must be merged before this branch can start? -->

- [ ] Depends on: `feature/xxx` (merged? yes/no)
- [ ] External: [any external service, API, or data needed]

## IS THERE EXISTING CODE TO REUSE?
<!-- Grep the codebase before writing new code. List any relevant existing functions. -->

- [ ] Checked for existing patterns: `grep -r "keyword" backend/app/`
- Relevant existing code: [file:function or "none found"]

## IS THIS ON THE MVP CRITICAL PATH?
<!-- If yes, do the simplest possible version first. Note what to skip for MVP. -->

- On critical path: yes/no
- MVP simplification: [what to skip or simplify to hit the deadline]
- Full implementation: [what the complete version looks like post-MVP]

## ESTIMATED COMPLEXITY
<!-- Small: < 1 hour | Medium: 1-4 hours | Large: 4-8 hours | XL: > 8 hours -->

Estimated complexity: ___

## TECH DEBT TO WATCH FOR
<!-- Note shortcuts you might be tempted to take and why they're risky -->

- Avoid: [pattern to avoid and why]

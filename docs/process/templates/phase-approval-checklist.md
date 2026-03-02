# Phase Approval Checklist

Use this before moving from one phase to the next.

## Phase 1: Discovery Approval
- [ ] Problem statement is clear in plain language
- [ ] Constraints are listed (time, quality, cost, tools)
- [ ] Unknowns and risks are explicit
- [ ] Success metrics are measurable
- [ ] Stakeholder approval recorded

## Phase 2: Options Approval
- [ ] 2 to 3 options compared with tradeoffs
- [ ] Decision matrix includes: quality, speed, cost, complexity
- [ ] Chosen option has clear reason
- [ ] Rejected options are documented
- [ ] Stakeholder approval recorded

## Phase 3: Build Plan Approval
- [ ] Tasks are split into small reviewable units
- [ ] Each task has branch name `codex/<feature>`
- [ ] Each task includes tests-to-write-first
- [ ] Dependencies and parallelizable tasks are marked
- [ ] Done criteria per task are objective
- [ ] Stakeholder approval recorded

## Phase 4: Execution Approval
- [ ] PRs are small and focused
- [ ] Quality gates passed
- [ ] Docs/context files updated
- [ ] Demo or evidence captured
- [ ] Remaining risks and next steps listed
- [ ] Final stakeholder approval recorded

## Parallel Work Guardrails
- [ ] Shared contracts defined first (API schemas, data models)
- [ ] Merge order decided for dependent branches
- [ ] Rebase schedule set (for example: twice daily)
- [ ] Conflict owner assigned per shared area

## Token Efficiency Guardrails
- [ ] Prompts include scope and exact output format
- [ ] Reused context files instead of repeating background
- [ ] No open-ended brainstorming in implementation prompts
- [ ] Responses requested as concise diffs + results


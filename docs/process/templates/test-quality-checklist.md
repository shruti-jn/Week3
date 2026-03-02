# Test Quality Checklist (A+ Standard)

Use this per feature and per PR.

## 1) Coverage Basics
- [ ] Line coverage meets target (start 85%, move to 90%+)
- [ ] Branch coverage meets target (start 80%, move to 90%+)
- [ ] Critical paths have direct tests (ingestion, chunking, retrieval, citations)

## 2) Test Strength
- [ ] Mutation score meets target (start 60%, move to 70%+)
- [ ] Assertions verify behavior, not just status codes
- [ ] At least one negative/failure test per public function

## 3) Edge Cases
- [ ] Empty input
- [ ] Very large input
- [ ] Invalid encoding/special characters
- [ ] Missing metadata
- [ ] Duplicate chunks
- [ ] Zero search results
- [ ] Threshold fallback path
- [ ] Timeout/retry behavior

## 4) RAG-Specific Evaluation
- [ ] Golden query set exists (10 to 20 real queries)
- [ ] Precision@5 measured and logged
- [ ] Citation correctness checked (file + line range)
- [ ] Latency measured end to end
- [ ] Failure cases documented

## 5) Regression Safety
- [ ] Every bug fix includes a regression test
- [ ] Contract tests protect API schemas
- [ ] Snapshot tests are used only when stable and meaningful

## 6) Review Readiness
- [ ] Test names describe user-visible behavior
- [ ] Tests are deterministic (no flaky timing assumptions)
- [ ] Arrange/Act/Assert structure is clear


# 06 — Non-functional Requirements & Security

## Security and confidentiality
- Sources may contain client-confidential information. Data stays in the BDO tenant; LLM calls go only to
  approved endpoints configured in S1 (no consumer endpoints). No training on customer data per provider terms.
- Encryption: TLS 1.2+ in transit; storage encryption at rest; `pii_map.value_encrypted` with a KMS key.
- RBAC per process: SMEs see only their questions and the minimal context snippet; viewers cannot see raw sources
  unless granted.
- Prompt injection: source text is always passed as delimited data with an instruction that content inside
  delimiters is not instructions; LLM outputs are schema-validated and path-restricted (M6 §5); excerpt
  verification (M2) prevents fabricated evidence.
- Secrets in Key Vault; none in repo.

## Audit
- Every patch, acceptance, rejection, sign-off, waiver, question send, answer and export written to `audit_log`
  (append-only).
- Every LLM call logged with the prompt **file name and content hash** — reproducible "which prompt made
  this" for any element.
- Retention: configurable; default 7 years for audit, sources deletable per data-retention policy (deleting a
  source removes excerpts from provenance and recomputes confidence, keeping an audit tombstone).

## Performance targets
| Operation | Target |
|---|---|
| Ingest + parse a 30-page SOP | < 60 s |
| First draft IR from 3 sources | < 5 min |
| Patch apply (validate + version + score) | p95 < 300 ms |
| Structural gap scan | p95 < 1 s for 200-node IR |
| Canvas render 200 nodes | < 1.5 s |

## Reliability
- Workers idempotent; at-least-once events; transactional outbox.
- LLM failures: retry with backoff (3×); circuit breaker per model; jobs surface `failed` with reason in UI.

## Observability
OpenTelemetry traces across API → worker → LLM gateway with `correlation_id`; metrics: gaps opened/resolved per
day, question answer latency, time-to-ready per process (the headline KPI), LLM cost per process.

## Accessibility
WCAG 2.2 AA for all screens; canvas operations available via side panel and keyboard.

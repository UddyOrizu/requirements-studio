# 03 — API & Event Contracts

Base path `/api/v1`. JSON. Auth: OIDC bearer token; RBAC roles `admin`, `requester` (idea owner; becomes `owner` of the process they start), `owner` (per process), `ba`, `sme`,
`viewer`, `system:mother`. All mutating endpoints accept `Idempotency-Key`. Errors: RFC 7807 problem+json.

## 1. Endpoints

| Method | Path | Role | Module | Notes |
|---|---|---|---|---|
| GET | `/ideas?status=&owner=&q=` | viewer | M12 | Ideas list with stats |
| POST | `/ideas` | requester | M12/M0 | `{text, has_process_today, files?}` → idea + session + first question |
| GET | `/ideas/{id}` · `/ideas/{id}/flow?variant=&format=` · `/ideas/{id}/flow/compare` | viewer | M12/M10 | detail, flows, as-is vs to-be |
| POST | `/ideas/{id}/suggestions:generate` · GET `/ideas/{id}/suggestions` | requester | M11 | |
| POST | `/suggestions/{sid}/accept` · `/reject {reason}` · `/edit {instruction}` | requester | M11 | accept = patch on the to-be |
| POST | `/stories/{sid}/refine {instruction}` → preview · POST `/stories/{sid}/refine/{pid}/apply` · GET `/stories/{sid}/history` | requester, ba | M12 | |
| GET | `/ideas/{id}/exports/formats` · POST `/ideas/{id}/exports {formats}` · GET `/exports/{id}/download` | owner, viewer | M9 | Lucidchart, Markdown, Gherkin, Jira, ADO, xlsx, CSV |
| POST | `/intake-sessions` | requester | M0 | `{idea_text, title?, files?}` → process + session + first question |
| GET | `/intake-sessions/{id}` | requester, ba | M0 | phase, coverage, timeline |
| POST | `/intake-sessions/{id}/answers` | requester | M0 | `{text?, choice?, special?, ask_sme_id?}` → captured + next question |
| POST | `/intake-sessions/{id}/turns/{n}/undo` | requester | M0 | inverse patch |
| POST | `/intake-sessions/{id}/jump` | requester | M0 | `{phase: "validate"}` |
| WS | `/intake-sessions/{id}/stream` | requester | M0 | streamed questions, captured cards, SME answers |
| POST | `/processes` | ba | M3 | `{name, domain, owner_user_id, description}` → IR v0 |
| GET | `/processes` · `/processes/{pid}` | viewer | M3 | includes readiness summary |
| GET | `/processes/{pid}/ir?version=` | viewer | M3 | latest by default |
| GET | `/processes/{pid}/ir/diff?from=&to=` | viewer | M3 | JSON Patch |
| POST | `/processes/{pid}/patches` | ba, owner, agent | M3 | body = patch envelope |
| POST | `/patches/{id}/accept` · `/reject` | owner, ba | M3 | reject requires `reason` |
| POST | `/processes/{pid}/sources` | ba | M1 | multipart |
| GET | `/processes/{pid}/sources` · `/sources/{sid}` · `/sources/{sid}/blocks` | viewer | M1 | |
| DELETE | `/sources/{sid}` | ba | M1 | soft delete + re-reconcile |
| POST | `/processes/{pid}/extract` | ba | M2 | re-run extraction for all/selected sources |
| GET | `/processes/{pid}/gaps?status=&severity=` | viewer | M5 | sorted by priority |
| POST | `/gaps/{id}/dismiss` · `/waive` | owner | M5 | reason required |
| POST | `/processes/{pid}/gaps/scan` | ba | M5 | manual rescan |
| GET/POST/PUT | `/smes`, `/smes/{id}` | admin | M6 | |
| POST | `/gaps/{id}/route` | ba | M6 | override SME |
| GET | `/processes/{pid}/questions` | ba | M6 | |
| GET | `/portal/questions` | sme | M6 | own questions only |
| POST | `/questions/{id}/answer` | sme, ba | M6 | `{text, structured_value?}` |
| POST | `/processes/{pid}/interviews` · WS `/interviews/{id}` | ba, sme | M6 | live mode |
| GET | `/processes/{pid}/stories` · `/stories.md` · `/features` | viewer | M7 | rendered at latest version |
| GET | `/processes/{pid}/dor` | viewer | M8 | |
| GET | `/processes/{pid}/diagram?format=drawio\|mermaid` | viewer | M10 | Lucidchart-importable `.drawio` or Mermaid |
| GET | `/processes/{pid}/hitl` | viewer | M10 | human touchpoints summary |
| GET | `/elements/{pid}/{element_id}/confidence` | viewer | M8 | explain breakdown |
| POST | `/stories/{id}/signoff` · `/waivers` | owner | M8 | |
| POST | `/processes/{pid}/exports` | owner | M9 | |
| GET | `/exports/{id}` · `/exports/{id}/download` | owner, system:mother | M9 | |
| POST | `/exports/{id}/mother-ack` | system:mother | M9 | |
| WS | `/processes/{pid}/events` | viewer | all | pushes `ir.patched`, `gaps.updated`, `dor.evaluated` |

## 2. Representative payloads

`POST /processes/{pid}/patches` → `201`:
```json
{ "patch_id": "0192…", "status": "applied", "to_version": 4, "changed_paths": ["/nodes/node_high_risk_approval"] }
```
`409`:
```json
{ "type": "/problems/patch-conflict", "title": "Patch conflicts with newer changes",
  "base_version": 3, "current_version": 5, "conflicting_paths": ["/nodes/node_risk_decision"] }
```

`POST /questions/{id}/answer` → `202`:
```json
{ "question_id": "q_01", "status": "answered", "patch_id": "0192…", "patch_status": "proposed",
  "summary": "High-risk approval is performed by the MLRO, with Engagement Partner informed." }
```

## 3. Event envelope
```json
{ "event_id": "uuid", "type": "ir.patched", "process_id": "proc_client_onboarding", "ir_version": 4,
  "occurred_at": "2026-10-02T12:00:00Z", "correlation_id": "uuid", "payload": { } }
```
Types and payloads: see `01-architecture.md §8`.

## 4. LLM Gateway (S1) internal interface
```python
async def complete_json(
    prompt: str,                  # file name without extension, e.g. "extract_process" -> prompts/extract_process.md
    variables: dict,
    output_model: type[BaseModel],
    correlation_id: str | None = None,
) -> tuple[BaseModel, LLMCallRecord]  # record includes prompt_file, prompt_sha256, model, tokens, latency
```
Prompt loading: all files in `prompts/` are parsed and validated at startup (front matter, `name` = file name,
`output_model` exists, template compiles). `_preamble.md` is prepended. Variables are checked against the front
matter list, and rendering uses Jinja2 `StrictUndefined`. Model = front-matter `model` if set, else `RS_LLM_MODEL`.
Full rules: `prompts/README.md`.

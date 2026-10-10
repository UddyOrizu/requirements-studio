# 03 — API & Event Contracts

Base path `/api/v1`. JSON. Auth: bearer token, either a session token from `/auth/login` or (with `RS_SSO=entra`) an
Entra ID access token mapped onto the internal user. Roles: `user` and `admin`. In the table, **user** means any
signed-in person, **owner** the owner of the idea or process (an admin may always act as owner), **assignee** the
person an approval request was sent to, and **admin** administrators only. Services such as MOTHER use app-only Entra
tokens with an app role (`system:mother`). All mutating endpoints accept `Idempotency-Key`. Errors: RFC 7807
problem+json.

## 1. Endpoints

| Method | Path | Role | Module | Notes |
|---|---|---|---|---|
| GET | `/auth/config` | public | S3 | `{password, sso, dev_sign_in}`: how the web app signs in |
| POST | `/auth/login` `{email, password}` · `/auth/token` (form) | public | S3 | session token + user; 401 problem on failure (same message whether or not the account exists) |
| POST | `/auth/password/forgot {email}` · GET `/auth/password/link?token=` · POST `/auth/password/set {token, password}` | public | S3 | reset / invitation links; `set` signs in |
| GET | `/me` · POST `/me/password {current_password, new_password}` | user | S3 | a password change signs out other sessions |
| GET | `/users` | user | S3 | people directory for pickers (not disabled) |
| GET/POST | `/admin/users` · GET/PATCH `/admin/users/{id}` `{name?, role?, status?}` | admin | S3 | create = invite by email; 409 `/problems/last-admin`, `/problems/cannot-disable-self` |
| POST | `/admin/users/{id}/invite` · `/admin/users/{id}/password-reset` | admin | S3 | emails a link |
| POST | `/approvals {kind, assignee_user_id, subject_id, idea_id?, message?}` | owner | Approvals | kind `patch_review` (patch id), `story_signoff` (session id), `suggestion` (S0x + idea_id); questions come from "ask someone" |
| GET | `/approvals?box=inbox\|sent\|all&status=&idea_id=` · `/approvals/summary` · `/approvals/{id}` | user | Approvals | detail includes the subject as it is now |
| POST | `/approvals/{id}/decision {decision: approve\|reject\|answer, note?}` | assignee | Approvals | runs the owning service; note required to reject and as the answer |
| POST | `/approvals/{id}/cancel` | requester, admin | Approvals | |
| GET | `/ideas?status=&owner=&q=` | user | M12 | Ideas list with stats |
| POST | `/ideas` | user | M12/M0 | `{text, has_process_today, files?}` → idea + session + first question |
| GET | `/ideas/{id}` · `/ideas/{id}/flow?variant=&format=` · `/ideas/{id}/flow/compare` | user | M12/M10 | detail, flows, as-is vs to-be |
| POST | `/ideas/{id}/suggestions:generate` · GET `/ideas/{id}/suggestions` | owner | M11 | |
| POST | `/suggestions/{sid}/accept` · `/reject {reason}` · `/edit {instruction}` | owner | M11 | accept = patch on the to-be |
| POST | `/stories/{sid}/refine {instruction}` → preview · POST `/stories/{sid}/refine/{pid}/apply` · GET `/stories/{sid}/history` | owner | M12 | |
| GET | `/ideas/{id}/exports/formats` · POST `/ideas/{id}/exports {formats}` · GET `/exports/{id}/download` | user | M9 | Lucidchart, Markdown, Gherkin, Jira, ADO, xlsx, CSV |
| POST | `/intake-sessions` | user | M0 | `{idea_text, title?, files?}` → process + session + first question |
| GET | `/intake-sessions/{id}` | owner | M0 | phase, coverage, timeline |
| POST | `/intake-sessions/{id}/answers` | owner | M0 | `{text?, choice?, special?, ask_user_id?, ask_sme_id?}` → captured + next question; "ask someone" emails the user |
| POST | `/intake-sessions/{id}/turns/{n}/undo` | owner | M0 | inverse patch |
| POST | `/intake-sessions/{id}/jump` | owner | M0 | `{phase: "validate"}` |
| WS | `/intake-sessions/{id}/stream` | owner | M0 | streamed questions, captured cards, SME answers |
| POST | `/processes` | owner | M3 | `{name, domain, owner_user_id, description}` → IR v0 |
| GET | `/processes` · `/processes/{pid}` | user | M3 | includes readiness summary |
| GET | `/processes/{pid}/ir?version=` | user | M3 | latest by default |
| GET | `/processes/{pid}/ir/diff?from=&to=` | user | M3 | JSON Patch |
| POST | `/processes/{pid}/patches?reviewer=` | owner, agent | M3 | body = patch envelope; a proposed patch is sent for review to `reviewer` (default the owner) |
| POST | `/patches/{id}/accept` · `/reject` | owner | M3 | reject requires `reason`; closes pending review requests |
| POST | `/processes/{pid}/sources` | owner | M1 | multipart |
| GET | `/processes/{pid}/sources` · `/sources/{sid}` · `/sources/{sid}/blocks` | user | M1 | |
| DELETE | `/sources/{sid}` | owner | M1 | soft delete + re-reconcile |
| POST | `/processes/{pid}/extract` | owner | M2 | re-run extraction for all/selected sources |
| GET | `/processes/{pid}/gaps?status=&severity=` | user | M5 | sorted by priority |
| POST | `/gaps/{id}/dismiss` · `/waive` | owner | M5 | reason required |
| POST | `/processes/{pid}/gaps/scan` | owner | M5 | manual rescan |
| GET/POST/PUT | `/smes`, `/smes/{id}` | admin | M6 | |
| POST | `/gaps/{id}/route` | owner | M6 | override SME |
| GET | `/processes/{pid}/questions` | owner | M6 | |
| GET | `/portal/questions` | assignee | M6 | own questions only |
| POST | `/questions/{id}/answer` | assignee, owner | M6 | `{text, structured_value?}` |
| POST | `/processes/{pid}/interviews` · WS `/interviews/{id}` | owner, assignee | M6 | live mode |
| GET | `/processes/{pid}/stories` · `/stories.md` · `/features` | user | M7 | rendered at latest version |
| GET | `/processes/{pid}/dor` | user | M8 | |
| GET | `/processes/{pid}/diagram?format=drawio\|mermaid` | user | M10 | Lucidchart-importable `.drawio` or Mermaid |
| GET | `/processes/{pid}/hitl` | user | M10 | human touchpoints summary |
| GET | `/elements/{pid}/{element_id}/confidence` | user | M8 | explain breakdown |
| POST | `/stories/{id}/signoff` · `/waivers` | owner | M8 | |
| POST | `/processes/{pid}/exports` | owner | M9 | |
| GET | `/exports/{id}` · `/exports/{id}/download` | owner, system:mother | M9 | |
| POST | `/exports/{id}/mother-ack` | system:mother | M9 | |
| WS | `/processes/{pid}/events` | user | all | pushes `ir.patched`, `gaps.updated`, `dor.evaluated` |

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

# Requirements Studio — Design & Implementation Specification

**Status:** v1.1 build spec (adds idea-first discovery + detailed stories) · **Owner:** Udo · **Consumer:** Claude Code (implementation) and the MOTHER team (downstream)
**Date:** 2026-10-03

Requirements Studio turns the months-long requirements phase into days. **Start from just an idea**: the
discovery interview (M0) asks one well-chosen follow-up question at a time until the idea is a complete process
with detailed, ready user stories. Or start from documents: it ingests what already exists
(SOPs, process docs, emails, meeting transcripts, later screen recordings), drafts the business process as a
diagram, lets people **correct** rather than write, asks targeted questions only where the model is uncertain,
routes each question to the right SME, and produces two synchronised outputs:

**A conversational requirements and discovery tool.** New idea → a conversation about the idea, or about today's process if
one exists → AI suggests where agents can help → **process flow + detailed user stories** → refine → export. Ideas are
listed and each opens to its flow and stories.

**Main outputs** (all rendered from the IR):

| Output | Audience | Format |
|---|---|---|
| **Detailed user stories** with Given/When/Then acceptance criteria | Business, BA, QA, delivery | Markdown + `.feature`; **Jira CSV, Azure DevOps CSV, Excel/CSV** |
| **Process flows** (as-is and to-be) marking automated steps, human-in-the-loop reviews, approval gates and human queues | Process owners, risk, architects | **`.drawio`** (import into Lucidchart as editable shapes) + Mermaid `.mmd` |
| **Improvements report**: AI suggestions, decisions, hours saved | Sponsors, process owners | Markdown + Excel sheet |
| Process IR (machine view, the source of truth) | MOTHER | JSON validated by `schemas/process-ir.schema.json` |

Stories are never edited as prose and parsed back. All change goes through the IR.

---

## How to use this pack (Claude Code)

1. Read `CLAUDE.md` first — it holds the non-negotiable build rules.
2. Read `docs/00-overview.md` → `docs/01-architecture.md` → `docs/02-ir-specification.md`.
3. Build in the order given in `docs/05-implementation-plan.md`. Each phase lists the module specs it needs and
   its exit tests.
4. Use `samples/` as fixtures. Two worked examples:
   - **Client KYC** (`samples/client_kyc/`), the main example: a one-paragraph idea. The requester says a process exists today,
     so the conversation captures the as-is (17 turns). The AI then suggests 7 improvements (6 accepted, 1 rejected, ~275 analyst
     hours a month), and the result is a to-be with 9 ready stories, as-is and to-be flows, one story refinement, and Jira, Azure DevOps,
     Excel and CSV exports. Every patch and decision is in `intake_session_kyc.json`; `conversation_kyc.md` is the readable version.
   - **Document-led** (`samples/*.json`): client onboarding/KYC from an SOP, a transcript and an email, mid-review,
     with conflicts, gaps and stories that aren't ready yet.
5. `tools/rs_reference.py` is the reference implementation (test oracle) of confidence, coverage, next-question
   selection, story derivation and DoR. `python tools/validate_samples.py` replays the idea-first session from an
   empty IR and checks every fixture against the schemas and the oracle.

## File map

```
README.md                       this file
CLAUDE.md                       build rules for Claude Code
docs/
  00-overview.md                what the product is, user journeys, outputs, goals, glossary
  01-architecture.md            module map, data flow, sequences, stack, repo layout, events
  02-ir-specification.md        the Process IR (as-is / to-be), element metadata, patch model, confidence model
  03-api.md                     REST + event contracts
  04-data-model.md              Postgres tables
  05-implementation-plan.md     phased build plan with exit criteria
  06-nfr-security.md            security, confidentiality, audit, performance
  modules/
    M0-idea-intake-discovery.md   ← the conversation (idea mode / as-is mode)
    M11-as-is-improvement.md      ← AI suggests where agents help; accept/reject each
    M12-ideas-workspace-and-refinement.md  ← ideas list, idea detail, story refinement
    M7-story-renderer.md          detailed user stories
    M10-process-flow-diagram.md   Lucidchart-ready flows with HITL + approval gates
    M9-exports.md                 Lucidchart, Markdown, Gherkin, Jira, Azure DevOps, Excel/CSV, MOTHER
    M1-source-ingestion.md        (supporting) document upload
    M2-extraction-reconciliation.md
    M3-ir-store-patch-service.md
    M4-process-canvas-ui.md
    M5-gap-detector.md
    M6-interviewer-sme-routing.md
    M8-confidence-dor.md
schemas/
  process-ir.schema.json        THE contract
  idea.schema.json              an idea (top-level object in the Ideas list)
  suggestion.schema.json        an M11 improvement suggestion
  intake-session.schema.json    the conversation timeline (incl. fork, suggestions, refinements)
  patch.schema.json · gap.schema.json · question.schema.json
prompts/
  README.md                     how prompts are loaded (by file name), file format, gateway rules
  *.md                          one file per prompt, e.g. intake_interpret.md, improve_suggest.md, story_refine.md
samples/
  ideas_index.json              the Ideas list: both sample ideas with stats
  client_kyc/                   ★ main worked example: as-is conversation → AI improvements → to-be → stories → exports
    idea.md                     the only input: one paragraph
    idea_client_kyc.json        the idea record
    intake_session_kyc.json     full timeline: 17 as-is turns, fork, 7 suggestions + decisions, deepen/validate, 1 story refinement
    conversation_kyc.md         the same conversation as a readable transcript
    ir_v0_empty.json            starting IR (as-is)
    ir_client_kyc_as_is.json    today's process (confirmed)
    ir_client_kyc_to_be.json    improved process with stories (status ready)
    suggestions_client_kyc.json 7 suggestions: 6 accepted, 1 rejected, evidence + benefit + ops
    gaps_client_kyc.json · dor_report_kyc.json
    stories_client_kyc.md       9 detailed to-be stories, all ready, with "what changes from today"
    features/client_kyc.feature
    flow/as_is_process_flow.drawio|.mmd   today: all manual, minutes + pain points
    flow/to_be_process_flow.drawio|.mmd   improved: automated steps, human review, 2 approval gates, 3 human queues
    exports/                    jira_import.csv · azure_devops_import.csv · stories_backlog.csv · stories_backlog.xlsx · improvements.md
  (document-led example, supporting path)
  sources/                      raw inputs (SOP, transcript, email thread)
  ir_client_onboarding.json     as-is IR after extraction + first corrections (deliberately has gaps)
  gaps_client_onboarding.json · questions_outbox.json · patch_example.json · dor_report.json · sme_directory.json
  stories_client_onboarding.md · features/client_onboarding.feature
  flow/as_is_process_flow.drawio|.mmd   onboarding flow (controls not yet set, shown dashed)
  export/manifest.yaml          MOTHER package manifest
tools/
  rs_reference.py               reference implementation / test oracle (confidence, coverage, stories, DoR)
  render_flow.py                reference diagram renderer: python tools/render_flow.py <ir.json> <out_dir>
  render_exports.py             reference export renderer: python tools/render_exports.py <to_be.json> <out_dir> [as_is.json suggestions.json]
  validate_samples.py           schema, integrity, replay, suggestion, flow and export checks
```

## Local development

Requires Python 3.12, [uv](https://docs.astral.sh/uv/) and Docker.

```bash
uv sync                                   # install dependencies (incl. dev tools)
cp .env.example .env
docker compose up -d                      # Postgres 16 + pgvector, Redis, Azurite (Azure Blob), Mailpit (email)
uv run alembic upgrade head               # create the schema (docs/04)
uv run uvicorn apps.api.main:app --factory --reload   # API on :8000, docs at /docs
uv run arq apps.worker.main.WorkerSettings            # worker
```

If a port is taken, move it: `RS_PG_PORT=5434 docker compose up -d` and set `RS_DATABASE_URL` to match
(`RS_REDIS_PORT`, `RS_AZURITE_PORT`, `RS_MAILPIT_SMTP_PORT` and `RS_MAILPIT_UI_PORT` work the same way).

**Sign-in in dev.** Accounts are internal (see "Users and sign-in" below). `POST /dev/seed` creates the sample users
(password `requirements-studio-dev`), and the sign-in page offers a "sign in as" picker while `RS_ENV` is `dev` or
`test` (never in prod). For curl, `POST /dev/token` gives a session token for any active user:

```bash
curl -s -X POST localhost:8000/dev/seed -H 'Content-Type: application/json' -d '{"scenario": "samples"}'
TOKEN=$(curl -s -X POST localhost:8000/dev/token -d username=user_sarah_lin | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/me
```

Email (invitations, password resets, approval requests) goes to Mailpit: open http://localhost:8025.

**Checks** (CI runs the same):

```bash
uv run ruff check .
uv run python tools/validate_samples.py
RS_DATABASE_URL=postgresql+asyncpg://rs:rs@localhost:5432/rs uv run pytest   # DB tests skip without RS_DATABASE_URL
```

DB tests create and drop their own `rs_test_*` database. The application's DB login should be granted the `rs_app`
role, which cannot UPDATE, DELETE or TRUNCATE `audit_log`; a trigger also blocks those for every role.

## Users and sign-in

Requirements Studio keeps its own user list. There are two roles: **user** and **admin**. Admins add people (who get
an email invitation), change roles, disable and re-enable accounts, and send password resets, on the **Users** page.
Everything else is decided per record: you own the ideas you start, and an admin can act on any idea. Users are never
deleted (audit entries and ownership keep pointing at them); disabling one signs them out everywhere at once.

**The first admin.** On a new database:

```bash
uv run python tools/create_admin.py --email you@example.com --name "Your Name"
```

It prints a link to choose a password (and emails it). Run it again to make an existing user an admin.

**Passwords.** Argon2id hashes; at least 12 characters; five failed attempts pause sign-in for 15 minutes. Invitation
links last 7 days, reset links an hour, and each works once. Sessions are tokens signed with `RS_SESSION_SECRET`
(required in prod: 32+ random characters, e.g. `openssl rand -base64 48`) and last `RS_SESSION_TTL_MINUTES` (480).

**Email.** Messages are queued in `email_outbox` with the change they announce and sent over SMTP (`RS_SMTP_*`,
`RS_EMAIL_FROM`) by the API process, or by the worker with `RS_EMAIL_SENDER=worker`; failures are retried with
back-off. Office 365 (`smtp.office365.com:587`, `starttls`), SendGrid, Mailgun or any relay works. Links in emails
point at `RS_WEB_BASE_URL`.

## Approvals

Instead of deciding something yourself, you can send it to a colleague. They get an email with a link and decide in
the app (**Approvals** in the top bar); you get an email with the outcome.

| What | Where | Their choice |
|---|---|---|
| A proposed change (a patch awaiting review) | sent to the process owner automatically, or `?reviewer=<user>` | approve (the patch applies) or reject with a note |
| Story sign-off | Conversation, at sign-off: "Ask someone else to sign off" | sign off (recorded as theirs) or ask for changes |
| An improvement suggestion | Improvements: "Ask someone to decide" | accept (applied to the to-be) or reject with a reason |
| A question | Conversation "Not sure — ask", or a story's "Ask someone" | answer; it shows in the conversation |

Decisions run through the owning service exactly as if the owner had made them, so the IR still changes only through
patches. If the owner decides directly, or the request was sent to several people and one decides, the others close.
A sign-off is refused if the stories changed after the request.

## Microsoft Entra ID SSO (optional)

Set `RS_SSO=entra` to add "Sign in with Microsoft". Only people an admin has added can sign in: the first time, the
Microsoft account is matched to the user by email and linked by its object id (`oid`); roles always come from
Requirements Studio, not from Entra. Keep `RS_PASSWORD_SIGN_IN=true` to offer both, or set it to `false` for SSO
only (invitations then say "sign in with Microsoft"). Create two app registrations in the tenant:

1. **API** (`RS_ENTRA_API_CLIENT_ID`)
   - *Expose an API*: Application ID URI `api://<client id>`, scope `access_as_user` (admins and users can consent).
   - *App roles*: only for services, e.g. `system.mother` (allowed member type: applications).
   - *Manifest*: `"accessTokenAcceptedVersion": 2` (the API refuses v1.0 tokens and says so).
2. **Web app** (`RS_ENTRA_SPA_CLIENT_ID`)
   - Platform *Single-page application*, redirect URI = the web origin with a trailing slash (e.g. `https://rs.example.com/`).
   - *API permissions*: the API's `access_as_user` (delegated); grant admin consent.

Then set `RS_ENTRA_TENANT_ID` as well. The web app reads these from `GET /auth/config` at runtime, so one build serves
every environment. MOTHER can call the API with a client-credentials token carrying the `system.mother` app role.

## Azure Blob Storage

`RS_OBJECT_STORE=azure_blob` keeps export packages in the `RS_AZURE_BLOB_CONTAINER_EXPORTS` container (created on
first use). In Azure, set `RS_AZURE_STORAGE_ACCOUNT_URL` and give the app's managed identity the *Storage Blob Data
Contributor* role on the account; connection strings are refused in prod. Locally, Azurite (in `docker-compose.yml`)
and the connection string in `.env.example` stand in for it.

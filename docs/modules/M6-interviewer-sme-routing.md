# M6 — AI Interviewer & SME Routing

## Purpose
Turn open gaps into the **fewest, best-targeted questions**, send them to the **right person** through the
channel they already use, and turn answers into reviewable IR patches. Two modes:

- **Async** (default): batched questions via Teams / email / SME portal.
- **Live interview**: a chat session (BA + SME, or SME alone) that walks the gap list conversationally and emits
  patches in real time.

## 0. Who answers first

| Situation | Default answerer | SMEs involved when |
|---|---|---|
| **Active intake session** (idea-first, M0) | the **requester**, in the conversation | the requester picks *Not sure — ask someone* (they may name the person; else §2 scoring). Question `origin = intake_ask_someone`. |
| **Document-led process**, gap is about how the work is done (structural, conflict, semantic) | SME chosen by §2 scoring | always |
| **Document-led process**, gap is `coverage_missing` or `story_*` | **process owner** | the owner forwards it, or answers *ask someone* |

SME answers to intake questions come back as *Captured from <SME>* cards in the requester's session, as
`proposed` patches the requester accepts (or the BA, if the requester is away).

## 1. SME directory (`smes`)

```json
{ "sme_id": "sme_priya_shah", "name": "Priya Shah", "email": "...", "role_title": "MLRO",
  "actor_ids": ["act_mlro"], "topic_tags": ["aml", "risk_rating", "high_risk_approval", "pep"],
  "process_ids_owned": [], "channels": ["teams", "email"], "max_open_questions": 5,
  "working_hours": {"tz": "Europe/London", "days": "Mon-Fri", "start": "09:00", "end": "17:30"},
  "out_of_office_until": null, "delegate_sme_id": "sme_tom_reed" }
```
Populated by admin import (CSV / Entra ID groups) plus `actor_ids` linking: when an SME confirms they perform an
actor's role, the link is saved. Topic tags get an embedding for semantic matching.

## 2. Routing

For gap `g` and each eligible SME `s` (not OOO, under `max_open_questions`; else use delegate):

```
actor_match  = 1.0 if s.actor_ids ∩ g.routing.candidate_actor_ids else 0
topic_match  = cosine(embed(g.routing.topic_tags + g.title), embed(s.topic_tags))
ownership    = 1.0 if g.process_id ∈ s.process_ids_owned else 0
load_penalty = open_questions(s) / s.max_open_questions
history      = answer_rate(s, last 90d)               # 0..1, default 0.7

score = 0.40·actor_match + 0.30·topic_match + 0.10·ownership + 0.10·history − 0.10·load_penalty
```

- Pick the top SME if `score ≥ 0.45`; else route to the **process owner** with a note "no clear SME".
- For `conflicting_sources` gaps, prefer the SME linked to the actor *in dispute* on either side; if both sides
  name different actors, ask the higher-authority one (owner can configure) and CC the other.
- BA can override routing before send.

## 3. Question generation and batching

- Gap → question text via `prompts/interview_phrase.md` (or the gap's drafted question if detector already produced one).
  Rules: one question per gap, ≤ 40 words, plain English, include a short context snippet, offer
  `suggested_answers` (2–4) plus "Other". Never include PII beyond what the SME already has access to.
- **Batching**: queue per SME; flush when (a) a blocking gap is queued, or (b) every 4 working hours, or (c) 5
  questions queued. Ordered by priority. Max 5 per batch.
- **Merge**: gaps with the same target and SME are merged into one question with multiple sub-answers.

## 4. Delivery and chasing

| Event | Action |
|---|---|
| send | Teams adaptive card / email with deep link to SME portal; status `sent`; `due_at = sent + 2 working days` |
| +2 working days, unanswered | reminder (`reminded`) |
| +4 working days | escalate to process owner + suggest alternate SME (`escalated`) |
| owner reassigns | new question for new SME; old `expired` |

Teams card answers with suggested options post directly back (`POST /questions/{id}/answer`).

## 5. Answer interpretation

`prompts/interview_interpret.md` receives: the gap, target element(s) JSON, the question, the answer, allowed patch
paths (derived from `target_refs` + creation of new SLA/exception/AC/edge elements). It returns:

```json
{ "ops": [ ... RFC 6902 ... ],
  "interpretation_confidence": 0.0,
  "follow_up_question": null | "string",
  "summary": "Human-readable change summary" }
```

Validation:
- Ops paths must be within the allowed set; others are stripped and confidence capped at 0.5.
- The resulting IR must validate (dry-run through M3 validators).
- Add confirmation ops: touched elements → `meta.status=confirmed`, `meta.confirmed_by=<sme_id>`, plus a
  `supports` provenance ref with `source_id = src_answer_<question_id>` (a source of kind `interview_answer` is
  created for each answered question; locator `message`, excerpt = the answer text, truncated).
- If `follow_up_question` is present or confidence < 0.6 → the gap stays `answered`, a follow-up is queued to the
  same SME, and the patch (if any) is still `proposed`.

## 6. Auto-accept policy (per process; default off)
Auto-apply an answer patch only if **all** hold: answerer is the routed SME; `interpretation_confidence ≥ 0.85`;
ops are only `add` or `replace` (no `remove`); no op changes an element already `confirmed` by someone else.
Otherwise → `proposed` for owner/BA review.

## 7. Live interview mode
- Session = `{process_id, participants, gap_ids (ordered), transcript}`.
- The agent (`prompts/interview_live.md`) asks one gap at a time, may ask one clarification, then shows the interpreted
  change as a **preview card**; SME/BA clicks Confirm → patch submitted. The session transcript is also ingested
  as a `transcript` source afterwards, so evidence is preserved.
- The agent must not invent new topics; it may raise a *new gap* (via `prompts/gaps_semantic.md` on the touched region)
  if the answer reveals one.

## API
- `GET/POST /smes`, `PUT /smes/{id}`
- `GET /processes/{pid}/questions?status=` · `POST /gaps/{id}/route` (override) · `POST /questions/{id}/send`
- `GET /portal/questions` (SME's own) · `POST /questions/{id}/answer`
- `POST /processes/{pid}/interviews` · WebSocket `/interviews/{id}`

## Acceptance tests (fixtures: `samples/gaps_client_onboarding.json`, `samples/sme_directory.json`,
`samples/questions_outbox.json`)
- **AC-M6-1** Routing the sample gaps yields the SME assignments in `questions_outbox.json`
  (conflict on high-risk approval → Priya Shah, MLRO; docs timeout → Daniel Okafor, onboarding lead).
- **AC-M6-2** Two gaps on the same SME are batched into one delivery; blocking gap triggers immediate flush.
- **AC-M6-3** The MLRO's answer in `questions_outbox.json` interprets to ops equivalent to
  `samples/patch_example.json` (order-insensitive), with `interpretation_confidence ≥ 0.85`.
- **AC-M6-4** An interpreted op outside the allowed path set is stripped and confidence capped at 0.5.
- **AC-M6-5** Unanswered question is reminded at +2 working days and escalated at +4 (use a frozen clock; skip
  weekends).

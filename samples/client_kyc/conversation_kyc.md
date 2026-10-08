# Client KYC: discovery and improvement conversation (readable transcript)

_Rendered from `intake_session_kyc.json`. Requester: Sarah Lin, Compliance Manager. She answered **yes** to "Is there a process today?", so the interview captures today's process first, then the AI suggests improvements she accepts or rejects one by one. Each 'Captured' list is the plain-English view of that step's change to the process model._

#### T0 · Idea
**🧑 Sarah:** Client KYC checks take us days because the onboarding team gathers ID documents by email, checks them by hand and runs screening separately. I want something that collects the KYC documents from new clients, verifies the IDs, runs the sanctions and PEP screening and gives a risk rating, so we only look at the cases that need a human.

Captured:
- Mode: a process exists today, so I'll capture how it works now first
- Goal: cut the time it takes to complete KYC for a new client
- Roles: Onboarding Analyst; Client
- Today's steps: Request KYC documents (by email) · Verify identity documents (by hand) · Screen client and owners (separately) · Assign risk rating
- Pain points noted: email, manual ID checks, separate screening
- _I assumed:_ KYC means 'know your client' checks on the client and its owners

_Coverage 8%_

#### T1 · slot C04 · Trigger
**🤖** Today, what has to happen before KYC starts for a new client?
<sub>Why: I need the trigger so the workflow knows when to start.</sub>

Options: `Client record created in the CRM` · `Engagement letter signed` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** The engagement team accepts the client and creates the client record in the CRM. That's when KYC starts, and the first step is asking the client for their documents.

Captured:
- Start: client record created in the CRM
- First step: Request KYC documents
- Data: Client (CRM id, legal name)

_Coverage 14%_

#### T2 · slot C05 · Outcome
**🤖** How do you know KYC is finished for a client?
<sub>Why: This defines the end points, and what 'done' means.</sub>

Options: `Outcome recorded on the client file` · `Client approved by compliance` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** When the checks are done and the risk rating is signed off where needed, the outcome is recorded on the client file. Or we decline the client if the risk is too high.

Captured:
- End: KYC complete (outcome recorded on the client file)
- End: client declined
- New steps: Record KYC outcome · Decline client

_Coverage 21%_

#### T3 · slot C02 · Success metric
**🤖** How would you measure success, and what does it look like today?
<sub>Why: A baseline and a target let us prove the change worked.</sub>

Options: `Working days to complete KYC` · `Share of cases an analyst has to touch` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** KYC takes about 8 working days per client today and I want it under 3. Analysts also review every case by hand; I'd like them to touch no more than 30% of cases.

Captured:
- Metric: KYC elapsed time, 8 → 3 working days
- New goal: focus analyst time on cases that need a human (100% → 30% touched)

_Coverage 27%_

#### T4 · slot C06 · Main steps
**🤖** Here's how it works today as I understand it: client record created → request documents → verify IDs → screen → risk rating → record the outcome, or decline. What's missing or in the wrong order?
<sub>Why: The main path is the backbone everything else hangs off.</sub>

Options: `That's right` · `Something's missing` · `The order is wrong` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** We email the client a checklist and wait for the documents, and they often send them late. After the risk rating, low risk goes straight to recording, medium risk needs an analyst to review it, and high risk needs the MLRO.

Captured:
- New wait: Await client documents (clients are often late)
- Decision after the rating: low → record; medium → analyst; high → MLRO
- New steps: Analyst approval of medium-risk client · MLRO approval of high-risk client
- Data: KYC documents
- _I assumed:_ Verification, screening and rating follow in that order once documents arrive
- _I assumed:_ After approval the outcome is recorded; the MLRO can also decline

_Coverage 37%_

#### T5 · slot C07 · Who does what
**🤖** Who does each step today?
<sub>Why: Each story needs a role, and it shows where people spend time today.</sub>

Options: `The onboarding analyst does most of it` · `Split between onboarding and compliance` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** The onboarding analyst does everything up to the risk rating and records the outcome. The MLRO approves high-risk clients, and the engagement manager tells the client if we decline.

Captured:
- Onboarding Analyst: request, verify, screen, rate, approve medium risk, record
- MLRO: approves high-risk clients
- Engagement Manager: tells the client if declined

_Coverage 43%_

#### T6 · slot C08 · Decisions
**🤖** How does the analyst decide the risk rating today?
<sub>Why: An explicit rule can be automated and tested instead of left to judgement.</sub>

Options: `Sanctions match → high` · `PEP → high` · `Adverse media → medium` · `High-risk country → medium` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** Any sanctions match or a PEP makes it high risk. Adverse media or a high-risk country makes it medium. Otherwise it's low.

Captured:
- Rule: sanctions match or PEP → high; adverse media or high-risk country → medium; otherwise low
- Data: Screening result; Client country risk
- 3 acceptance criteria (low / medium / high)

_Coverage 50%_

#### T7 · slot C13 · Timing
**🤖** What time limits apply today: how long does the client have to send documents, and how long should the checks take?
<sub>Why: Waiting needs a time limit, otherwise an automated workflow could wait forever.</sub>

Options: `5 working days for documents` · `Checks within 3 working days` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** The client has 5 working days to send their documents. After that the analyst chases by email, usually every 3 working days. The whole check should be done within 3 working days of receiving the documents, but it often isn't.

Captured:
- SLA: client sends documents within 5 working days; on breach → Chase missing documents
- Step: Chase missing documents (analyst, by email, every 3 working days)
- SLA: checks done within 3 working days of receiving documents (often missed)

_Coverage 56%_ · follow-up queued

#### T8 · follow-up to T7
**🤖** Do reminders carry on indefinitely, or is there a point where someone steps in?
<sub>Why: A chase needs a stop point, so real problems get a person's attention.</sub>

Options: `Escalate after N working days` · `Stop after N reminders` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** After 10 working days with no documents, the engagement manager is told and onboarding is put on hold.

Captured:
- Exception: no documents after 10 working days → Engagement Manager told, onboarding on hold

_Coverage 62%_

#### T9 · slot C10 · Data
**🤖** What do you record for each client's KYC?
<sub>Why: These fields become the evidence the workflow must keep.</sub>

Options: `Documents received` · `Screening results` · `Risk rating and reason` · `Who approved and when` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** The documents received, the screening results, the risk rating with the reason, who approved it and when.

Captured:
- Risk assessment: rating, reason, approved by, approved at
- KYC documents: received at

_Coverage 68%_

#### T10 · slot C11 · Systems
**🤖** Which systems are involved today: how do documents come in, and which tools are used for ID checks and screening?
<sub>Why: Integration points show what could be automated and what MOTHER would need tools for.</sub>

Options: `Email` · `Client portal` · `e-ID verification service` · `Screening tool` · `CRM` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** Documents come in by email and get saved to a shared drive. We have a client portal but don't use it for KYC yet. The analyst checks IDs on the e-ID verification website, searches each name in the screening tool and types the outcome into the CRM. I'm not sure whether the screening tool can be called automatically, so ask James in onboarding technology. _(Not sure, ask someone → James Patel (Head of Onboarding Technology))_

Captured:
- Systems today: email + shared drive (documents), e-ID website, screening tool (one name at a time), CRM (typed in)
- Client portal exists but isn't used for KYC
- Asked James Patel (Head of Onboarding Technology): can the screening tool be called automatically?

_Coverage 72%_

#### T11 · slot C12 · Volume
**🤖** Roughly how many new clients go through KYC, and are there busy periods?
<sub>Why: Volume turns minutes saved into hours saved.</sub>

**🧑 Sarah:** About 150 new clients a month, with roughly double that in April and May.

Captured:
- Volume: ~150 new clients a month; about double in April and May

_Coverage 76%_

#### T12 · slot C14 · Security & audit
**🤖** Are there rules about who can see KYC data, or what must be kept as evidence?
<sub>Why: Security and audit rules become non-functional criteria.</sub>

Options: `Restricted to onboarding and compliance` · `Keep evidence for 5 years` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** KYC documents are personal data, so only onboarding and compliance can see them. Every check, result and approval has to be kept as evidence for 5 years after the relationship ends.

Captured:
- Security: documents visible only to onboarding and compliance
- Audit: evidence kept 5 years after the relationship ends

_Coverage 81%_

#### T13 · slot C15 · Scope
**🤖** What should a new solution not do, at least in the first version?
<sub>Why: Scope tells the improvement step and MOTHER where automation must stop.</sub>

**🧑 Sarah:** It shouldn't make the final call on high-risk clients. That stays with the MLRO. Periodic KYC refreshes for existing clients can come later, and individuals as clients are out of scope for now.

Captured:
- Out: final call on high-risk clients (MLRO); periodic refresh (later); individuals
- In: KYC for new corporate clients

_Coverage 85%_

#### T14 · slot C03 · Beneficiaries
**🤖** Who would benefit from improving this?
<sub>Why: Beneficiaries shape each story's 'so that'.</sub>

**🧑 Sarah:** Analysts stop chasing and rekeying, the MLRO only sees the cases that matter, and clients get onboarded faster.

Captured:
- Beneficiaries: Onboarding Analyst (no chasing or rekeying), MLRO (only cases that matter), Client (faster onboarding)

_Coverage 89%_

#### T15 · slot C16 · Human controls today
**🤖** Which steps are done by hand today, and where does someone approve before the case moves on?
<sub>Why: Today's controls are the starting point for deciding where AI agents can help and where people must stay.</sub>

Options: `All done by hand` · `Some steps already automated` · `Approvals for medium and high risk` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** Everything is done by hand by the analyst today. Medium risk is approved by an analyst and high risk by the MLRO. Declining is always done by the engagement manager.

Captured:
- Today: every step done by hand by the Onboarding Analyst
- Approval gates: analyst (medium risk), MLRO (high risk)
- Human task: Engagement Manager declines clients
- _I assumed:_ An analyst who rejects a medium-risk client escalates it to the MLRO
- _I assumed:_ Approval criteria: medium = reason understood and acceptable; high = risk acceptable to the firm

_Coverage 94%_

#### T16 · slot C17 · Effort & pain points
**🤖** Where does the time go today? Roughly how many minutes does each step take an analyst per client?
<sub>Why: Effort per step lets me estimate what each improvement would save.</sub>

**🧑 Sarah:** Sending the checklist takes about 10 minutes and chasing about 30 minutes per client in emails. Checking IDs by hand takes about 20 minutes, screening about 25 because every director is searched separately, the rating takes 10, and typing it all into the CRM and filing takes another 15.

Captured:
- Effort today per client: request 10 min, chase 30, verify 20, screen 25, rate 10, record 15 (110 min in total)
- Pain: every director searched separately in screening

_Coverage 100%_

**📨 Answer from James Patel (Head of Onboarding Technology)** to `q_intake_01`
> Yes. The screening tool has an API for single and batch checks, and it returns possible matches with a match score.

Captured:
- Captured from James: the screening tool has an API for single and batch checks and returns a match score

**🤖 Playback**
> Today, when a client record is created in the CRM, the analyst emails a document checklist and waits up to 5 working days, chasing by email every 3 days; after 10 days the engagement manager is told. The analyst checks IDs by hand on the e-ID website, searches each name in the screening tool, applies the risk rule and types the outcome into the CRM. Medium risk needs an analyst's approval, high risk the MLRO's, and the engagement manager declines rejected clients. It takes about 110 analyst minutes and 8 working days per client.

#### T17 · confirm as-is
**🤖** That's how KYC works today. Is that right?
<sub>Why: I'll suggest improvements against this picture, so it needs to be accurate.</sub>

Options: `That's right` · `Change something` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** That's right.

Captured:
- As-is confirmed (60 elements)

_Coverage 100%_

---

### ▸ Phase: Discover → **Improve**

**⚙ Studio:** As-is confirmed and frozen. Created the to-be process as a copy to improve.

**🤖 Improvement suggestions**

- 7 improvement suggestions, about 275 analyst hours a month if all accepted
- Not suggested: any change to MLRO approval (out of scope: the final decision on high-risk clients stays with the MLRO)

| ID | Suggestion | Saves (min per client) | Human control |
|---|---|---|---|
| S01 | Send the document request through the client portal | 10 | None needed: the request uses an approved template. |
| S02 | Automate document reminders | 30 | Engagement Manager is still told after 10 working days (existing exception). |
| S03 | Verify IDs through the e-ID service API | 20 | Human queue: failed checks go to an Onboarding Analyst. |
| S04 | Screen automatically, analyst reviews possible matches | 25 | Human review: an Onboarding Analyst confirms or clears every possible match before the case moves on. |
| S05 | Apply the risk rating rule automatically | 10 | Approval gates for medium and high risk stay as they are. |
| S06 | Write the outcome to the CRM and file the evidence automatically | 15 | None needed: every write is logged as evidence. |
| S07 | Auto-approve medium risk when the only flag is the country | — | Weekly sample of auto-approved cases reviewed by an analyst. |

✅ **S01 accepted**: Send the document request through the client portal

✅ **S02 accepted**: Automate document reminders

✅ **S03 accepted**: Verify IDs through the e-ID service API

✅ **S04 accepted**: Screen automatically, analyst reviews possible matches

✅ **S05 accepted**: Apply the risk rating rule automatically

✅ **S06 accepted**: Write the outcome to the CRM and file the evidence automatically

✖ **S07 rejected**: Auto-approve medium risk when the only flag is the country. _"Medium-risk clients still need a person's judgement, even if the only flag is the country."_

---

### ▸ Phase: Improve → **Deepen**

**⚙ Studio (automatic)**
- Drafted 12 acceptance criteria (incl. edge cases) for the to-be steps
- Drafted an outcome for each step and linked steps to goals
- _Assumption:_ All drafted acceptance criteria, outcomes and goal links are my assumptions; you'll confirm them in Validate

#### T18 · gap `gap_kyc_sla_breach` · to-be
**🤖** If KYC isn't finished within 3 working days of the documents arriving, who should be told?
<sub>Why: A time limit without an action can't be monitored.</sub>

Options: `MLRO` · `Onboarding team lead` · `No one, report only` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** The MLRO should be told, so nothing high-risk sits waiting.

Captured:
- SLA breach: if checks take over 3 working days, the MLRO is notified

_Coverage 100%_

#### T19 · gap `gap_match_threshold` · to-be
**🤖** What match score counts as a possible match that an analyst must review?
<sub>Why: The threshold decides how many cases reach a person, which drives the 30% target.</sub>

Options: `80 and above` · `70 and above` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** Not sure, ask Priya. She sets the screening thresholds. _(Not sure, ask someone → Priya Shah (MLRO))_

Captured:
- Asked Priya Shah (MLRO): what match score needs analyst review? Parked as an open question on 'Screen client and owners'

_Coverage 100%_

---

### ▸ Phase: Deepen → **Validate**

#### T20 · gap `gap_story_priority` · to-be
**🤖** Here are the 9 draft stories for the improved process. Which are must-haves for the first release?
<sub>Why: Priority tells the delivery team and MOTHER what to build first.</sub>

Options: `Request KYC documents` · `Chase missing documents` · `Verify identity documents` · `Screen client and owners` · `Assign risk rating` · `Analyst approval of medium-risk client` · `MLRO approval of high-risk client` · `Record KYC outcome` · `Decline client` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** All must-haves except chasing, which is a should-have.

Captured:
- Must have: 8 stories
- Should have: Chase missing documents

_Coverage 100%_

#### T21 · refine story `story_record_kyc`
**🧑 Sarah:** Add what happens if the CRM is down: retry a few times, then put it in the analyst's queue.

Captured:
- Story 'Record KYC outcome' refined: new exception 'CRM unavailable' (retry 3 times, then analyst queue)
- New edge-case acceptance criterion: CRM outage retries, then goes to an analyst

**🤖 Playback**
> When a new client record is created, an agent sends the document request through the client portal and reminds the client every 3 working days; after 10 days the engagement manager is told. IDs are verified through the e-ID service (failures go to an analyst), the client and every director are screened in one batch (an analyst reviews possible matches), and the risk rule runs automatically. Low risk is recorded straight to the CRM; an analyst approves medium risk or escalates it; the MLRO approves or rejects high risk, and the engagement manager declines rejected clients. If the CRM is down, recording retries 3 times then goes to an analyst. Analyst effort drops from about 110 minutes per client to reviews and approvals only.

#### T22 · confirm to-be · to-be
**🤖** That's the improved process: 9 stories, 12 acceptance criteria I drafted as assumptions. Confirm, or tell me what to change.
<sub>Why: Confirming turns proposed (amber) items green and makes the stories ready.</sub>

Options: `Confirm all` · `Change something` · `Other…` · `Not sure — ask someone` · `Skip`

**🧑 Sarah:** Confirm all.

Captured:
- Confirmed 14 elements, including all assumptions

_Coverage 100%_

---

### ✅ Signed off

- Sarah Lin signed off 9 stories at to-be version 12

---

**Totals:** 30 requester inputs · 6/7 suggestions accepted · 2 questions to SMEs · 9 stories · 17 acceptance criteria · elapsed 1 day (≈ 45 min of requester time)

# User stories — Client KYC checks

_Rendered by M7 from the to-be process (v12), produced from a one-line idea: as-is interview, AI improvements, refinement (polish off). Do not edit — change the IR._

## Process context

**Goals**

- **Cut the time it takes to complete KYC for a new client** (`goal_faster_kyc`): KYC elapsed time per client: 8 → 3 working days · benefits: Client, Onboarding Analyst
- **Focus analyst time on the cases that need a human** (`goal_focus_analysts`): Cases needing manual review: 100 → 30 % · benefits: Onboarding Analyst, MLRO

**Scope**

- In: KYC for new corporate clients: documents, ID verification, screening, risk rating, approval and recording
- Out: The final decision on high-risk clients (stays with the MLRO)
- Out: Periodic KYC refresh for existing clients (later phase)
- Out: Individuals as clients
- Assumption: New clients in scope are companies

**Non-functional requirements**

- [volume] About 150 new clients a month, roughly double in April and May — ~150 clients/month; ~300/month in April–May (all steps) `nfr_volume`
- [security] KYC documents are visible only to onboarding and compliance (all steps) `nfr_access`
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends — Retention: relationship end + 5 years (all steps) `nfr_evidence`

**What changes from today**

_As-is vs to-be per step. Details and rejected suggestions: `exports/improvements.md`._

| Step | Today | Minutes today | To-be | Change |
|---|---|---|---|---|
| Request KYC documents | Human task | 10 | Automated | S01: automated |
| Verify identity documents | Human task | 20 | Automated | S03: automated |
| Screen client and owners | Human task | 25 | Automated + human review | S04: automated with review |
| Assign risk rating | Human task | 10 | Automated | S05: automated |
| Analyst approval of medium-risk client | Approval gate | — | Approval gate | Unchanged |
| MLRO approval of high-risk client | Approval gate | — | Approval gate | Unchanged |
| Record KYC outcome | Human task | 15 | Automated | S06: automated |
| Decline client | Human task | — | Human task | Unchanged |
| Chase missing documents | Human task | 30 | Automated | S02: automated |

**Human-in-the-loop and approval gates**

_Shown on the process flow diagram (`flow/to_be_process_flow.drawio` for Lucidchart import, `.mmd` for Mermaid; for a document-led as-is: `flow/as_is_process_flow.drawio`)._

| Step | Control | Who | When | Checks |
|---|---|---|---|---|
| Exception: No documents after 10 working days | Human queue (exception) | Engagement Manager | on exception | Onboarding is put on hold. |
| Exception: ID check failed | Human queue (exception) | Onboarding Analyst | on exception | An analyst checks the document before the case moves on. |
| Screen client and owners | Automated + human review | Onboarding Analyst | on exception | Each possible match is confirmed or cleared before the case moves on |
| Analyst approval of medium-risk client | Approval gate | Onboarding Analyst | always | The reason for the medium rating is understood and acceptable |
| MLRO approval of high-risk client | Approval gate | MLRO | always | The client's risk is acceptable to the firm |
| Exception: CRM unavailable | Human queue (exception) | Onboarding Analyst | on exception | Retried automatically up to 3 times, then queued for an analyst. |
| Decline client | Human task | Engagement Manager | always | — |

**Story index**

| Story | ID | Priority | Control | Confidence | DoR |
|---|---|---|---|---|---|
| Request KYC documents | `story_request_docs` | Must have | Automated (no person) | green 0.95 | ready |
| Verify identity documents | `story_verify_id` | Must have | Automated (no person) | green 0.95 | ready |
| Screen client and owners | `story_screen` | Must have | Automated + human review | green 0.92 | ready |
| Assign risk rating | `story_risk_rate` | Must have | Automated (no person) | green 0.95 | ready |
| Analyst approval of medium-risk client | `story_analyst_review` | Must have | Approval gate | green 0.95 | ready |
| MLRO approval of high-risk client | `story_mlro_approval` | Must have | Approval gate | green 0.95 | ready |
| Record KYC outcome | `story_record_kyc` | Must have | Automated (no person) | green 0.95 | ready |
| Decline client | `story_decline` | Must have | Human task | green 0.95 | ready |
| Chase missing documents | `story_chase_docs` | Should have | Automated (no person) | green 0.95 | ready |

---

### Request KYC documents · `story_request_docs`
**Must have** · Confidence **green (0.95)** · DoR **ready** · Control **Automated (no person)** · Open questions **0**

> As an **Onboarding Analyst**, I want **to send the KYC document request to the new client through the client portal**, so that **the client knows exactly which documents to send and where, helping us cut the time it takes to complete KYC for a new client**.

**Who benefits:** Onboarding Analyst, Client · **Goals served:** Cut the time it takes to complete KYC for a new client

**Human in the loop:** Automated (no person). Exception 'No documents after 10 working days' goes to Engagement Manager.

**Change from today:** Automated by suggestion S01 (today: manual, ~10 min per case).

**Acceptance criteria**

1. *No documents after 10 working days puts onboarding on hold* `ac_docs_overdue` (edge case)
   - Given a client who has not sent their KYC documents 10 working days after the request
   - When the daily overdue check runs
   - Then the engagement manager is notified
   - And onboarding for the client is set to on hold
2. *Document request sent through the portal* `ac_request_docs` (happy path)
   - Given a new client record in the CRM
   - When KYC starts
   - Then the client receives a portal request listing photo ID and proof of address for each director and owner
   - And the request is due 5 working days after sending

**Edge cases & exceptions**

- No documents after 10 working days (`exc_docs_overdue`): escalate; notify Engagement Manager
- No documents after 10 working days puts onboarding on hold (`ac_docs_overdue`): see acceptance criterion

**Time limits (SLAs)**

- **Client sends documents within 5 working days**: P5D working days; starts: KYC documents requested; stops: All KYC documents received; on breach: route to node → 'Chase missing documents'

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | read | crm_id, legal_name, country_risk |
| KYC documents (`ent_kyc_documents`) | write | photo_ids, proof_of_address, received_at |

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_chase_docs · downstream story_chase_docs, story_verify_id · systems Client portal

**Traceability:** nodes node_request_docs, node_await_docs · sources: AI improvement suggestions accepted by Sarah Lin, 5 Oct 2026; Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

### Verify identity documents · `story_verify_id`
**Must have** · Confidence **green (0.95)** · DoR **ready** · Control **Automated (no person)** · Open questions **0**

> As an **Onboarding Analyst**, I want **to verify each identity document through the e-ID verification service API**, so that **identities are verified in minutes, not by hand, helping us cut the time it takes to complete KYC for a new client and focus analyst time on the cases that need a human**.

**Who benefits:** Onboarding Analyst, Client, MLRO · **Goals served:** Cut the time it takes to complete KYC for a new client; Focus analyst time on the cases that need a human

**Human in the loop:** Automated (no person). Exception 'ID check failed' goes to Onboarding Analyst.

**Change from today:** Automated by suggestion S03 (today: manual, ~20 min per case).

**Acceptance criteria**

1. *Failed ID check goes to an analyst* `ac_id_check_failed` (edge case)
   - Given an expired passport for one director
   - When the identity documents are verified
   - Then the case is placed in the analyst's queue with the reason
   - And screening does not start until the analyst clears it
2. *Valid ID is verified automatically* `ac_verify_id` (happy path)
   - Given a valid passport for each director
   - When the identity documents are verified
   - Then a verification result is recorded for each director
   - And the case moves on to screening

**Edge cases & exceptions**

- ID check failed (`exc_id_check_failed`): manual review; notify Onboarding Analyst
- Failed ID check goes to an analyst (`ac_id_check_failed`): see acceptance criterion

**Data**

| Entity | Access | Attributes |
|---|---|---|
| KYC documents (`ent_kyc_documents`) | read | photo_ids, proof_of_address, received_at |

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_request_docs · downstream story_screen · systems e-ID verification service

**Traceability:** nodes node_verify_id · sources: AI improvement suggestions accepted by Sarah Lin, 5 Oct 2026; Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

### Screen client and owners · `story_screen`
**Must have** · Confidence **green (0.92)** · DoR **ready** · Control **Automated + human review** · Open questions **1**

> As an **Onboarding Analyst**, I want **to screen the client and every director in one batch through the screening tool's API**, so that **every client and owner is screened consistently in one go, helping us cut the time it takes to complete KYC for a new client and focus analyst time on the cases that need a human**.

**Who benefits:** Onboarding Analyst, Client, MLRO · **Goals served:** Cut the time it takes to complete KYC for a new client; Focus analyst time on the cases that need a human

**Human in the loop:** Automated + human review — reviewer: Onboarding Analyst, on exception. Checks: Each possible match is confirmed or cleared before the case moves on.

**Change from today:** Automated with review by suggestion S04 (today: manual, ~25 min per case).

**Acceptance criteria**

1. *Clean screening moves on automatically* `ac_screen_clear` (happy path)
   - Given a client and owners with no possible matches
   - When screening runs
   - Then the screening result is saved to the client file
   - And the case moves on to the risk rating
2. *Possible match is reviewed by an analyst* `ac_screen_possible_match` (edge case)
   - Given a director with a possible PEP match
   - When screening runs
   - Then the case waits for an analyst to confirm or clear the match
   - And the analyst's decision and reason are saved

**Edge cases & exceptions**

- Possible match is reviewed by an analyst (`ac_screen_possible_match`): see acceptance criterion

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | read | crm_id, legal_name, country_risk |
| Screening result (`ent_screening_result`) | write | sanctions_match, pep_match, adverse_media, match_score |

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_verify_id · downstream story_risk_rate · systems Screening tool

**Open questions**

- What match score counts as a possible match that an analyst must review? (major, asked, waiting on sme_priya_shah) `gap_match_threshold`

**Traceability:** nodes node_screen · sources: SME answer q_intake_01 – James Patel (Head of Onboarding Technology), 5 Oct 2026; AI improvement suggestions accepted by Sarah Lin, 5 Oct 2026; Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

### Assign risk rating · `story_risk_rate`
**Must have** · Confidence **green (0.95)** · DoR **ready** · Control **Automated (no person)** · Open questions **0**

> As an **Onboarding Analyst**, I want **to apply the KYC risk rating rule to the screening result and client country, and record the reason**, so that **every client gets the same rating for the same facts, helping us focus analyst time on the cases that need a human**.

**Who benefits:** Onboarding Analyst, MLRO · **Goals served:** Focus analyst time on the cases that need a human

**Human in the loop:** Automated (no person).

**Change from today:** Automated by suggestion S05 (today: manual, ~10 min per case).

**Acceptance criteria**

1. *Sanctions match or PEP gives high risk* `ac_risk_high` (edge case)
   - Given a screening result where a director is a PEP
   - When the risk rating is assigned
   - Then the risk rating is high
   - And the case goes to the MLRO for approval
2. *Clean screening gives low risk* `ac_risk_low` (happy path)
   - Given a screening result with no sanctions match, no PEP and no adverse media
   - And the client's country risk is standard
   - When the risk rating is assigned
   - Then the risk rating is low
   - And the case goes straight to recording
3. *Adverse media gives medium risk* `ac_risk_medium` (edge case)
   - Given a screening result with adverse media but no sanctions match or PEP
   - When the risk rating is assigned
   - Then the risk rating is medium
   - And the case goes to an analyst for approval

**Edge cases & exceptions**

- Sanctions match or PEP gives high risk (`ac_risk_high`): see acceptance criterion
- Adverse media gives medium risk (`ac_risk_medium`): see acceptance criterion

**Business rules**

- **KYC risk rating** (`rule_risk_rating`) → outcomes: low, medium, high

  | sanctions_match | pep_match | adverse_media | country_risk | → outcome |
  |---|---|---|---|---|
  | true | any | any | any | **high** |
  | any | true | any | any | **high** |
  | any | any | true | any | **medium** |
  | any | any | any | high | **medium** |
  | any | any | any | any | **low** |
  _Hit policy: first_

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | read | crm_id, legal_name, country_risk |
| Risk assessment (`ent_risk_assessment`) | read/write | rating, reason, approved_by, approved_at |
| Screening result (`ent_screening_result`) | read | sanctions_match, pep_match, adverse_media, match_score |

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_screen · downstream story_analyst_review, story_mlro_approval, story_record_kyc · systems —

**Traceability:** nodes node_risk_rate, node_risk_level · sources: SME answer q_intake_01 – James Patel (Head of Onboarding Technology), 5 Oct 2026; AI improvement suggestions accepted by Sarah Lin, 5 Oct 2026; Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

### Analyst approval of medium-risk client · `story_analyst_review`
**Must have** · Confidence **green (0.95)** · DoR **ready** · Control **Approval gate** · Open questions **0**

> As an **Onboarding Analyst**, I want **to an analyst approves a medium-risk client, or escalates it to the MLRO**, so that **medium-risk clients get a person's judgement before they're accepted, helping us focus analyst time on the cases that need a human**.

**Who benefits:** Onboarding Analyst, MLRO · **Goals served:** Focus analyst time on the cases that need a human

**Human in the loop:** Approval gate — approver: Onboarding Analyst. Checks: The reason for the medium rating is understood and acceptable.

**Change from today:** Unchanged from today.

**Acceptance criteria**

1. *Analyst approves a medium-risk client* `ac_analyst_approved` (happy path)
   - Given a medium-risk client because of adverse media
   - When the analyst approves the client with a reason
   - Then the approval, approver and reason are saved
   - And the outcome moves on to be recorded
2. *Analyst escalates a medium-risk client to the MLRO* `ac_analyst_rejected` (edge case)
   - Given a medium-risk client the analyst is not comfortable accepting
   - When the analyst rejects the client
   - Then the case goes to the MLRO for approval with the analyst's reason

**Edge cases & exceptions**

- Analyst escalates a medium-risk client to the MLRO (`ac_analyst_rejected`): see acceptance criterion

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Risk assessment (`ent_risk_assessment`) | read | rating, reason, approved_by, approved_at |

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_risk_rate · downstream story_mlro_approval, story_record_kyc · systems —

**Traceability:** nodes node_analyst_review · sources: Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

### MLRO approval of high-risk client · `story_mlro_approval`
**Must have** · Confidence **green (0.95)** · DoR **ready** · Control **Approval gate** · Open questions **0**

> As a **MLRO**, I want **to the MLRO decides whether to accept a high-risk client**, so that **only the MLRO can accept a high-risk client, helping us focus analyst time on the cases that need a human**.

**Who benefits:** Onboarding Analyst, MLRO · **Goals served:** Focus analyst time on the cases that need a human

**Human in the loop:** Approval gate — approver: MLRO. Checks: The client's risk is acceptable to the firm.

**Change from today:** Unchanged from today.

**Acceptance criteria**

1. *MLRO approves a high-risk client* `ac_mlro_approved` (happy path)
   - Given a high-risk client because a director is a PEP
   - When the MLRO approves the client
   - Then the approval, approver and date are saved
   - And the outcome moves on to be recorded
2. *MLRO rejects a high-risk client* `ac_mlro_rejected` (edge case)
   - Given a high-risk client with a sanctions match
   - When the MLRO rejects the client
   - Then nothing is recorded as KYC complete
   - And the engagement manager is asked to decline the client

**Edge cases & exceptions**

- MLRO rejects a high-risk client (`ac_mlro_rejected`): see acceptance criterion

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Risk assessment (`ent_risk_assessment`) | read | rating, reason, approved_by, approved_at |

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_analyst_review, story_risk_rate · downstream story_decline, story_record_kyc · systems —

**Traceability:** nodes node_mlro_approval · sources: Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

### Record KYC outcome · `story_record_kyc`
**Must have** · Confidence **green (0.95)** · DoR **ready** · Control **Automated (no person)** · Open questions **0**

> As an **Onboarding Analyst**, I want **to write the KYC outcome to the CRM and file the documents and screening results to the client file**, so that **the evidence is on the client file without rekeying and onboarding can continue, helping us cut the time it takes to complete KYC for a new client**.

**Who benefits:** Onboarding Analyst, Client · **Goals served:** Cut the time it takes to complete KYC for a new client

**Human in the loop:** Automated (no person). Exception 'CRM unavailable' goes to Onboarding Analyst.

**Change from today:** Automated by suggestion S06 (today: manual, ~15 min per case).

**Acceptance criteria**

1. *CRM outage retries, then goes to an analyst* `ac_crm_unavailable` (edge case)
   - Given the CRM is unavailable when a KYC outcome is ready to record
   - When the outcome is recorded
   - Then recording is retried up to 3 times
   - And after the third failure the case is placed in the analyst's queue
   - And nothing is marked KYC complete until the CRM write succeeds
2. *KYC outcome and evidence recorded* `ac_record_kyc` (happy path)
   - Given a client whose rating is low, or approved where needed
   - When the KYC outcome is recorded
   - Then the CRM shows KYC complete with the rating
   - And the documents, screening results and approvals are kept on the client file

**Edge cases & exceptions**

- CRM unavailable (`exc_crm_unavailable`): manual review; notify Onboarding Analyst
- CRM outage retries, then goes to an analyst (`ac_crm_unavailable`): see acceptance criterion

**Time limits (SLAs)**

- **KYC checks done within 3 working days of documents**: P3D working days; starts: All KYC documents received; stops: KYC outcome recorded; on breach: notify (notify MLRO)

**Data**

| Entity | Access | Attributes |
|---|---|---|
| KYC documents (`ent_kyc_documents`) | read | photo_ids, proof_of_address, received_at |
| Risk assessment (`ent_risk_assessment`) | read | rating, reason, approved_by, approved_at |
| Screening result (`ent_screening_result`) | read | sanctions_match, pep_match, adverse_media, match_score |

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_analyst_review, story_mlro_approval, story_risk_rate · downstream — · systems CRM, Shared drive

**Traceability:** nodes node_record_kyc · sources: SME answer q_intake_01 – James Patel (Head of Onboarding Technology), 5 Oct 2026; AI improvement suggestions accepted by Sarah Lin, 5 Oct 2026; Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

### Decline client · `story_decline`
**Must have** · Confidence **green (0.95)** · DoR **ready** · Control **Human task** · Open questions **0**

> As an **Engagement Manager**, I want **to decline the client because the risk is too high**, so that **the client hears the decision from their engagement manager, helping us cut the time it takes to complete KYC for a new client**.

**Who benefits:** Onboarding Analyst, Client · **Goals served:** Cut the time it takes to complete KYC for a new client

**Human in the loop:** Human task.

**Change from today:** Unchanged from today.

**Acceptance criteria**

1. *Engagement manager declines the client* `ac_decline` (happy path)
   - Given a client the MLRO has rejected
   - When the engagement manager declines the client
   - Then the client is told the firm cannot act
   - And the client record is marked declined

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_mlro_approval · downstream — · systems —

**Traceability:** nodes node_decline · sources: Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

### Chase missing documents · `story_chase_docs`
**Should have** · Confidence **green (0.95)** · DoR **ready** · Control **Automated (no person)** · Open questions **0**

> As an **Onboarding Analyst**, I want **to send the client a reminder on day 5, then every 3 working days until the documents arrive**, so that **late documents are chased without an analyst writing emails, helping us cut the time it takes to complete KYC for a new client and focus analyst time on the cases that need a human**.

**Who benefits:** Onboarding Analyst, Client, MLRO · **Goals served:** Cut the time it takes to complete KYC for a new client; Focus analyst time on the cases that need a human

**Human in the loop:** Automated (no person).

**Change from today:** Automated by suggestion S02 (today: manual, ~30 min per case).

**Acceptance criteria**

1. *Reminders follow the agreed schedule* `ac_chase_docs` (happy path)
   - Given a client who has not sent their documents 5 working days after the request
   - When the reminder schedule runs each working day
   - Then a reminder is sent on day 5
   - And a further reminder is sent every 3 working days until the documents arrive

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | read | crm_id, legal_name, country_risk |

**Non-functional**

- [security] KYC documents are visible only to onboarding and compliance
- [audit] Every check, result and approval is kept as evidence for 5 years after the relationship ends
- [volume] About 150 new clients a month, roughly double in April and May

**Dependencies:** upstream story_request_docs · downstream story_request_docs · systems Client portal

**Traceability:** nodes node_chase_docs · sources: AI improvement suggestions accepted by Sarah Lin, 5 Oct 2026; Studio assumption (confirmed by requester); Intake session with Sarah Lin (Compliance Manager), 5–6 Oct 2026

---

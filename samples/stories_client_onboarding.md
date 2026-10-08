# User stories — Client onboarding – KYC & engagement acceptance

_Rendered by M7 from IR version 3 (document-led path, mid-review, polish off). Do not edit — change the IR._

## Process context

**Goals**

- **Meet our anti-money laundering obligations for every new client** (`goal_aml_compliance`): no metric yet · benefits: —
- **Only accept engagements we are independent to perform** (`goal_independence`): no metric yet · benefits: —

**Scope**

- In: Taking on new audit and advisory clients

**Human-in-the-loop and approval gates**

_Shown on the process flow diagram (`flow/to_be_process_flow.drawio` for Lucidchart import, `.mmd` for Mermaid; for a document-led as-is: `flow/as_is_process_flow.drawio`)._

_No human checkpoints captured yet._

⚠ Control not set for 9 step(s): Log client request in CRM, Request KYC documents, Verify identity documents, Screen company and individuals, Assign client risk rating, Approve high-risk client, Perform conflict and independence check, Issue engagement letter, Notify client of decline.

**Story index**

| Story | ID | Priority | Control | Confidence | DoR |
|---|---|---|---|---|---|
| Log client request in CRM | `story_capture_request` | Priority not set | Not set | green 0.89 | not_ready |
| Request KYC documents | `story_request_docs` | Priority not set | Not set | red 0.46 | not_ready |
| Verify identity documents | `story_id_verify` | Priority not set | Not set | amber 0.62 | not_ready |
| Screen company and individuals | `story_screening` | Priority not set | Not set | amber 0.547 | not_ready |
| Assign client risk rating | `story_risk_rate` | Priority not set | Not set | red 0.45 | not_ready |
| Perform conflict and independence check | `story_conflict_check` | Priority not set | Not set | amber 0.56 | not_ready |
| Approve high-risk client | `story_high_risk_approval` | Priority not set | Not set | red 0.17 | not_ready |
| Notify client of decline | `story_decline` | Priority not set | Not set | amber 0.59 | not_ready |
| Issue engagement letter | `story_engagement_letter` | Priority not set | Not set | amber 0.62 | not_ready |

---

### Log client request in CRM · `story_capture_request`
**Priority not set** · Confidence **green (0.89)** · DoR **not_ready** · Control **Not set** · Open questions **2**

> As an **Engagement Manager**, I want **to log the new client request in the CRM with legal name, company number and requested service**, so that **the client record is available for the KYC document request**.

**Human in the loop:** Not set.

**Acceptance criteria**

1. *New client request is logged* `ac_capture_request` (happy path)
   - Given an Engagement Manager has received a request to act for a new client
   - When they log the request in the CRM
   - Then a client record exists with legal name, company number and requested service

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | write | legal_name, company_number, requested_service, jurisdiction |

**Dependencies:** upstream — · downstream story_request_docs · systems CRM

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`

**Not ready because**

- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-16: node_capture_request: human-in-the-loop mode not set

**Traceability:** nodes node_capture_request · sources: SOP OPS-ONB-004 Client Onboarding v4.0

---

### Request KYC documents · `story_request_docs`
**Priority not set** · Confidence **red (0.46)** · DoR **not_ready** · Control **Not set** · Open questions **5**

> As an **Onboarding Team**, I want **to request certified photo ID and proof of address for each director and beneficial owner (25%+) and the certificate of incorporation**, so that **the KYC document set is available for identity verification**.

**Human in the loop:** Not set.

**Acceptance criteria**

1. *KYC documents requested on time* `ac_request_docs` (happy path)
   - Given a client request has been logged in the CRM
   - When the Onboarding Team requests KYC documents
   - Then the request is sent to the client within 1 working day of the CRM request being logged
   - And the request lists photo ID and proof of address for each director and beneficial owner holding 25% or more, and the certificate of incorporation

**Time limits (SLAs)**

- **Document request sent within 1 working day**: P1D working days; starts: Client request logged in CRM; stops: Document request sent; on breach: undefined

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | read | legal_name, company_number, requested_service, jurisdiction |
| KYC Document Set (`ent_kyc_document_set`) | write | photo_ids, proofs_of_address, certificate_of_incorporation, received_at, complete |

**Dependencies:** upstream story_capture_request, story_id_verify · downstream story_id_verify · systems —

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`
- If a client hasn't returned their KYC documents, how many working days do we wait, and what happens then? (blocking, asked) `gap_wait_docs_timeout`
- For requesting documents, screening and the conflict check — what's the most common thing that goes wrong, and what should happen? (major, open) `gap_story_edge_cases`
- If the document request isn't sent within 1 working day, who should be told? (major, asked) `gap_request_docs_sla_breach`

**Not ready because**

- DOR-05: Wait node(s) ['node_wait_docs'] have no timeout.
- DOR-08: Open blocking gap(s): ['gap_wait_docs_timeout'].
- DOR-09: Story confidence 0.46 is below 0.80; confirm low-confidence elements.
- DOR-11: No process owner sign-off at the current closure.
- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-15: Story has a decision, wait or exception but no edge-case acceptance criterion.
- DOR-16: node_request_docs: human-in-the-loop mode not set

**Traceability:** nodes node_request_docs, node_wait_docs · sources: Email thread: Chasing KYC docs – Northgate Logistics; SOP OPS-ONB-004 Client Onboarding v4.0; Onboarding workshop 24 Sep 2026 (transcript)

---

### Verify identity documents · `story_id_verify`
**Priority not set** · Confidence **amber (0.62)** · DoR **not_ready** · Control **Not set** · Open questions **2**

> As an **Onboarding Team**, I want **to verify each identity document through the electronic ID verification service**, so that **verified identities are available for screening**.

**Human in the loop:** Not set.

**Acceptance criteria**

1. *Expired ID triggers replacement request* `ac_id_expired` (edge case)
   - Given a KYC document set containing an expired photo ID
   - When the identity documents are verified
   - Then the client is asked to provide a valid replacement
   - And the case returns to the document request step
2. *Identity documents verified* `ac_id_verified` (happy path)
   - Given a complete KYC document set has been received
   - When the Onboarding Team verifies the identity documents
   - Then a verification result is recorded for each director and beneficial owner

**Edge cases & exceptions**

- Expired ID document (`exc_id_expired`): go to 'Request KYC documents'
- Expired ID triggers replacement request (`ac_id_expired`): see acceptance criterion

**Data**

| Entity | Access | Attributes |
|---|---|---|
| KYC Document Set (`ent_kyc_document_set`) | read | photo_ids, proofs_of_address, certificate_of_incorporation, received_at, complete |

**Dependencies:** upstream story_request_docs · downstream story_request_docs, story_screening · systems Electronic ID Verification Service

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`

**Not ready because**

- DOR-09: Story confidence 0.62 is below 0.80; confirm low-confidence elements.
- DOR-11: No process owner sign-off at the current closure.
- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-16: node_id_verify: human-in-the-loop mode not set

**Traceability:** nodes node_id_verify · sources: SOP OPS-ONB-004 Client Onboarding v4.0; Onboarding workshop 24 Sep 2026 (transcript)

---

### Screen company and individuals · `story_screening`
**Priority not set** · Confidence **amber (0.547)** · DoR **not_ready** · Control **Not set** · Open questions **4**

> As an **Onboarding Team**, I want **to screen the company, directors and beneficial owners against sanctions, PEP and adverse media sources and save results to the client file**, so that **the screening result is available for the client risk rating**.

**Human in the loop:** Not set.

**Acceptance criteria**

1. *Screening completed and filed* `ac_screening_complete` (happy path)
   - Given identity documents have been verified
   - When the Onboarding Team runs screening
   - Then the company and every director and beneficial owner have been screened against sanctions, PEP and adverse media sources
   - And all screening results are saved to the client file

**Edge cases & exceptions**

- Screening service unavailable (`exc_screening_service_down`): UNDEFINED

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | read | legal_name, company_number, requested_service, jurisdiction |
| KYC Document Set (`ent_kyc_document_set`) | read | photo_ids, proofs_of_address, certificate_of_incorporation, received_at, complete |
| Screening Result (`ent_screening_result`) | write | sanctions_match, pep_match, adverse_media_severity |

**Dependencies:** upstream story_id_verify · downstream story_risk_rate · systems Screening Service

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`
- For requesting documents, screening and the conflict check — what's the most common thing that goes wrong, and what should happen? (major, open) `gap_story_edge_cases`
- If the screening service is unavailable, what should happen: retry later, use a manual fallback, or escalate to someone? (major, open) `gap_screening_down_handling`

**Not ready because**

- DOR-06: Exception(s) ['exc_screening_service_down'] have undefined handling.
- DOR-09: Story confidence 0.547 is below 0.80; confirm low-confidence elements.
- DOR-11: No process owner sign-off at the current closure.
- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-15: Story has a decision, wait or exception but no edge-case acceptance criterion.
- DOR-16: node_screening: human-in-the-loop mode not set

**Traceability:** nodes node_screening · sources: SOP OPS-ONB-004 Client Onboarding v4.0; Onboarding workshop 24 Sep 2026 (transcript)

---

### Assign client risk rating · `story_risk_rate`
**Priority not set** · Confidence **red (0.45)** · DoR **not_ready** · Control **Not set** · Open questions **4**

> As an **Onboarding Team**, I want **to apply the risk rating matrix to the screening result and client jurisdiction**, so that **the risk assessment decides whether approval is needed before the conflict check**.

**Human in the loop:** Not set.

**Acceptance criteria**

1. *PEP director gives High rating* `ac_risk_rating_high` (edge case)
   - Given a screening result where a director is a PEP
   - When the client risk rating is assigned
   - Then the client risk rating is High
2. *Clean screening gives Low rating* `ac_risk_rating_low` (happy path)
   - Given a screening result with no PEP matches and no adverse media
   - And the client jurisdiction is standard
   - When the client risk rating is assigned
   - Then the client risk rating is Low
   - And the case proceeds to the conflict check

**Edge cases & exceptions**

- PEP director gives High rating (`ac_risk_rating_high`): see acceptance criterion

**Business rules**

- **Client risk rating matrix** (`rule_risk_rating`) → outcomes: low, medium, high

  | pep_match | adverse_media_severity | jurisdiction | → outcome |
  |---|---|---|---|
  | true | any | any | **high** |
  | any | significant | any | **high** |
  | any | any | high_risk | **high** |
  | false | none | standard | **low** |
  _Hit policy: first_

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | read | legal_name, company_number, requested_service, jurisdiction |
| Risk Assessment (`ent_risk_assessment`) | read/write | rating, rationale |
| Screening Result (`ent_screening_result`) | read | sanctions_match, pep_match, adverse_media_severity |

**Dependencies:** upstream story_screening · downstream story_conflict_check, story_high_risk_approval · systems —

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`
- When a client is rated Medium risk, what decides that rating and what happens next? (blocking, asked) `gap_risk_medium_branch`
- What counts as 'significant' adverse media for the risk rating? (major, asked) `gap_significant_adverse_media`

**Not ready because**

- DOR-04: node_risk_decision: outcome(s) ['medium'] of rule_risk_rating not wired
- DOR-08: Open blocking gap(s): ['gap_risk_medium_branch'].
- DOR-09: Story confidence 0.45 is below 0.80; confirm low-confidence elements.
- DOR-11: No process owner sign-off at the current closure.
- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-16: node_risk_rate: human-in-the-loop mode not set

**Traceability:** nodes node_risk_rate, node_risk_decision · sources: SOP OPS-ONB-004 Client Onboarding v4.0; Onboarding workshop 24 Sep 2026 (transcript)

---

### Perform conflict and independence check · `story_conflict_check`
**Priority not set** · Confidence **amber (0.56)** · DoR **not_ready** · Control **Not set** · Open questions **4**

> As an **Independence Team**, I want **to check for conflicts of interest and independence issues for the new client**, so that **only engagements without unmanageable conflicts are accepted**.

**Human in the loop:** Not set.

**Acceptance criteria**

1. *Conflict check gates acceptance* `ac_conflict_check` (happy path)
   - Given a client rated Low, or rated High and approved
   - When the Independence Team performs the conflict and independence check
   - Then the check outcome is recorded
   - And the engagement is accepted only if no unmanageable conflict exists

**Business rules**

- **Engagement acceptance** (`rule_accept_engagement`) → outcomes: accept, decline
  ⚠ Natural language: "Accept if no conflict exists and the risk is acceptable; decline if a conflict cannot be managed."

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Client (`ent_client`) | read | legal_name, company_number, requested_service, jurisdiction |

**Dependencies:** upstream story_high_risk_approval, story_risk_rate · downstream story_decline, story_engagement_letter · systems —

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`
- For requesting documents, screening and the conflict check — what's the most common thing that goes wrong, and what should happen? (major, open) `gap_story_edge_cases`
- What exactly makes the engagement acceptable after the conflict check — no conflict found, or conflicts that can be managed with safeguards? (major, open) `gap_accept_rule_nl`

**Not ready because**

- DOR-04: rule_accept_engagement is natural language
- DOR-09: Story confidence 0.56 is below 0.80; confirm low-confidence elements.
- DOR-11: No process owner sign-off at the current closure.
- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-15: Story has a decision, wait or exception but no edge-case acceptance criterion.
- DOR-16: node_conflict_check: human-in-the-loop mode not set

**Traceability:** nodes node_conflict_check, node_accept_decision · sources: SOP OPS-ONB-004 Client Onboarding v4.0; Onboarding workshop 24 Sep 2026 (transcript)

---

### Approve high-risk client · `story_high_risk_approval`
**Priority not set** · Confidence **red (0.17)** · DoR **not_ready** · Control **Not set** · Open questions **5**

> As an **Engagement Partner**, I want **to approve the engagement for a high-risk client before it proceeds. The Engagement Partner should escalate promptly if they have concerns**, so that **only approved high-risk clients proceed to the conflict check**.

**Human in the loop:** Not set.

**Acceptance criteria**

1. *High-risk client needs approval* `ac_high_risk_approval` (happy path)
   - Given a client rated High
   - When approval is requested
   - Then the engagement does not proceed to the conflict check until approval is recorded
   - And the approver's decision is saved to the client file

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Risk Assessment (`ent_risk_assessment`) | read | rating, rationale |
| Screening Result (`ent_screening_result`) | read | sanctions_match, pep_match, adverse_media_severity |

**Dependencies:** upstream story_risk_rate · downstream story_conflict_check · systems —

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`
- The SOP says the Engagement Partner approves high-risk clients; in the 24 Sep workshop you said the MLRO does since July. Which is correct? (blocking, answered) `gap_high_risk_approver_conflict`
- If a high-risk client is not approved, what happens next? (major, open) `gap_approval_refused`
- When an approver has concerns about a high-risk client, within how many working days should they escalate? (minor, open) `gap_promptly`

**Not ready because**

- DOR-08: Open blocking gap(s): ['gap_high_risk_approver_conflict'].
- DOR-09: Story confidence 0.17 is below 0.80; confirm low-confidence elements.
- DOR-11: No process owner sign-off at the current closure.
- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-16: node_high_risk_approval: human-in-the-loop mode not set

**Traceability:** nodes node_high_risk_approval · sources: SOP OPS-ONB-004 Client Onboarding v4.0; Onboarding workshop 24 Sep 2026 (transcript)

---

### Notify client of decline · `story_decline`
**Priority not set** · Confidence **amber (0.59)** · DoR **not_ready** · Control **Not set** · Open questions **3**

> As an **Engagement Manager**, I want **to notify the client that the firm cannot act**, so that **the client knows the firm cannot act**.

**Human in the loop:** Not set.

**Acceptance criteria**

_None defined yet._

**Dependencies:** upstream story_conflict_check · downstream — · systems —

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`
- When we decline a client, what must the notification include and within what time? (major, open) `gap_decline_no_ac`

**Not ready because**

- DOR-02: No acceptance criteria with Given/When/Then.
- DOR-09: Story confidence 0.59 is below 0.80; confirm low-confidence elements.
- DOR-11: No process owner sign-off at the current closure.
- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-16: node_decline: human-in-the-loop mode not set

**Traceability:** nodes node_decline · sources: SOP OPS-ONB-004 Client Onboarding v4.0

---

### Issue engagement letter · `story_engagement_letter`
**Priority not set** · Confidence **amber (0.62)** · DoR **not_ready** · Control **Not set** · Open questions **2**

> As an **Engagement Manager**, I want **to issue the engagement letter to the client**, so that **the client is onboarded with an engagement letter**.

**Human in the loop:** Not set.

**Acceptance criteria**

1. *Engagement letter issued within SLA* `ac_engagement_letter` (happy path)
   - Given the engagement has been accepted
   - When the Engagement Manager issues the engagement letter
   - Then an engagement letter is issued to the client
   - And the letter is issued within 10 working days of the request being logged

**Time limits (SLAs)**

- **Onboarding completed within 10 working days**: P10D working days; starts: Client request logged in CRM; stops: Engagement letter issued; on breach: notify (notify Engagement Manager)

**Data**

| Entity | Access | Attributes |
|---|---|---|
| Engagement Letter (`ent_engagement_letter`) | write | document, issued_at |

**Dependencies:** upstream story_conflict_check · downstream — · systems —

**Open questions**

- Which of these steps are must-haves for the first automated release? (major, open) `gap_story_priority`
- Which goal does each step mainly serve — meeting AML obligations, or only accepting engagements we're independent to perform? (major, open) `gap_story_value`

**Not ready because**

- DOR-09: Story confidence 0.62 is below 0.80; confirm low-confidence elements.
- DOR-11: No process owner sign-off at the current closure.
- DOR-12: Story is not linked to a business goal (no real 'so that').
- DOR-13: Priority not set.
- DOR-14: Missing NFR categories: ['audit', 'security', 'volume'].
- DOR-16: node_engagement_letter: human-in-the-loop mode not set

**Traceability:** nodes node_engagement_letter · sources: SOP OPS-ONB-004 Client Onboarding v4.0; Onboarding workshop 24 Sep 2026 (transcript)

---

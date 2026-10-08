@proc_client_onboarding
Feature: Client onboarding – KYC & engagement acceptance
  Rendered by M7 from IR version 3. Scenarios map 1:1 to acceptance criteria.

  @story_capture_request @ac_capture_request
  Scenario: New client request is logged
    Given an Engagement Manager has received a request to act for a new client
    When they log the request in the CRM
    Then a client record exists with legal name, company number and requested service

  @story_request_docs @ac_request_docs @sla
  Scenario: KYC documents requested on time
    Given a client request has been logged in the CRM
    When the Onboarding Team requests KYC documents
    Then the request is sent to the client within 1 working day of the CRM request being logged
    And the request lists photo ID and proof of address for each director and beneficial owner holding 25% or more, and the certificate of incorporation

  @story_id_verify @ac_id_expired @edge_case @exception
  Scenario: Expired ID triggers replacement request
    Given a KYC document set containing an expired photo ID
    When the identity documents are verified
    Then the client is asked to provide a valid replacement
    And the case returns to the document request step

  @story_id_verify @ac_id_verified
  Scenario: Identity documents verified
    Given a complete KYC document set has been received
    When the Onboarding Team verifies the identity documents
    Then a verification result is recorded for each director and beneficial owner

  @story_screening @ac_screening_complete
  Scenario: Screening completed and filed
    Given identity documents have been verified
    When the Onboarding Team runs screening
    Then the company and every director and beneficial owner have been screened against sanctions, PEP and adverse media sources
    And all screening results are saved to the client file

  @story_risk_rate @ac_risk_rating_high @edge_case
  Scenario: PEP director gives High rating
    Given a screening result where a director is a PEP
    When the client risk rating is assigned
    Then the client risk rating is High

  @story_risk_rate @ac_risk_rating_low
  Scenario: Clean screening gives Low rating
    Given a screening result with no PEP matches and no adverse media
    And the client jurisdiction is standard
    When the client risk rating is assigned
    Then the client risk rating is Low
    And the case proceeds to the conflict check

  @story_conflict_check @ac_conflict_check
  Scenario: Conflict check gates acceptance
    Given a client rated Low, or rated High and approved
    When the Independence Team performs the conflict and independence check
    Then the check outcome is recorded
    And the engagement is accepted only if no unmanageable conflict exists

  @story_high_risk_approval @ac_high_risk_approval
  Scenario: High-risk client needs approval
    Given a client rated High
    When approval is requested
    Then the engagement does not proceed to the conflict check until approval is recorded
    And the approver's decision is saved to the client file

  @story_engagement_letter @ac_engagement_letter @sla
  Scenario: Engagement letter issued within SLA
    Given the engagement has been accepted
    When the Engagement Manager issues the engagement letter
    Then an engagement letter is issued to the client
    And the letter is issued within 10 working days of the request being logged

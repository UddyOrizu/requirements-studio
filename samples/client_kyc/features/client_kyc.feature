@proc_client_kyc_to_be
Feature: Client KYC checks
  Rendered by M7 from the to-be process v12. One scenario per acceptance criterion.

  @story_request_docs @ac_docs_overdue @must @edge_case @exception
  Scenario: No documents after 10 working days puts onboarding on hold
    Given a client who has not sent their KYC documents 10 working days after the request
    When the daily overdue check runs
    Then the engagement manager is notified
    And onboarding for the client is set to on hold

  @story_request_docs @ac_request_docs @must
  Scenario: Document request sent through the portal
    Given a new client record in the CRM
    When KYC starts
    Then the client receives a portal request listing photo ID and proof of address for each director and owner
    And the request is due 5 working days after sending

  @story_verify_id @ac_id_check_failed @must @edge_case @exception
  Scenario: Failed ID check goes to an analyst
    Given an expired passport for one director
    When the identity documents are verified
    Then the case is placed in the analyst's queue with the reason
    And screening does not start until the analyst clears it

  @story_verify_id @ac_verify_id @must
  Scenario: Valid ID is verified automatically
    Given a valid passport for each director
    When the identity documents are verified
    Then a verification result is recorded for each director
    And the case moves on to screening

  @story_screen @ac_screen_clear @must
  Scenario: Clean screening moves on automatically
    Given a client and owners with no possible matches
    When screening runs
    Then the screening result is saved to the client file
    And the case moves on to the risk rating

  @story_screen @ac_screen_possible_match @must @edge_case
  Scenario: Possible match is reviewed by an analyst
    Given a director with a possible PEP match
    When screening runs
    Then the case waits for an analyst to confirm or clear the match
    And the analyst's decision and reason are saved

  @story_risk_rate @ac_risk_high @must @edge_case
  Scenario: Sanctions match or PEP gives high risk
    Given a screening result where a director is a PEP
    When the risk rating is assigned
    Then the risk rating is high
    And the case goes to the MLRO for approval

  @story_risk_rate @ac_risk_low @must
  Scenario: Clean screening gives low risk
    Given a screening result with no sanctions match, no PEP and no adverse media
    And the client's country risk is standard
    When the risk rating is assigned
    Then the risk rating is low
    And the case goes straight to recording

  @story_risk_rate @ac_risk_medium @must @edge_case
  Scenario: Adverse media gives medium risk
    Given a screening result with adverse media but no sanctions match or PEP
    When the risk rating is assigned
    Then the risk rating is medium
    And the case goes to an analyst for approval

  @story_analyst_review @ac_analyst_approved @must
  Scenario: Analyst approves a medium-risk client
    Given a medium-risk client because of adverse media
    When the analyst approves the client with a reason
    Then the approval, approver and reason are saved
    And the outcome moves on to be recorded

  @story_analyst_review @ac_analyst_rejected @must @edge_case
  Scenario: Analyst escalates a medium-risk client to the MLRO
    Given a medium-risk client the analyst is not comfortable accepting
    When the analyst rejects the client
    Then the case goes to the MLRO for approval with the analyst's reason

  @story_mlro_approval @ac_mlro_approved @must
  Scenario: MLRO approves a high-risk client
    Given a high-risk client because a director is a PEP
    When the MLRO approves the client
    Then the approval, approver and date are saved
    And the outcome moves on to be recorded

  @story_mlro_approval @ac_mlro_rejected @must @edge_case
  Scenario: MLRO rejects a high-risk client
    Given a high-risk client with a sanctions match
    When the MLRO rejects the client
    Then nothing is recorded as KYC complete
    And the engagement manager is asked to decline the client

  @story_record_kyc @ac_crm_unavailable @must @edge_case @exception
  Scenario: CRM outage retries, then goes to an analyst
    Given the CRM is unavailable when a KYC outcome is ready to record
    When the outcome is recorded
    Then recording is retried up to 3 times
    And after the third failure the case is placed in the analyst's queue
    And nothing is marked KYC complete until the CRM write succeeds

  @story_record_kyc @ac_record_kyc @must
  Scenario: KYC outcome and evidence recorded
    Given a client whose rating is low, or approved where needed
    When the KYC outcome is recorded
    Then the CRM shows KYC complete with the rating
    And the documents, screening results and approvals are kept on the client file

  @story_decline @ac_decline @must
  Scenario: Engagement manager declines the client
    Given a client the MLRO has rejected
    When the engagement manager declines the client
    Then the client is told the firm cannot act
    And the client record is marked declined

  @story_chase_docs @ac_chase_docs @should
  Scenario: Reminders follow the agreed schedule
    Given a client who has not sent their documents 5 working days after the request
    When the reminder schedule runs each working day
    Then a reminder is sent on day 5
    And a further reminder is sent every 3 working days until the documents arrive

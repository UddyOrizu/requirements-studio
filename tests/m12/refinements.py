"""story_refine responses, by instruction. T21 is the recorded session's; the others are authored for the M12
acceptance tests (split, out of scope, a question) and recorded into cassettes the same way."""
from tests.m0.kyc_replay import TIMELINE

T21 = next(e for e in TIMELINE if e["kind"] == "story_refinement")
SPLIT = "Split this into sending the request and handling replies"
OUT_OF_SCOPE = "Also rename the decline step to Reject client"
QUESTION = "Who approves this?"
MERGE = "Merge this with chasing"


def _ref(excerpt: str) -> dict:
    return {"source_id": "src_intake_is_client_kyc", "locator": {"kind": "turn", "value": "T21"}, "excerpt": excerpt,
            "stance": "supports", "extraction_certainty": 0.9}


def _meta(excerpt: str) -> dict:
    return {"status": "proposed", "confidence": 0.0, "provenance": [_ref(excerpt)]}


RESPONSES = {
    T21["answer"]["text"]: {"ops": T21["ops"], "summary": T21["captured"], "clarifying_question": None,
                            "answer": None},
    SPLIT: {"ops": [
        {"op": "replace", "path": "/nodes/node_request_docs/name", "value": "Send KYC document request"},
        {"op": "add", "path": "/nodes/node_handle_replies", "value": {
            "type": "task", "name": "Handle client replies",
            "description": "File each document the client uploads through the portal and check the set is complete.",
            "actor_id": "act_onboarding_analyst", "system_ids": ["act_client_portal"], "inputs": ["ent_kyc_documents"],
            "hitl": {"mode": "automated"}, "goal_ids": ["goal_faster_kyc"], "priority": "must",
            "outcome": "every document the client sends is filed and ready to verify",
            "meta": _meta("handling replies")}},
        {"op": "replace", "path": "/edges/edge_await_verify/to", "value": "node_handle_replies"},
        {"op": "add", "path": "/edges/edge_replies_verify", "value": {
            "from": "node_handle_replies", "to": "node_verify_id", "meta": _meta("handling replies")}},
        {"op": "add", "path": "/acceptance_criteria/ac_handle_replies", "value": {
            "title": "Uploaded documents are filed", "kind": "happy_path", "applies_to": ["node_handle_replies"],
            "given": ["a client uploads a passport through the portal"], "when": ["the upload is received"],
            "then": ["the passport is filed to the client's KYC documents"], "meta": _meta("handling replies")}},
    ], "summary": ["Split 'Request KYC documents' into 'Send KYC document request' and 'Handle client replies'",
                   "New acceptance criterion: Uploaded documents are filed"],
        "clarifying_question": None, "answer": None},
    MERGE: {"ops": [
        {"op": "replace", "path": "/nodes/node_request_docs/description",
         "value": "Send the KYC document request through the client portal, then remind the client on day 5 and "
                  "every 3 working days until the documents arrive."},
        {"op": "add", "path": "/nodes/node_request_docs/meta/provenance/-", "value": _ref("Merge this with chasing")},
        {"op": "remove", "path": "/edges/edge_chase_await"},
        {"op": "replace", "path": "/slas/sla_docs_due/breach_action",
         "value": {"action": "route_to_node", "target_node_id": "node_request_docs"}},
        {"op": "replace", "path": "/acceptance_criteria/ac_chase_docs/applies_to", "value": ["node_request_docs"]},
        {"op": "remove", "path": "/nodes/node_chase_docs"},
    ], "summary": ["Merged 'Chase missing documents' into 'Request KYC documents'",
                   "Reminder acceptance criterion now belongs to 'Request KYC documents'"],
        "clarifying_question": None, "answer": None},
    OUT_OF_SCOPE: {"ops": [{"op": "replace", "path": "/nodes/node_decline/name", "value": "Reject client"}],
                   "summary": ["Renamed 'Decline client' to 'Reject client'"], "clarifying_question": None,
                   "answer": None},
    QUESTION: {"ops": [], "summary": [], "clarifying_question": None,
               "answer": "Nobody approves recording: it runs automatically once a low-risk client is rated, or after "
                         "the analyst or MLRO has approved a medium- or high-risk client."},
}

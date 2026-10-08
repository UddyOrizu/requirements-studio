"""Wording for deterministic gaps: title, why it matters and a drafted question (M5 "Gap object").

This is fixed copy, not an LLM prompt: M6 rephrases questions for a specific SME through prompts/interview_phrase.md.
"""
# type → (title, why_it_matters, question, answer_type, suggested_answers); strings are str.format templates over
# the finding's context.
Wording = tuple[str, str, str, str, list[str]]

TEXTS: dict[str, Wording] = {
    "node_without_actor": (
        "Nobody is named for '{name}'",
        "Automation has to know who performs or owns each step, and who gets the work when it needs a person.",
        "Who does '{name}' today?", "actor", ["{actor_options}", "Other"]),
    "decision_missing_branch": (
        "'{node}' has outcomes with no next step",
        "A decision outcome with nowhere to go stops the case; the system cannot route it.",
        "When '{node}' comes out as {missing}, what happens next?", "choice",
        ["It follows the same path as another outcome", "It goes to a person to decide", "The case stops", "Other"]),
    "decision_missing_default": (
        "'{node}' has no default path",
        "If none of the rules match, the case has nowhere to go.",
        "If none of the expected outcomes apply at '{node}', what should happen?", "choice",
        ["Send it to a person to decide", "Treat it like the most common outcome", "Other"]),
    "wait_without_timeout": (
        "No time limit while waiting at '{name}'",
        "Without a time limit cases wait forever; nobody is prompted to chase or close them.",
        "How long do we wait at '{name}', and what happens if nothing has arrived by then?", "duration",
        ["5 working days, then chase", "10 working days, then close the case", "Other"]),
    "unreachable_node": (
        "'{name}' can never be reached",
        "A step that no path leads to will never run; either a connection or the step itself is wrong.",
        "Which step comes just before '{name}'?", "choice", ["{node_options}", "This step is not needed", "Other"]),
    "no_path_to_end": (
        "Cases that reach '{name}' never finish",
        "A case that cannot reach an end stays open forever and blocks reporting and SLAs.",
        "What happens after '{name}'?", "choice", ["{node_options}", "The process ends here", "Other"]),
    "undefined_entity_reference": (
        "'{ref}' is used but not defined",
        "Rules and acceptance tests can only be automated against data the system knows about.",
        "What is '{attribute}' on {entity}, and where does it come from?", "free_text", []),
    "sla_without_breach_action": (
        "Nothing happens when '{name}' is missed",
        "A time limit with no consequence is not enforced; someone must be told or the case must move.",
        "If '{name}' is missed, who should be told, or what should happen?", "actor",
        ["{actor_options}", "Other"]),
    "exception_without_handling": (
        "No handling for '{name}'",
        "When this happens the case stalls, because the system has no instruction.",
        "When {trigger}, what should happen?", "choice",
        ["Retry later", "Send it to a person to handle", "Escalate", "Stop the case", "Other"]),
    "node_without_acceptance_criteria": (
        "No acceptance criteria for '{name}'",
        "Without criteria nobody can test that the automated step does the right thing.",
        "When '{name}' is done correctly, what can we see? (e.g. a status, a record, a message sent)", "free_text",
        []),
    "natural_language_rule_gating_edge": (
        "'{name}' is described in words, not as a rule",
        "The system routes cases on this decision, so it needs exact conditions it can evaluate.",
        "What exactly decides '{name}'? Please give the conditions and values.", "free_text", []),
    "low_confidence_element": (
        "Unconfirmed: {label}",
        "This was drawn from weak or indirect evidence; building on it risks automating the wrong thing.",
        "Is this right: {label}?", "yes_no", ["Yes", "No, it's different"]),
    "conflicting_sources": (
        "Sources disagree about {label}",
        "The sources say different things, so automating either version could be wrong.",
        "The sources disagree about {label}: {statements}. Which is correct?", "choice",
        ["{choice_options}", "Both apply", "Other"]),
    "story_value_missing": (
        "Steps not linked to a goal",
        "Every story needs a business reason ('so that'); without it the team cannot judge value or trade-offs.",
        "Which goal does each of these steps serve: {names}?", "choice", ["{goal_options}", "Other"]),
    "story_priority_missing": (
        "Steps without a priority",
        "Without priorities the first release cannot be planned.",
        "Which of these steps are must-haves for the first release: {names}?", "choice",
        ["All of them", "Only some of them", "Other"]),
    "story_edge_cases_missing": (
        "No edge cases for steps with decisions, waits or exceptions",
        "These steps can go wrong or branch; without an edge-case test the unhappy path is never checked.",
        "For {names}: what's the most common thing that goes wrong, and what should happen then?", "free_text", []),
    "hitl_undefined": (
        "Human involvement not set",
        "Each step needs to say whether it runs automatically, needs a person's review, or is done by a person.",
        "Which of these steps can run automatically, which need a person to review, and which need approval: "
        "{names}?", "free_text", []),
    "approval_gate_incomplete": (
        "Approval gate is incomplete",
        "An approval needs a named approver, the criteria they check, and a path for both approval and rejection.",
        "For {names}: who approves, what do they check, and what happens if they reject?", "free_text", []),
}

TOPIC: dict[str, str] = {
    "node_without_actor": "ownership", "decision_missing_branch": "decisions", "decision_missing_default": "decisions",
    "wait_without_timeout": "timing", "unreachable_node": "flow", "no_path_to_end": "flow",
    "undefined_entity_reference": "data", "sla_without_breach_action": "timing",
    "exception_without_handling": "exceptions", "node_without_acceptance_criteria": "acceptance_criteria",
    "natural_language_rule_gating_edge": "decisions", "low_confidence_element": "confirmation",
    "conflicting_sources": "conflict", "story_value_missing": "goals", "story_priority_missing": "prioritisation",
    "story_edge_cases_missing": "acceptance_criteria", "hitl_undefined": "human_controls",
    "approval_gate_incomplete": "human_controls",
}


class _Defaults(dict):
    def __missing__(self, key: str) -> str:
        return "?"


def word(gap_type: str, context: dict) -> dict:
    """Title, why_it_matters and question for a finding; list-valued context fills option placeholders."""
    title, why, question, answer_type, suggestions = TEXTS[gap_type]
    ctx = _Defaults(context)
    options = []
    for s in suggestions:
        if s.startswith("{") and s.endswith("}") and isinstance(context.get(s[1:-1]), list):
            options += context[s[1:-1]]
        else:
            options.append(s.format_map(ctx))
    q = {"text": question.format_map(ctx), "answer_type": answer_type}
    if options:
        q["suggested_answers"] = options
    return {"title": title.format_map(ctx), "why_it_matters": why.format_map(ctx), "question": q}

---
name: intake_draft_acs
module: M0 (entering Deepen)
output_model: DraftedACs
variables: [story_closures, existing_acs]
temperature: 0
---
For each step with no acceptance criteria, draft 1–2 criteria in Given/When/Then with concrete example values.
If the step's story contains a decision, wait or exception, at least one must be kind "edge_case".
Every Then must be observable (status change, message sent, record created, decision outcome).
Also draft a one-line outcome for each step ("what this achieves for the business") and propose goal_ids from
the existing goals. Everything you return is an assumption for the requester to confirm.
Give each criterion an ac_id (ac_<snake_case>, not already used) and applies_to: the step's node id, plus the id of the
exception or rule it exercises.
<data>
story_closures: {{ story_closures }}
existing_acs: {{ existing_acs }}
</data>

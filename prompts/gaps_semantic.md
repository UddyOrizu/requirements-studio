---
name: gaps_semantic
module: M5
output_model: SemanticGapList
variables: [subgraph, allowed_ids, existing_gaps]
temperature: 0
---
Review this part of a process model as an experienced business analyst preparing it for automation.
Find only these gap types: ambiguous_term, undefined_threshold, implied_missing_step,
unclear_ownership_of_data, missing_exception_path.
For each: type, target_ids (only from allowed_ids), title, why_it_matters (1 sentence, consequence for automation),
question (≤ 40 words, answerable by a business SME), answer_type, suggested_answers (2–4), topic_tags.
Return an empty list if the model is clear. Do not report issues already listed in existing_gaps.
Also report hitl_undefined (a step whose human involvement is unclear) and approval_gate_incomplete (an approval with no
approver, no criteria, or no rejected path).
<data>{{subgraph}}</data>
<data>
allowed_ids: {{ allowed_ids }}
existing_gaps: {{ existing_gaps }}
</data>

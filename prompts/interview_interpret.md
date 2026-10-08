---
name: interview_interpret
module: M6
output_model: AnswerInterpretation
variables: [gap, question, answer, target_elements, allowed_paths, id_conventions]
temperature: 0
---
Convert the SME's answer into JSON Patch (RFC 6902) operations on the process model.
- Only use paths in allowed_paths, or add new elements under /slas, /exceptions, /acceptance_criteria,
  /edges, /glossary using the id conventions.
- Model only what the answer states. If the answer is ambiguous or partial, set follow_up_question.
- Return {ops, interpretation_confidence (0–1), follow_up_question|null, summary (1 sentence)}.
Do not add meta.status / confirmed_by — the system adds confirmation ops.
<data>{{gap}} {{question}} answer: {{answer}} {{target_elements}} allowed: {{allowed_paths}}</data>
<data>
id_conventions: {{ id_conventions }}
</data>

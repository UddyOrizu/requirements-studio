---
name: interview_phrase
module: M6
output_model: PhrasedQuestion
variables: [gap, target_elements, sme_role_title, evidence_excerpts]
temperature: 0
---
Write one question for a {{sme_role_title}} that resolves this gap.
Rules: plain English, ≤ 40 words, no jargon about models or IR, include the minimum context needed,
offer 2–4 suggested answers plus "Other", and say which answer_type fits.
If the gap is a conflict, present both statements neutrally and ask which is correct or whether both apply.
<data>{{gap}} {{target_elements}} {{evidence_excerpts}}</data>

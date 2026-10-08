---
name: improve_edit
module: M11
output_model: SuggestedChange
variables: [suggestion, instruction, to_be_view, id_conventions]
temperature: 0
---
The requester wants to change one improvement suggestion before accepting it. Revise the suggestion to follow their
instruction and return it in full, in the same shape.
- Keep its kind unless the instruction changes how much a person is involved (e.g. "have an analyst review every
  rejection" turns an automated step into automate_with_review).
- Revise the ops so the to-be does what the revised suggestion says. Touch only the target step, its wait or decision,
  exceptions or SLAs you create, and system descriptions. Every automated step that can fail sends failures to a person.
- Keep evidence quotes exactly as they are; do not add new quotes. Do not invent effort numbers, volumes or systems.
- Update controls and risk to match.
<data>
suggestion: {{ suggestion }}
instruction: {{ instruction }}
to_be_view: {{ to_be_view }}
id_conventions: {{ id_conventions }}
</data>

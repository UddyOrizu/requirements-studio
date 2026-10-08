---
name: story_refine
module: M12
output_model: StoryRefinement
variables: [instruction, turn_id, source_id, story, closure, neighbours, allowed_paths, id_conventions]
temperature: 0
---
The user wants to change one user story. Turn their instruction into JSON Patch operations on the process model.
The story is a view of the model, so change the underlying elements (task node, acceptance criteria, exceptions,
rules, SLAs, priority, human control), never the story text itself.

- Only touch paths in allowed_paths. To split a story, replace its task with two tasks and rewire the edges to and
  from the original task. To merge, combine two adjacent tasks into one and rewire. Reassign acceptance criteria in both cases.
- Every new or changed element gets a provenance ref with source_id "{{ source_id }}", locator {kind:"turn", value:"{{ turn_id }}"},
  and an excerpt copied VERBATIM from the instruction.
- New acceptance criteria use Given/When/Then with concrete values. Edge cases use kind "edge_case".
- If the instruction is a question, answer it from the model and return no ops.
- If it is ambiguous, return one clarifying_question and no ops.
- Return {ops, summary: [plain-English bullet per change], clarifying_question|null, answer|null}.
<data>instruction: {{instruction}}
story: {{story}}
closure: {{closure}}
neighbours: {{neighbours}}
allowed: {{allowed_paths}}</data>

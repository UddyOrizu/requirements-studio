# Prompts

Every LLM prompt Requirements Studio uses is a file in this folder. Code loads a prompt **by file name**:

```python
result, call = await llm.complete_json("intake_interpret", variables, IntakeInterpretation)
#                                      ^ loads prompts/intake_interpret.md
```

There is no prompt management system. Git is the version history: change a prompt by editing its file, run the
tests (LLM tests replay recorded responses, so re-record the affected cassettes), and commit.

## File format

```markdown
---
name: intake_interpret            # must equal the file name
module: M0
output_model: IntakeInterpretation  # Pydantic model in packages/ir_core/llm_models.py
variables: [target, answer, ...]  # every variable the template uses; the gateway rejects missing or extra ones
temperature: 0
model: (optional) overrides RS_LLM_MODEL for this prompt
---
Jinja2 template body. Variables as {{ name }}. Source text always inside <data> or <source> tags.
```

## Rules for the gateway (S1)

- Resolve `prompts/<name>.md`. Unknown name means an error at startup, not at call time (all prompts load and validate on boot).
- Prepend `_preamble.md` to every prompt.
- Render with Jinja2 `StrictUndefined`; the caller must pass every listed variable (null where not applicable) and nothing else.
- Log every call to `llm_calls` with `prompt_file` and `prompt_sha256` (hash of the file content at call time),
  plus model, tokens, latency and correlation id, so any output can be traced to the exact prompt text.
- Cassette keys are `(prompt_file, prompt_sha256, sha256(variables))`. Editing a prompt invalidates its cassettes on purpose.
- Prompt files are read-only at runtime. Production images bake them in, and dev reloads on change.

## Files

- `extract_process.md`
- `improve_suggest.md` (M11)
- `story_refine.md` (M12)
- `gaps_semantic.md`
- `intake_draft_acs.md`
- `intake_interpret.md`
- `intake_phrase.md`
- `intake_playback.md`
- `interview_interpret.md`
- `interview_live.md`
- `interview_phrase.md`
- `reconcile_match.md`
- `render_polish.md`
- `_preamble.md`: shared safety and format preamble

## Output model sketches

```python
class Citation(BaseModel):
    block_ids: list[str]
    excerpt: str = Field(max_length=300)
    extraction_certainty: float = Field(ge=0, le=1)

class StepCandidate(Citation):
    type: Literal["task","decision","wait","event","start","end"]
    name: str; description: str = ""; performer: str | None = None
    inputs: list[str] = []; outputs: list[str] = []; order_hint: int | None = None
    outcomes: list[str] = []

class ExtractionResult(BaseModel):
    actors: list[ActorCandidate]; entities: list[EntityCandidate]; steps: list[StepCandidate]
    rules: list[RuleCandidate]; exceptions: list[ExceptionCandidate]; slas: list[SLACandidate]
    terms: list[TermCandidate]

class AnswerInterpretation(BaseModel):
    ops: list[JsonPatchOp]; interpretation_confidence: float = Field(ge=0, le=1)
    follow_up_question: str | None; summary: str
```

# M12 — Ideas Workspace & Story Refinement

## Purpose
The product's information architecture. Everything hangs off an **Idea**: its conversation, its as-is and to-be
process models, its flows, its stories and its exports. Users can list ideas, open one to see the flow and stories,
refine stories conversationally, and export.

## Core user journeys

| # | Journey | Screens | Modules |
|---|---|---|---|
| J1 | **New idea → conversation → flow + stories** | New idea → Conversation | M0 (+ M11 if a process exists today), M7, M10 |
| J2 | **List ideas → idea detail with flow → stories** | Ideas list → Idea: Overview / Flow / Stories | M12, M10, M7 |
| J3 | **Refine user stories** | Story detail → Refine chat / inline edit | M12, M3, M7 |
| J4 | **Improve an as-is process with AI** | Idea: Improvements | M11 |
| J5 | **Export** | Idea: Export | M9 |

## Screens

### Ideas list (home)
Cards or table, one row per idea, newest first. Filters: status, owner, tag. Search over title and summary.

| Column | Source |
|---|---|
| Title + one-line summary | `idea.title`, `idea.summary` |
| Status chip | discovering · improving · refining · ready · exported |
| Owner, last updated | `owner_user_id`, `updated_at` |
| Progress | coverage %, stories ready / total |
| Improvement | "6/7 accepted · ~275 h/month" when an as-is exists |
| Open questions | count, with who they're waiting on |
| Flow thumbnail | to-be flow (as-is until forked) rendered small |

Primary action: **New idea**. Sample data: `samples/ideas_index.json` (schema `schemas/idea.schema.json`).

### New idea
One large text box ("Describe your idea or the process you want to improve"), voice input, optional file upload
(SOPs, transcripts, emails go to M1/M2), and one question: **Is there a process today?** (Yes / No / Not sure). The
answer sets the M0 mode. Submitting creates the idea and opens the Conversation with the first question.

### Idea detail (tabs)
| Tab | Content |
|---|---|
| **Overview** | Summary, goals with metrics, beneficiaries, scope, NFRs, readiness, open questions, "Continue conversation" |
| **Conversation** | The M0 intake workspace (M0 §4): resumes where it stopped; shows the full history |
| **Flow** | **As-is / To-be toggle** (as-is only if one exists), plus a **Compare** view (side by side, changed steps highlighted). Same control styling as M10. Download for Lucidchart, copy Mermaid. Click a step to open its story |
| **Improvements** | M11 suggestion cards (accept/reject/edit), decided list, "Suggest more improvements", hours saved |
| **Stories** | Story list (table): title, priority, control, confidence, DoR, open questions, change from today. Filters by priority, control, DoR, has open questions. Opens Story detail |
| **Export** | M9 formats with preview; export history |

### Story detail
Rendered from the IR (M7) exactly as in the stories file, with three ways to change it:

1. **Refine chat** (scoped to the story). The user types an instruction; `prompts/story_refine.md` turns it into IR patch ops
   on the story's closure. The UI shows a **preview diff** (story before/after, plus flow changes) before **Apply**.
   Examples it must support:
   - "Add what happens if the CRM is down" → new exception + edge-case AC (sample turn T21)
   - "Make the acceptance criteria more specific about the reminder dates" → AC replace
   - "Split this into sending the request and handling replies" → **split**: one task node becomes two, the edges are rewired,
     ACs are reassigned, and two stories result
   - "Merge this with chasing" → **merge**: two adjacent tasks become one
   - "Who approves this?" (a question) → answered from the IR, no change
2. **Inline edit** of fields that map 1:1 to IR (priority, AC text, outcome, control mode). Each is a patch.
3. **Ask someone** about this story (creates an M6 question, attached as an open question).

Every change is a patch (CLAUDE.md rule 2). The story shows its **version history** (patches touching its closure) with undo.
After any change, M5/M8 re-run, so the story's DoR badge and confidence update live. Sign-off is cleared only if the
closure hash changed (M8).

### Refinement rules
- The LLM receives the story's closure + neighbouring nodes + allowed paths. Ops outside the closure are rejected,
  except the split/merge rewiring of adjacent edges.
- If the instruction is ambiguous, it asks one clarifying question in the chat instead of guessing.
- Refinements of a to-be never modify the as-is.
- Refinement provenance: source `src_intake_<session>`, locator `turn: Tn`, excerpt verbatim from the instruction (same rule as M0).

## API
| Method | Path | Notes |
|---|---|---|
| GET | `/ideas?status=&owner=&q=` | Ideas list with stats |
| POST | `/ideas` | `{text, has_process_today: yes\\|no\\|not_sure, files?}` → idea + session + first question |
| GET | `/ideas/{id}` | idea, stats, process ids |
| GET | `/ideas/{id}/flow?variant=as_is\\|to_be&format=json\\|drawio\\|mermaid` | flow data for the canvas, or a download |
| GET | `/ideas/{id}/flow/compare` | node-by-node as-is vs to-be (`compare_rows`) |
| GET | `/ideas/{id}/stories` · `/stories/{sid}` | rendered stories |
| POST | `/stories/{sid}/refine` | `{instruction}` → `{preview: {ops, story_before, story_after, flow_changes}, question?}` |
| POST | `/stories/{sid}/refine/{preview_id}/apply` | applies the patch |
| GET | `/stories/{sid}/history` | patches touching the closure |

## Acceptance tests
- **AC-M12-1** `GET /ideas` returns both ideas in `samples/ideas_index.json` with the stats shown there.
- **AC-M12-2** The client KYC idea's Flow tab offers As-is and To-be. Compare lists the 9 to-be tasks with their as-is control,
  minutes and change (`compare_rows`, as in the stories file's "What changes from today" table).
- **AC-M12-3** Refining `story_record_kyc` with the T21 instruction previews and then applies exactly the T21 `story_refinement` ops.
  The story gains the "CRM unavailable" edge case, and the to-be flow gains a human queue in the analyst lane.
- **AC-M12-4** A split instruction on a task produces two task nodes, rewired edges, both stories rendered and DoR re-evaluated.
  An undo restores the previous version byte for byte.
- **AC-M12-5** An instruction that would touch elements outside the story's closure (other than split/merge rewiring) is rejected
  with an explanation.

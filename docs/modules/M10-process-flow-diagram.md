# M10 — Process Flow Diagram (diagram as code, Lucidchart-ready)

## Purpose
Render the second **primary output** from the IR: a swimlane process flow that shows, at a glance, which steps are
automated, where a person reviews AI output (**HITL**), where a named approver must approve before the flow
continues (**approval gates**), and where exceptions are handed to a person (**human queues**).

It's generated as code, deterministically. The same IR always gives byte-identical files, so diagrams can be
diffed, reviewed and versioned with the stories.

| File | Use | Lucidchart |
|---|---|---|
| `<variant>_process_flow.drawio` (draw.io / mxGraph XML), e.g. `to_be_process_flow.drawio` | **Primary.** Fixed layout, swimlanes, styles, legend | Import as a draw.io file, giving **editable shapes** |
| `<variant>_process_flow.mmd` (Mermaid flowchart) | Docs, GitHub/ADO wikis, quick review | Paste into Lucid's diagram-as-code (Mermaid) panel. It renders, but not as draggable shapes |

Reference implementation: `tools/render_flow.py` (`render_drawio`, `render_mermaid`, `hitl_summary`).
Production code (`packages/flow_renderer`) must produce byte-identical output on the samples.

## What gets drawn

| IR | Shape (draw.io) | Mermaid | Label prefix | Colour |
|---|---|---|---|---|
| task, `hitl.mode = automated` | rounded rectangle | `[ ]` | `[AUTO]` | blue |
| task, `hitl_review` | rounded rectangle, thick border | `[ ]` | `[AUTO + HUMAN REVIEW]` + "Reviewed by X (when)" | amber |
| task, `human_task` | rounded rectangle, dark border | `[ ]` | `[HUMAN]` | white |
| task, `approval` | **hexagon** | `{{ }}` | `APPROVAL GATE` + "Approver: X" | red |
| task, mode not set | dashed rectangle | `[ ]` | `[CONTROL NOT SET]` | white/grey |
| decision | rhombus | `{ }` | — | yellow |
| wait | dashed rounded rectangle | `([ ])` | `[WAIT]` + "Due within …" from its SLA | grey |
| start / end | circle / double circle | `(( ))` / `((( )))` | — | green |
| exception with handling `manual_review`/`escalate` | dashed rounded rectangle in the person's lane | `[ ]` | `HUMAN QUEUE` | amber dashed |
| edge | solid arrow | `-->` | its label or outcome | — |
| approval `rejected` edge | **red** arrow | `-->` + `linkStyle` red | "Rejected…" | red |
| exception / SLA `route_to_node` | dashed grey arrow | `-.->` | "Exception: …" / "Overdue (SLA …)" | grey |

Colour is never the only signal: every shape's label also states its control type (accessibility, greyscale printing).
A legend box is included in the draw.io file and as comments at the top of the Mermaid file.

## As-is vs to-be

Both variants use the same renderer:
- **As-is:** task labels add `~N min per case` and `PAIN: …` from `as_is_effort`. Waits and rule decisions sit in the lane of
  the person doing the step before them, because nothing is automated today.
- **To-be:** steps changed by an accepted M11 suggestion add `Changed by Sxx: was manual`. Waits and rule decisions sit in the
  automation lane.
- Titles say "as-is (today)" or "to-be (improved)". The M12 Flow tab shows them side by side.

## Swimlanes (deterministic)

- **Human lanes**, one per actor who performs a `human_task` or `approval`, or who receives a human queue.
  Ordered by the first column they appear in.
- **"Automated (AI agents & systems)" lane**, last: `automated` and `hitl_review` tasks, waits, and decisions whose rule
  is a `table`/`expression`. A natural-language decision sits in the lane of the step before it.
- Start/end take a neighbour's lane. A task with mode not set sits in its `actor_id` lane.

This makes the to-be picture explicit: everything outside the automation lane is a person's time.

## Layout (draw.io)

- Column = shortest distance from start over edges + exception/SLA routes. Row within a lane: the main start→end
  path first, then branches.
- Column width 200 px, row height 110 px, lane header 140 px. Edges use orthogonal routing (`edgeStyle=orthogonalEdgeStyle`),
  so Lucid and draw.io route them around shapes.
- Styles: `tools/render_flow.py::STYLE` is normative.

## Where it appears
- Intake workspace (M0) live canvas uses the same control styling. **Download for Lucidchart** button (`.drawio`) and
  **Copy Mermaid**.
- Canvas (M4) has a "Controls" toggle that switches node colouring from confidence to control type.
- Stories header (M7): a **Human-in-the-loop and approval gates** table (`hitl_summary`), plus a *Human in the loop* line on every story.
- Exports (M9): both flows in `.drawio` and `.mmd`; MOTHER package adds `flow/hitl_summary.json`.

## API
`GET /processes/{pid}/diagram?format=drawio|mermaid&version=` → file download (`application/vnd.jgraph.mxfile` /
`text/vnd.mermaid`). `GET /processes/{pid}/hitl` → `hitl_summary` JSON.

## Acceptance tests
- **AC-M10-1** Rendering the sample IRs reproduces `samples/flow/as_is_*`, `samples/client_kyc/flow/as_is_*` and `samples/client_kyc/flow/to_be_*` byte for byte.
- **AC-M10-2** The draw.io file parses as XML. Every live node is a cell with the style for its control type, and every
  edge's source and target exist (validator check).
- **AC-M10-3** In the client KYC to-be diagram, every changed task shows `Changed by S0n`, and `node_analyst_review` is a hexagon in the Onboarding Analyst lane with an
  "Approved" edge to `node_record_kyc` and a red "Rejected: escalate to MLRO" edge to `node_mlro_approval`, a hexagon in the
  MLRO lane whose red "Rejected" edge goes to `node_decline` (Engagement Manager lane). `node_screen` is amber with "Reviewed by
  Onboarding Analyst (on exceptions)". "ID check failed" is a human queue in the Onboarding Analyst lane, and "No documents after
  10 working days" is a human queue in the Engagement Manager lane.
- **AC-M10-4** The Mermaid file renders with `@mermaid-js/mermaid-cli` without errors (CI step).
- **AC-M10-5** Manual check once per release: import the client KYC `to_be_process_flow.drawio` into Lucidchart. Shapes are editable, lanes and
  labels are intact, and the legend is present.

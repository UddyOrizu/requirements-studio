# M4 — Process Canvas UI (correction interface)

## Purpose
Let people **correct** a drafted process quickly: see it, see why each element exists, fix it, confirm it.

## Screens

| Screen | Purpose |
|---|---|
| **Intake workspace** (M0) | Conversation + live canvas + coverage/stories/questions panel. See M0 §4. Default landing for "New idea" |
| **Process list** | Status, readiness %, open blocking gaps, owner |
| **Sources** | Upload, parse status, authority weight, view parsed blocks |
| **Canvas** (primary) | Diagram + side panels (below) |
| **Gap inbox** | Open gaps by priority; "ask SME", "answer myself", "dismiss/waive" |
| **Patch review** | Proposed patches with visual diff on canvas |
| **Stories** | Rendered stories + Gherkin, confidence band, DoR status; "edit" jumps to IR element |
| **DoR dashboard** | Per-story checks; sign-off; waivers |
| **SME portal** | Minimal page for SMEs: their questions only, one-click suggested answers |
| **Export** | Build package, history, download |

## Canvas behaviour

- Rendering: React Flow; auto-layout with `elkjs` (layered, left→right); swimlanes by actor (toggle).
- Node shapes: start/end circle, task rounded rect, decision diamond, wait hourglass badge, event small circle,
  subprocess double border.
- **Confidence colouring**: border green / amber / red per bands (IR §8.1). Confirmed elements show a tick.
  Contradicted elements show a split-colour badge.
- **Variant toggle**: as-is / to-be (when an as-is exists), plus Compare (side by side, changed steps highlighted, M12).
- **Controls view** (toggle): colours nodes by human control instead of confidence, using the M10 styles (automated, human review, human task, approval gate, human queue), and shows an approver/reviewer chip. Setting a step's control is an inline edit (`/nodes/<id>/hitl`).
- **Gap markers**: red dot with count on any element targeted by an open gap; click opens the gap.
- **Provenance panel**: selecting any element lists its provenance refs; clicking one opens the source viewer
  scrolled/highlighted to the locator. Contradicting refs shown side by side.
- **Inline edits** (each produces JSON Patch ops, `auto_apply=true`, author = user):
  - rename / edit description
  - change actor (dropdown + "new actor")
  - add node on edge (splits edge), delete node (reconnects if single in/out, else asks)
  - draw / delete edge; set decision outcome label on edge
  - set SLA (duration picker) / add exception (trigger + handling)
  - add acceptance criterion (G/W/T form with glossary autocomplete; vague terms underlined)
  - **Confirm** (sets `meta.status=confirmed`, `confirmed_by`) / **Reject**
- Keyboard: `C` confirm, `R` reject, `E` edit, `G` next gap, `Ctrl+Z` undo (= inverse patch).
- Undo is a new patch applying the inverse ops (jsonpatch can generate it from the before/after snapshots).
- Optimistic UI: apply ops locally, reconcile on server response; on `409` show conflict banner and reload.

## "Correct, don't author" affordances
- **Bulk confirm** for a selected region once a BA has walked through it with an SME.
- **Proposal diffs**: proposed patches render as ghost nodes/edges (dashed) with accept/reject chips.
- **"Walkthrough mode"**: steps through nodes in flow order, showing description, actor, ACs and gaps one at a
  time — designed for screen-share with an SME; every "yes that's right" is a confirm.

## Real-time
Subscribe to `ir.patched` and `gaps.updated` via WebSocket per process; multiple BAs can work concurrently.

## Accessibility
Every canvas action is available from the element side panel (no drag-only operations); colour is never the sole
signal (icons + text labels for confidence bands).

## Acceptance tests
- **AC-M4-1** Loading the sample IR renders 15 nodes; `node_wait_docs` shows a gap marker; `node_high_risk_approval`
  shows a contradiction badge.
- **AC-M4-2** Clicking the contradicting provenance on `node_high_risk_approval` opens the transcript at `00:14:32`.
- **AC-M4-3** Renaming a node issues a single `replace` op on `/nodes/<id>/name` and the canvas updates on the
  `ir.patched` event.
- **AC-M4-4** Deleting a task with one in and one out edge reconnects predecessor to successor in the same patch.

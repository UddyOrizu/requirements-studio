# M9 — Exports

## Purpose
Get an idea's outputs out of the tool in the formats teams already use. Exports are generated from the IR on demand
(never hand-edited), versioned against the IR version they came from, and downloadable singly or as one zip.

Reference renderers: `tools/render_exports.py` (Jira, Azure DevOps, backlog CSV/Excel, improvements report),
`tools/render_flow.py` (Lucidchart/Mermaid), and the M7 renderer (Markdown/Gherkin). Samples: `samples/client_kyc/exports/`.

## Formats

| Format | File | Content | Import into |
|---|---|---|---|
| **Lucidchart** | `to_be_process_flow.drawio`, `as_is_process_flow.drawio` | M10 swimlane flows with control styling | Lucidchart (import draw.io, giving editable shapes); draw.io |
| **Mermaid** | `*_process_flow.mmd` | Same flows as code | Lucid diagram-as-code, GitHub/ADO wikis, docs |
| **Markdown** | `stories.md`, `improvements.md` | Detailed stories (M7); AI improvements report (M11) | Confluence, SharePoint, wikis |
| **Gherkin** | `<process>.feature` | One scenario per acceptance criterion | Test tooling (Cucumber, SpecFlow, Behave) |
| **Jira** | `jira_import.csv` | 1 Epic (the idea) + 1 Story per user story | Jira Cloud CSV importer |
| **Azure DevOps** | `azure_devops_import.csv` | 1 Feature (the idea) + 1 User Story per user story | Azure Boards CSV import |
| **Excel** | `stories_backlog.xlsx` | Sheets: Stories, Acceptance criteria, Human controls, Improvements, As-is vs to-be | Excel, Google Sheets |
| **CSV** | `stories_backlog.csv` | The Stories sheet as flat CSV | Any tool |
| **MOTHER package** | `package.zip` | IR + all of the above + manifest (below) | MOTHER |

### Jira CSV
- Columns: `Issue ID, Issue Type, Summary, Parent, Priority, Labels, Labels, Labels, Description`.
- **Row order matters:** the Epic comes first (Issue ID `1`), then every Story with `Parent = 1`. In the importer, map
  `Issue ID → Issue ID` and `Parent → Parent` so stories are linked to the epic
  ([Atlassian KB](https://support.atlassian.com/jira/kb/keep-issue-parent-child-mapping-during-csv-import-to-jira-cloud/)).
- Priority from MoSCoW: must → High, should → Medium, could → Low, won't → Lowest.
- Labels: `requirements-studio`, the process slug, `control-<mode>` (e.g. `control-approval`).
- Description (Jira wiki markup): story sentence · priority + human control · change from today · numbered acceptance
  criteria (Given/When/Then bullets) · edge cases · business rules · data · non-functional · open questions · generated-from line.

### Azure DevOps CSV
- Columns: `ID, Work Item Type, Title 1, Title 2, Description, Acceptance Criteria, Priority, Tags`.
- **ID left empty** (new items). The Feature's title goes in `Title 1`; each User Story's title goes in `Title 2` on
  the following rows, which makes it a child of that Feature
  ([Microsoft Learn](https://learn.microsoft.com/en-us/Azure/devops/boards/queries/import-work-items-from-csv?view=azure-devops)).
- `Description` and `Acceptance Criteria` are HTML. Priority: must 1, should 2, could 3, won't 4. Tags are semicolon-separated.
- Assumes the **Agile** process (Feature → User Story, *Acceptance Criteria* field). For Scrum, map Work Item Type to
  *Product Backlog Item*. Setting `RS_ADO_PROCESS=agile|scrum` switches the type names. Max 1,000 rows per import.

### Excel / CSV backlog
| Sheet | Rows |
|---|---|
| Stories | one per story: id, title, priority, control, as a / I want / so that, ACs (flattened), edge cases, NFRs, dependencies, systems, open questions, change from today, DoR, confidence |
| Acceptance criteria | one per AC: story, id, kind, title, Given, When, Then |
| Human controls | `hitl_summary`: step, control, who, when, checks |
| Improvements | M11 suggestions: id, title, kind, decision, minutes/hours saved, control, reason |
| As-is vs to-be | `compare_rows`: step, today's control, minutes today, to-be control, change |

Header row styled and frozen, auto-filter on, wrapped text. The CSV equals the Stories sheet.

## Export screen (M12 Idea → Export)
Checkboxes per format (defaults: Lucidchart, Markdown, Jira or ADO by tenant setting), a preview pane (first rows of
CSV, rendered Markdown, flow thumbnail), **Download** (single file or zip), and export history (who, when, IR version,
formats). Exports of a not-ready idea are allowed. They carry a "Draft — N stories not ready" banner in Markdown and a
`DRAFT` label in Jira/ADO.

## MOTHER package
### Preconditions
- Process status `ready` (all stories `ready`/`waived`), **or** an owner forces a `partial` export, in which case
  only `ready`/`waived` stories and their closures are included, and the manifest lists excluded stories.
- No patches in `proposed` state touching included closures (warn; owner can override).

### Package contents (zip, also available unpacked via API)

```
package/
  manifest.yaml               see samples/export/manifest.yaml
  ir.json                     IR at the exported version, stories populated, rejected elements removed
  stories.md                  M7 render
  features/<process>.feature  M7 Gherkin
  flow/as_is_process_flow.*   M10 as-is flow (when one exists)
  flow/to_be_process_flow.*   M10 to-be flow (.drawio + .mmd)
  improvements.json           M11 suggestions with decisions
  flow/hitl_summary.json      every human touchpoint: step, control, who, when, checks
  dor_report.json             M8 at that version
  gaps_open.json              remaining non-blocking open gaps (minor/major) with waivers
  sources_index.json          source ids → title, kind, sha256, uri (originals not bundled by default)
  audit_summary.json          counts: patches, confirmations by SME, questions asked/answered, elapsed days
```

### Transformations
- Drop `meta.status = rejected|superseded` elements and any references to them.
- Keep provenance (MOTHER uses excerpts as context for agent prompt generation).
- Add `export.hints` per task node for MOTHER:
  `{ automation_hint, hitl, single_goal_statement, priority, goal_ids, system_ids, acceptance_criteria_ids, qc_rubric_seed }`. MOTHER builds agents only for `automated`/`hitl_review` steps and routes `hitl_review`/`approval` to the named person where
  `qc_rubric_seed` is the list of `then` clauses from its ACs — MOTHER builds the QC agent rubric from these.
- Compute `ir_hash` = sha256(canonical ir.json); `package_hash` = sha256 of manifest with file hashes.

### Delivery
- Store in object storage `exports/{process_id}/{export_id}.zip`.
- `POST` to MOTHER import webhook (configurable) with `{export_id, package_uri (SAS, 24 h), ir_hash, ir_version}`;
  MOTHER acknowledges with `{import_id, status}` stored on the export row.
- Re-exporting the same IR version returns the existing export (idempotent by `ir_hash`).
- A later patch sets the process back to `in_review`. Existing exports are marked `superseded_by` when the next one
  is created, and are never changed.

## API
- `GET /ideas/{id}/exports/formats` → available formats + defaults
- `POST /ideas/{id}/exports {formats: [...], variant?: to_be|as_is}` → `{export_id, files: [...]}` (synchronous for text formats; zip assembled async)
- `GET /exports/{id}` · `GET /exports/{id}/download?file=` · `GET /ideas/{id}/exports` (history)
- MOTHER: `POST /processes/{pid}/exports {mode: full|partial, force?: bool}` and `POST /exports/{id}/mother-ack`

## Acceptance tests
- **AC-M9-1** For the client KYC to-be, the Jira, Azure DevOps, backlog CSV and improvements files equal `samples/client_kyc/exports/*` byte for byte,
  and the `.xlsx` sheets equal the reference rows (validator check).
- **AC-M9-2** The Jira CSV lists the Epic first and every Story has `Parent = 1`. The ADO CSV has an empty ID column, the Feature in
  `Title 1` and every User Story in `Title 2`.
- **AC-M9-3** Manual check once per release: import `jira_import.csv` into a Jira Cloud sandbox and `azure_devops_import.csv` into an
  Azure Boards (Agile) sandbox. 1 epic/feature and 9 linked stories are created, with acceptance criteria populated.
- **AC-M9-4** MOTHER: the manifest matches the structure of `samples/export/manifest.yaml`, and `ir.json` validates. A full export
  with an un-ready story returns `409`, and exporting twice at the same IR version returns the same `export_id`.
- **AC-M9-5** `qc_rubric_seed` for a task equals the `then` clauses of its acceptance criteria.

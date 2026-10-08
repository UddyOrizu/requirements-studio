# M3 — IR Store & Patch Service

## Purpose
The only component allowed to change the IR. Applies patches atomically, validates, versions, audits, and
publishes `ir.patched`.

## Responsibilities
- Create process (empty IR v0 conforming to schema).
- Accept patches, run the review workflow, apply, validate, version.
- Path-level rebase for stale `base_version`.
- Serve IR at any version; diff between versions.
- Recompute element confidence after each apply (calls `packages/confidence_dor.score_elements`).

## Apply algorithm

```
apply(patch):
  lock process row (SELECT … FOR UPDATE)
  cur = latest version
  if patch.base_version < cur.version:
      touched = union(changed_paths of patches base_version+1 .. cur)
      if any(op.path overlaps touched for op in patch.ops): mark conflicted; return 409 {conflicting_paths}
  doc = jsonpatch.apply(cur.snapshot, patch.ops)           # on a copy
  forbid ops on /stories, /process/version, /process/updated_at
  ir_core.validate_schema(doc)                              # JSON Schema
  ir_core.validate_integrity(doc)                           # IR spec §9
  if patch.evidence.answer_id: assert confirmation ops present for touched elements
  doc = confidence_dor.score_elements(doc)                  # recompute meta.confidence
  doc.process.version = cur.version + 1; updated_at = now
  insert ir_versions(version, snapshot, sha256(canonical_json(doc)))
  patch.status = applied; insert audit_log
  publish ir.patched {from, to, changed_paths}
```

"Overlaps" = one path is a prefix of the other (`/nodes/node_x` overlaps `/nodes/node_x/name`).

Canonical JSON for hashing: sorted keys, no whitespace, UTF-8, `meta.confidence` included.

## Review workflow
- `proposed` → reviewers notified (process owner + BAs). Reviewer may `accept`, `reject` (with reason) or
  `edit-and-accept` (creates a new user patch referencing the original, original marked `superseded`).
- Auto-accept policy (configurable per process; default **off**): see M6 §6.

## API
- `POST /processes` → creates process + IR v0
- `GET /processes/{pid}/ir?version=` · `GET /processes/{pid}/ir/diff?from=&to=`
- `POST /processes/{pid}/patches` → `201` (applied) | `202` (proposed) | `409` (conflict) | `422` (invalid)
- `POST /patches/{id}/accept|reject` · `GET /processes/{pid}/patches?status=`

## Acceptance tests
- **AC-M3-1** Applying `samples/patch_example.json` to `samples/ir_client_onboarding.json` (version 3) produces
  version 4 where `node_high_risk_approval.actor_id = act_mlro`, its `meta.status = confirmed`, and confidence ≥ 0.95.
- **AC-M3-2** A patch adding an edge to a non-existent node returns `422` with an integrity error naming the id.
- **AC-M3-3** Two patches with `base_version=3` touching different nodes both apply (second rebases).
  Two touching the same node: second returns `409` with the conflicting path.
- **AC-M3-4** Any op targeting `/stories/...` returns `422`.
- **AC-M3-5** Hash is stable: serialising the same IR twice yields the same sha256.

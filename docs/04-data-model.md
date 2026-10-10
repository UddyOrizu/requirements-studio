# 04 — Data Model (Postgres 16)

UUIDv7 primary keys unless noted. `created_at`/`updated_at` timestamptz on all tables. JSONB where shown.

```sql
-- M3
processes(id text pk, name, domain, description, owner_user_id, status, current_version int,
          settings jsonb)            -- thresholds, authority weights, auto_accept policy
ir_versions(process_id fk, version int, snapshot jsonb, ir_hash char(64), patch_id fk null,
            pk(process_id, version))
ir_patches(id pk, process_id fk, base_version int, applied_version int null, ops jsonb,
           author_kind, author_id, reason, evidence jsonb, interpretation_confidence numeric null,
           auto_apply bool, status, reviewed_by null, reviewed_at null, supersedes_patch_id null,
           changed_paths text[])

-- M12 / M11
ideas(id text pk, title, summary, owner_user_id, status, has_as_is bool, as_is_process_id null, to_be_process_id null,
      session_id, tags text[], stats jsonb, created_at, updated_at)
suggestions(id text, idea_id fk, kind, target_refs text[], title, change_summary, rationale, evidence jsonb, benefit jsonb,
            controls, risk, confidence numeric, status, decision jsonb, ops jsonb, applied_patch_id null, pk(idea_id, id))
story_refinements(id pk, process_id fk, story_id, instruction, preview jsonb, patch_id null, status, by, at)

-- M0
intake_sessions(id text pk, mode, idea_id, process_id fk, requester_user_id, phase, status, coverage jsonb, parked text[],
                current_target jsonb, started_at, completed_at null)
intake_turns(id pk, session_id fk, n int, phase, target jsonb, question jsonb, answer_text, special null,
             ask_sme_id null, patch_id fk null, captured jsonb, assumptions jsonb, follow_up_question null,
             coverage_after jsonb, at, unique(session_id, n))

-- M1
sources(id text pk, process_id fk, kind, title, uri, sha256, authority_weight numeric, status,
        metadata jsonb, deleted_at null, unique(process_id, sha256))
source_blocks(id pk, source_id fk, block_id, ord int, text, clean_text, locator_kind, locator_value,
              speaker null, heading_path text[])
source_chunks(id pk, source_id fk, ord int, block_ids text[], text, embedding vector(1536))
pii_map(id pk, source_id fk, placeholder, value_encrypted bytea)

-- M2
extraction_runs(id pk, process_id fk, source_id fk, source_sha, prompt_file, prompt_sha256,
                model, status, stats jsonb, patch_id fk null, unique(source_id, source_sha, prompt_file,
                prompt_sha256, model))

-- M5
gaps(id text pk, process_id fk, fingerprint char(40), type, severity, detector, target_refs text[],
     title, why_it_matters, question jsonb, routing jsonb, priority numeric, status,
     ir_version_detected int, resolved_by_patch_id null, waiver jsonb null,
     unique(process_id, fingerprint) where status not in ('resolved'))

-- M6
smes(id text pk, name, email, role_title, actor_ids text[], topic_tags text[], topic_embedding vector(1536),
     process_ids_owned text[], channels text[], max_open_questions int, working_hours jsonb,
     out_of_office_until date null, delegate_sme_id null)
questions(id text pk, process_id fk, origin, asked_by null, gap_ids text[], sme_id fk null, assignee_user_id fk null,
          batch_id, channel, text, context_snippet, answer_type, suggested_answers jsonb, status, sent_at, due_at,
          reminded_at, escalated_at)        -- the person asked: an SME entry and/or an internal user
answers(id pk, question_id fk, answered_by, text, structured_value jsonb, answered_at, patch_id fk null,
        interpretation_confidence numeric, follow_up_question null)
interviews(id pk, process_id fk, participants text[], gap_ids text[], transcript jsonb, status,
           source_id fk null)

-- M7 / M8
stories_cache(process_id, ir_version, story_id, rendered_md, gherkin, pk(process_id, ir_version, story_id))
dor_reports(id pk, process_id fk, ir_version, report jsonb)
signoffs(id pk, process_id fk, story_id, ir_version, closure_hash, signed_by, signed_at)
waivers(id pk, process_id fk, story_id, check_id, reason, waived_by, waived_at, revoked_at null)

-- M9
exports(id pk, process_id fk, ir_version, ir_hash, package_hash, mode, uri, status, mother_import_id null,
        superseded_by null, unique(process_id, ir_hash, mode))

-- S3 Identity: internal accounts (roles user | admin); Entra ID sign-ins link by object id
users(id text pk, email, name, role, status, password_hash null, entra_oid null, session_version int,
      failed_sign_ins int, locked_until null, last_sign_in_at null, created_by null,
      unique(lower(email)), unique(entra_oid) where entra_oid is not null)   -- status: invited | active | disabled
user_tokens(id pk, user_id fk, purpose, token_hash unique, expires_at, used_at null, created_by null)
                                     -- invitation and password-reset links; only a SHA-256 of the token is kept

-- Approvals: ask a named user to decide (patch_review | story_signoff | suggestion | question)
approval_requests(id text pk, kind, idea_id fk null, process_id fk null, subject_id, title, summary null, message null,
                  details jsonb, requested_by, assignee_user_id fk, status, response null, decided_by null,
                  decided_at null, due_at null, unique(kind, subject_id, assignee_user_id) where status = 'pending')
                                     -- status: pending | approved | rejected | answered | cancelled | closed

-- S2 Notifications
email_outbox(id pk, to_address, to_name, subject, text_body, html_body, template, related_id null, status,
             attempts int, next_attempt_at, last_error null, sent_at null)   -- queued with the change it announces

-- Shared
llm_calls(id pk, correlation_id, process_id null, prompt_file, prompt_sha256, model,
          input_tokens, output_tokens, latency_ms, status, error null)
audit_log(id pk, process_id null, actor_kind, actor_id, action, target, before jsonb null,
          after jsonb null, at)  -- append-only; revoke UPDATE/DELETE from app role
events_outbox(id pk, type, payload jsonb, published_at null)   -- transactional outbox → Redis Streams
```

Indexes: `source_chunks USING hnsw (embedding vector_cosine_ops)`, `smes USING hnsw (topic_embedding …)`,
`gaps(process_id, status, priority desc)`, `questions(sme_id, status)`, `ir_patches(process_id, status)`,
`approval_requests(assignee_user_id, status)`, `email_outbox(next_attempt_at) where status = 'queued'`.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { DorChip, ErrorNote, Loading, Section } from "../components/ui";
import type { ApprovalDetail as Detail, StoryRow, Suggestion } from "../types";
import { KIND_LABEL, STATUS_STYLE, ago } from "./Approvals";

const VERBS: Record<Detail["kind"], [string, string]> = {
  patch_review: ["Approve change", "Reject"], story_signoff: ["Sign off stories", "Ask for changes"],
  suggestion: ["Accept suggestion", "Reject"], question: ["Send answer", ""],
};

export default function ApprovalDetail() {
  const { approvalId = "" } = useParams();
  const qc = useQueryClient();
  const key = ["approvals", "detail", approvalId];
  const detail = useQuery({ queryKey: key, queryFn: () => api.get<Detail>(`/approvals/${approvalId}`) });
  const [note, setNote] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const done = (d: Detail) => { qc.setQueryData(key, d); qc.invalidateQueries({ queryKey: ["approvals"] }); setRejecting(false); setNote(""); };
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject" | "answer") => api.post<Detail>(`/approvals/${approvalId}/decision`, { decision, note: note || undefined }),
    onSuccess: done,
  });
  const cancel = useMutation({ mutationFn: () => api.post<Detail>(`/approvals/${approvalId}/cancel`), onSuccess: done });

  if (detail.isLoading) return <Loading />;
  if (detail.error) return <ErrorNote error={detail.error} />;
  const a = detail.data!;
  const [approveLabel, rejectLabel] = VERBS[a.kind];
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link to="/approvals" className="text-sm text-accent-700 hover:underline">← Approvals</Link>
      <header>
        <p className="text-xs text-slate-500">{KIND_LABEL[a.kind]}{a.idea_title && <> · <Link className="hover:underline" to={`/ideas/${a.idea_id}`}>{a.idea_title}</Link></>}</p>
        <div className="mt-1 flex items-start justify-between gap-4">
          <h1 className="text-xl font-semibold text-slate-900">{a.title}</h1>
          <span className={`chip shrink-0 ${STATUS_STYLE[a.status]}`} data-testid="approval-status">{a.status}</span>
        </div>
        <p className="mt-1 text-sm text-slate-500">
          {a.requested_by.name} asked {a.assignee.name} · {ago(a.created_at)}{a.summary && ` · ${a.summary}`}
        </p>
        {a.message && <blockquote className="mt-3 border-l-4 border-accent-500 bg-accent-50 px-4 py-2 text-sm text-slate-700">“{a.message}”</blockquote>}
      </header>

      <Subject a={a} />

      {a.status !== "pending" && (
        <Section title="Outcome">
          <p className="text-sm text-slate-700">
            <span className="capitalize">{a.status}</span>{a.decided_by && ` by ${a.decided_by.name}`}{a.decided_at && ` · ${ago(a.decided_at)}`}
          </p>
          {a.response && <p className="mt-2 text-sm text-slate-600">“{a.response}”</p>}
        </Section>
      )}

      {a.can_decide && (
        <Section title={a.kind === "question" ? "Your answer" : "Your decision"}>
          {a.kind === "question" ? (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); decide.mutate("answer"); }}>
              <textarea className="input min-h-28" aria-label="Your answer" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Write your answer…" />
              <button className="btn-primary" disabled={!note.trim() || decide.isPending}>{approveLabel}</button>
            </form>
          ) : rejecting ? (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); decide.mutate("reject"); }}>
              <textarea className="input min-h-20" aria-label="What needs to change" autoFocus value={note} onChange={(e) => setNote(e.target.value)}
                        placeholder="What needs to change? (required)" />
              <div className="flex gap-2">
                <button className="btn-primary" disabled={!note.trim() || decide.isPending}>{rejectLabel}</button>
                <button type="button" className="btn-ghost" onClick={() => setRejecting(false)}>Back</button>
              </div>
            </form>
          ) : (
            <div className="space-y-3">
              <input className="input" aria-label="Note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note (optional)" />
              <div className="flex gap-2">
                <button className="btn-primary" disabled={decide.isPending} onClick={() => decide.mutate("approve")}>{approveLabel}</button>
                <button className="btn-secondary" onClick={() => setRejecting(true)}>{rejectLabel}</button>
              </div>
            </div>
          )}
          <div className="mt-3"><ErrorNote error={decide.error} /></div>
        </Section>
      )}

      {a.can_cancel && (
        <div className="flex items-center justify-end gap-3">
          <ErrorNote error={cancel.error} />
          <button className="btn-ghost" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Withdraw request</button>
        </div>
      )}
    </div>
  );
}

function Subject({ a }: { a: Detail }) {
  const s = a.subject;
  if (a.kind === "patch_review") {
    return (
      <Section title={`Proposed change · ${s.status}`}>
        <p className="text-sm text-slate-700">{s.reason}</p>
        <p className="mt-1 text-xs text-slate-500">By {s.author.name || s.author.id} · based on version {s.base_version}</p>
        <ul className="mt-3 space-y-1.5" data-testid="patch-ops">
          {(s.ops as { op: string; path: string; value?: unknown }[]).map((op, i) => (
            <li key={i} className="rounded bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">
              <span className="font-semibold">{op.op}</span> {op.path}
              {op.value !== undefined && <span className="block break-all text-slate-500">{JSON.stringify(op.value)}</span>}
            </li>
          ))}
        </ul>
      </Section>
    );
  }
  if (a.kind === "story_signoff") {
    const stories = s.stories as StoryRow[];
    const moved = s.current_version !== s.ir_version;
    return (
      <Section title={`${stories.length} stories at version ${s.ir_version}`}>
        {moved && a.status === "pending" && (
          <p className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
            The stories changed after this request (now version {s.current_version}). Ask {a.requested_by.name} to send it again.
          </p>
        )}
        <ul className="divide-y divide-slate-100">
          {stories.map((st) => (
            <li key={st.story_id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <Link to={`/ideas/${a.idea_id}/stories/${st.story_id}`} className="text-slate-800 hover:text-accent-700 hover:underline">{st.title}</Link>
              <DorChip status={st.dor_status} />
            </li>
          ))}
        </ul>
      </Section>
    );
  }
  if (a.kind === "suggestion") {
    const x = s.suggestion as Suggestion | null;
    if (!x) return null;
    return (
      <Section title={`Suggestion ${x.suggestion_id} · ${x.status}`}>
        <p className="text-sm text-slate-700">{x.change_summary}</p>
        <p className="mt-2 text-sm text-slate-600"><span className="font-medium">Why:</span> {x.rationale}</p>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
          <div><dt className="label">Saves</dt><dd>{x.benefit.hours_saved_per_month != null ? `${x.benefit.hours_saved_per_month} h/month` : x.benefit.qualitative ?? "—"}</dd></div>
          <div><dt className="label">Human control</dt><dd>{x.controls}</dd></div>
          {x.risk && <div><dt className="label">Risk</dt><dd>{x.risk}</dd></div>}
        </dl>
      </Section>
    );
  }
  return (
    <Section title="Question">
      <p className="text-sm font-medium text-slate-900">{s.text}</p>
      {s.context && <p className="mt-1 text-sm text-slate-500">{s.context}</p>}
      {s.answer && <p className="mt-3 text-sm text-slate-700"><span className="font-medium">Answer:</span> {s.answer.text}</p>}
    </Section>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { ErrorNote, Loading, Section } from "../components/ui";
import type { Overview, Suggestion } from "../types";

export default function Improvements({ idea }: { idea: Overview }) {
  const qc = useQueryClient();
  const key = ["suggestions", idea.idea_id];
  const suggestions = useQuery({ queryKey: key, queryFn: () => api.get<Suggestion[]>(`/ideas/${idea.idea_id}/suggestions`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["idea", idea.idea_id] }); };
  const generate = useMutation({ mutationFn: () => api.post(`/ideas/${idea.idea_id}/suggestions:generate`), onSuccess: refresh });
  if (suggestions.isLoading) return <Loading />;
  if (suggestions.error) return <ErrorNote error={suggestions.error} />;
  const open = suggestions.data!.filter((s) => !["accepted", "rejected"].includes(s.status));
  const decided = suggestions.data!.filter((s) => ["accepted", "rejected"].includes(s.status));
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">
          {idea.stats.suggestions_accepted} accepted · {idea.stats.suggestions_rejected} rejected ·
          about <strong>{idea.stats.hours_saved_per_month ?? 0} analyst hours a month</strong> saved
        </p>
        <button className="btn-secondary" disabled={!idea.to_be_process_id || generate.isPending} onClick={() => generate.mutate()}>
          Suggest more improvements
        </button>
      </div>
      <ErrorNote error={generate.error} />
      {open.length > 0 && <div className="space-y-4">{open.map((s) => <Card key={s.suggestion_id} idea={idea} s={s} onChange={refresh} />)}</div>}
      <Section title={`Decided (${decided.length})`}>
        <ul className="divide-y divide-slate-100">
          {decided.map((s) => (
            <li key={s.suggestion_id} className="flex items-start justify-between gap-4 py-3 text-sm">
              <div>
                <span className="mr-2 text-xs text-slate-400">{s.suggestion_id}</span>
                <span className="font-medium text-slate-900">{s.title}</span>
                {s.decision?.reason && <p className="mt-1 text-xs text-slate-500">Reason: {s.decision.reason}</p>}
              </div>
              <div className="text-right">
                <span className={`chip ${s.status === "accepted" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{s.status}</span>
                <div className="mt-1 text-xs text-slate-500">{s.benefit.hours_saved_per_month != null ? `${s.benefit.hours_saved_per_month} h/month` : "—"}</div>
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Card({ idea, s, onChange }: { idea: Overview; s: Suggestion; onChange: () => void }) {
  const [mode, setMode] = useState<"idle" | "reject" | "edit">("idle");
  const [text, setText] = useState("");
  const base = `/ideas/${idea.idea_id}/suggestions/${s.suggestion_id}`;
  const act = useMutation({
    mutationFn: (kind: "accept" | "reject" | "edit") =>
      api.post(`${base}/${kind}`, kind === "reject" ? { reason: text } : kind === "edit" ? { instruction: text } : {}),
    onSuccess: () => { setMode("idle"); setText(""); onChange(); },
  });
  const b = s.benefit;
  return (
    <article className="card p-5" data-testid={`suggestion-${s.suggestion_id}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-slate-400">{s.suggestion_id} · {s.kind.replaceAll("_", " ")}{s.status === "edited" ? " · edited" : ""}</p>
          <h3 className="mt-1 font-semibold text-slate-900">{s.title}</h3>
        </div>
        <div className="text-right text-sm">
          <div className="font-semibold text-slate-900">{b.hours_saved_per_month != null ? `${b.hours_saved_per_month} h/month` : "—"}</div>
          <div className="text-xs text-slate-500">{b.minutes_saved_per_case != null ? `${b.minutes_saved_per_case} min per client` : b.qualitative}</div>
        </div>
      </div>
      <p className="mt-3 text-sm text-slate-700">{s.change_summary}</p>
      <p className="mt-2 text-sm text-slate-600"><span className="font-medium">Why:</span> {s.rationale}</p>
      <ul className="mt-2 space-y-1">
        {s.evidence.map((e, i) => <li key={i} className="text-xs italic text-slate-500">“{e.excerpt}” — {e.locator}</li>)}
      </ul>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        <div><dt className="label">Human control</dt><dd>{s.controls}</dd></div>
        {s.risk && <div><dt className="label">Risk</dt><dd>{s.risk}</dd></div>}
      </dl>
      {mode !== "idle" && (
        <div className="mt-4 flex gap-2">
          <input className="input" autoFocus value={text} onChange={(e) => setText(e.target.value)}
                 placeholder={mode === "reject" ? "One-line reason" : "e.g. Do it, but have an analyst review every rejection"} />
          <button className="btn-primary" disabled={!text.trim() || act.isPending} onClick={() => act.mutate(mode)}>
            {mode === "reject" ? "Reject" : "Revise"}
          </button>
          <button className="btn-ghost" onClick={() => setMode("idle")}>Cancel</button>
        </div>
      )}
      <ErrorNote error={act.error} />
      {mode === "idle" && (
        <div className="mt-4 flex gap-2">
          <button className="btn-primary" disabled={act.isPending} onClick={() => act.mutate("accept")}>Accept</button>
          <button className="btn-secondary" onClick={() => setMode("reject")}>Reject</button>
          <button className="btn-ghost" onClick={() => setMode("edit")}>Edit</button>
        </div>
      )}
    </article>
  );
}

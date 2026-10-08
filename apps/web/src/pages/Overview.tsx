import { Link } from "react-router-dom";
import { Meter, Section } from "../components/ui";
import type { Overview as OverviewData } from "../types";

export default function Overview({ idea }: { idea: OverviewData }) {
  const s = idea.stats;
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Section title="Summary"><p className="text-sm leading-relaxed text-slate-700">{idea.summary}</p></Section>
        <Section title="Goals">
          {idea.goals.length === 0 ? <p className="text-sm text-slate-500">No goals captured yet.</p> : (
            <ul className="space-y-3">
              {idea.goals.map((g) => (
                <li key={g.id}>
                  <p className="text-sm font-medium text-slate-900">{g.statement}</p>
                  <p className="text-xs text-slate-500">
                    {g.metrics.map((m) => `${m.name}: ${m.baseline ?? "?"} → ${m.target ?? "?"} ${m.unit ?? ""}`).join(" · ") || "No metric yet"}
                    {g.beneficiaries.length > 0 && ` · benefits ${g.beneficiaries.join(", ")}`}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Scope">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="label">In</dt>{idea.scope.in.map((x) => <dd key={x}>{x}</dd>)}</div>
            <div><dt className="label">Out</dt>{idea.scope.out.map((x) => <dd key={x}>{x}</dd>)}</div>
          </dl>
        </Section>
        <Section title="Non-functional requirements">
          {idea.nfrs.length === 0 ? <p className="text-sm text-slate-500">None captured yet.</p> : (
            <ul className="space-y-1 text-sm">
              {idea.nfrs.map((n) => <li key={n.id}><span className="chip mr-2 bg-slate-100 text-slate-600">{n.category}</span>{n.statement}</li>)}
            </ul>
          )}
        </Section>
      </div>
      <div className="space-y-6">
        <Section title="Readiness">
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between"><dt>Coverage</dt><dd><Meter value={s.coverage} /></dd></div>
            <div className="flex justify-between"><dt>Stories ready</dt><dd>{s.stories_ready} / {s.stories}</dd></div>
            {idea.has_as_is && <div className="flex justify-between"><dt>Hours saved a month</dt><dd>{s.hours_saved_per_month ?? "—"}</dd></div>}
          </dl>
          <Link to="conversation" className="btn-secondary mt-4 w-full justify-center">Continue conversation</Link>
        </Section>
        <Section title="Beneficiaries">
          <p className="text-sm text-slate-700">{idea.beneficiaries.join(", ") || "—"}</p>
        </Section>
        <Section title={`Open questions (${idea.open_questions.length})`}>
          <ul className="space-y-2 text-sm">
            {idea.open_questions.slice(0, 8).map((q) => (
              <li key={`${q.story_id}-${q.gap_id}`}>
                <Link to={`stories/${q.story_id}`} className="text-slate-800 hover:text-accent-700">{q.text}</Link>
                <span className="block text-xs text-slate-500">{q.severity} · {q.status}{q.asked_to && ` · waiting on ${q.asked_to}`}</span>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </div>
  );
}

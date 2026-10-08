import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import FlowThumbnail from "../components/FlowThumbnail";
import { ErrorNote, Loading, Meter, StatusChip } from "../components/ui";
import type { IdeaSummary } from "../types";

const STATUSES = ["discovering", "improving", "refining", "ready", "exported"];

function when(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export default function IdeasList() {
  const [status, setStatus] = useState("");
  const [owner, setOwner] = useState("");
  const [q, setQ] = useState("");
  const params = new URLSearchParams(Object.entries({ status, owner, q }).filter(([, v]) => v));
  const ideas = useQuery({ queryKey: ["ideas", params.toString()], queryFn: () => api.get<IdeaSummary[]>(`/ideas?${params}`) });
  const all = useQuery({ queryKey: ["ideas", ""], queryFn: () => api.get<IdeaSummary[]>("/ideas") });
  const owners = [...new Set((all.data ?? []).map((i) => i.owner_user_id))];

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Ideas</h1>
          <p className="mt-1 text-sm text-slate-500">Each idea holds its conversation, process flows, stories and exports.</p>
        </div>
        <Link to="/ideas/new" className="btn-primary">New idea</Link>
      </div>

      <div className="flex flex-wrap gap-3">
        <input className="input max-w-sm" placeholder="Search titles and summaries" value={q}
               onChange={(e) => setQ(e.target.value)} aria-label="Search ideas" />
        <select className="input w-44" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="input w-52" value={owner} onChange={(e) => setOwner(e.target.value)} aria-label="Owner">
          <option value="">All owners</option>
          {owners.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>

      <ErrorNote error={ideas.error} />
      {ideas.isLoading ? <Loading /> : (
        <ul className="space-y-3" aria-label="Ideas">
          {ideas.data?.length === 0 && <li className="card p-8 text-center text-sm text-slate-500">No ideas match.</li>}
          {ideas.data?.map((idea) => <IdeaRow key={idea.idea_id} idea={idea} />)}
        </ul>
      )}
    </div>
  );
}

function IdeaRow({ idea }: { idea: IdeaSummary }) {
  const s = idea.stats;
  return (
    <li>
      <Link to={`/ideas/${idea.idea_id}`} data-testid={`idea-${idea.idea_id}`}
            className="card flex gap-5 p-5 transition-shadow hover:shadow-sm">
        <FlowThumbnail thumb={idea.thumbnail} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <h2 className="truncate font-semibold text-slate-900">{idea.title}</h2>
            <StatusChip status={idea.status} />
          </div>
          <p className="mt-1 line-clamp-2 text-sm text-slate-600">{idea.summary}</p>
          <p className="mt-2 text-xs text-slate-500">{idea.owner_user_id} · updated {when(idea.updated_at)}</p>
        </div>
        <dl className="grid w-[26rem] shrink-0 grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <div><dt className="label">Coverage</dt><dd><Meter value={s.coverage} label="Coverage" /></dd></div>
          <div><dt className="label">Stories ready</dt><dd data-testid="stories-ready">{s.stories_ready} / {s.stories}</dd></div>
          <div><dt className="label">Improvement</dt>
            <dd data-testid="improvement">{s.suggestions_accepted + s.suggestions_rejected > 0
              ? `${s.suggestions_accepted}/${s.suggestions_accepted + s.suggestions_rejected} accepted · ~${s.hours_saved_per_month} h/month`
              : "—"}</dd></div>
          <div><dt className="label">Open questions</dt>
            <dd data-testid="open-questions">{s.open_questions}{idea.waiting_on.length > 0 && (
              <span className="text-slate-500"> · waiting on {idea.waiting_on.length > 2
                ? `${idea.waiting_on.length} people` : idea.waiting_on.join(", ")}</span>)}</dd></div>
        </dl>
      </Link>
    </li>
  );
}

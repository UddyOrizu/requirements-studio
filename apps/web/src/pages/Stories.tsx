import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ConfidenceChip, DorChip, ErrorNote, Loading } from "../components/ui";
import { PRIORITY_LABEL } from "../hooks";
import type { Overview, StoryRow } from "../types";

export default function Stories({ idea }: { idea: Overview }) {
  const stories = useQuery({ queryKey: ["stories", idea.idea_id], queryFn: () => api.get<StoryRow[]>(`/ideas/${idea.idea_id}/stories`) });
  const [priority, setPriority] = useState("");
  const [control, setControl] = useState("");
  const [dor, setDor] = useState("");
  const [openOnly, setOpenOnly] = useState(false);
  if (stories.isLoading) return <Loading />;
  if (stories.error) return <ErrorNote error={stories.error} />;
  const rows = stories.data!.filter((s) => (!priority || (s.priority ?? "none") === priority)
    && (!control || s.control === control) && (!dor || s.dor_status === dor) && (!openOnly || s.open_questions > 0));
  const controls = [...new Set(stories.data!.map((s) => s.control))];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select className="input w-40" value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority">
          <option value="">Any priority</option>
          {Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          <option value="none">Not set</option>
        </select>
        <select className="input w-56" value={control} onChange={(e) => setControl(e.target.value)} aria-label="Control">
          <option value="">Any control</option>
          {controls.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select className="input w-40" value={dor} onChange={(e) => setDor(e.target.value)} aria-label="DoR">
          <option value="">Any DoR</option><option value="ready">ready</option><option value="not_ready">not ready</option><option value="waived">waived</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Has open questions
        </label>
        <a className="btn-ghost ml-auto" href={`/api/v1/ideas/${idea.idea_id}/stories.md`} target="_blank" rel="noreferrer">View as markdown</a>
      </div>
      <table className="card w-full overflow-hidden text-sm" data-testid="stories-table">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Story</th><th className="px-4 py-2">Priority</th><th className="px-4 py-2">Control</th>
            <th className="px-4 py-2">Confidence</th><th className="px-4 py-2">DoR</th><th className="px-4 py-2">Open questions</th>
            <th className="px-4 py-2">Change from today</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.story_id} className="border-t border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-2">
                <Link to={s.story_id} className="font-medium text-slate-900 hover:text-accent-700">{s.title}</Link>
                <div className="text-xs text-slate-400">{s.story_id}</div>
              </td>
              <td className="px-4 py-2">{s.priority ? PRIORITY_LABEL[s.priority] : <span className="text-slate-400">Not set</span>}</td>
              <td className="px-4 py-2">{s.control}</td>
              <td className="px-4 py-2"><ConfidenceChip band={s.band} value={s.confidence} /></td>
              <td className="px-4 py-2"><DorChip status={s.dor_status} /></td>
              <td className="px-4 py-2 tabular-nums">{s.open_questions}</td>
              <td className="px-4 py-2 text-slate-600">{s.change ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

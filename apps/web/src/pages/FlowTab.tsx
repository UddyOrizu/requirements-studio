import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, download } from "../api";
import FlowCanvas from "../components/FlowCanvas";
import { ErrorNote, Loading } from "../components/ui";
import type { Flow, Overview } from "../types";

type View = "as_is" | "to_be" | "compare";

interface CompareRow { node_id: string | null; step: string; today: string; minutes_today: number | null; to_be: string; change: string }

export default function FlowTab({ idea }: { idea: Overview }) {
  const navigate = useNavigate();
  const both = Boolean(idea.as_is_process_id && idea.to_be_process_id);
  const [view, setView] = useState<View>(idea.to_be_process_id ? "to_be" : "as_is");
  const variant = view === "compare" ? "to_be" : view;
  const flow = useQuery({ queryKey: ["flow", idea.idea_id, variant], queryFn: () => api.get<Flow>(`/ideas/${idea.idea_id}/flow?variant=${variant}`), enabled: view !== "compare" });
  const compare = useQuery({ queryKey: ["compare", idea.idea_id], queryFn: () => api.get<{ rows: CompareRow[]; as_is: Flow; to_be: Flow }>(`/ideas/${idea.idea_id}/flow/compare`), enabled: view === "compare" });
  const [copied, setCopied] = useState(false);
  const views: [View, string][] = [
    ...(idea.as_is_process_id ? [["as_is", "As-is"] as [View, string]] : []),
    ...(idea.to_be_process_id ? [["to_be", "To-be"] as [View, string]] : []),
    ...(both ? [["compare", "Compare"] as [View, string]] : []),
  ];
  const openStory = (sid: string) => navigate(`/ideas/${idea.idea_id}/stories/${sid}`);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div role="tablist" aria-label="Flow view" className="inline-flex rounded-md border border-slate-300 bg-white p-0.5">
          {views.map(([v, label]) => (
            <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
                    className={`rounded px-3 py-1 text-sm ${view === v ? "bg-accent-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
              {label}
            </button>
          ))}
        </div>
        {view !== "compare" && (
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={() => download(`/ideas/${idea.idea_id}/flow?variant=${variant}&format=drawio`, `${variant}_process_flow.drawio`)}>
              Download for Lucidchart
            </button>
            <button className="btn-secondary" onClick={async () => {
              await navigator.clipboard.writeText(await api.text(`/ideas/${idea.idea_id}/flow?variant=${variant}&format=mermaid`));
              setCopied(true); setTimeout(() => setCopied(false), 1500);
            }}>{copied ? "Copied" : "Copy Mermaid"}</button>
          </div>
        )}
      </div>

      {view === "compare" ? (
        compare.isLoading ? <Loading /> : compare.error ? <ErrorNote error={compare.error} /> : (
          <div className="space-y-4">
            <table className="card w-full overflow-hidden text-sm" data-testid="compare-table">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr><th className="px-4 py-2">Step</th><th className="px-4 py-2">Today</th><th className="px-4 py-2">Minutes today</th><th className="px-4 py-2">To-be</th><th className="px-4 py-2">Change</th></tr>
              </thead>
              <tbody>
                {compare.data!.rows.map((r) => (
                  <tr key={r.step} className={`border-t border-slate-100 ${r.change !== "Unchanged" ? "bg-accent-50/50" : ""}`}>
                    <td className="px-4 py-2 font-medium text-slate-900">{r.step}</td>
                    <td className="px-4 py-2">{r.today}</td>
                    <td className="px-4 py-2 tabular-nums">{r.minutes_today ?? "—"}</td>
                    <td className="px-4 py-2">{r.to_be}</td>
                    <td className="px-4 py-2">{r.change}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="grid gap-4 xl:grid-cols-2">
              <div><p className="label mb-2">As-is</p><FlowCanvas flow={compare.data!.as_is} height={380} /></div>
              <div><p className="label mb-2">To-be (changed steps highlighted)</p>
                <FlowCanvas flow={compare.data!.to_be} height={380} onOpenStory={openStory}
                            highlight={compare.data!.rows.filter((r) => r.change !== "Unchanged" && r.node_id).map((r) => r.node_id!)} /></div>
            </div>
          </div>
        )
      ) : flow.isLoading ? <Loading /> : flow.error ? <ErrorNote error={flow.error} /> : (
        <>
          <p className="text-sm text-slate-500">{flow.data!.title}. Click a step to open its story.</p>
          <FlowCanvas flow={flow.data!} onOpenStory={openStory} height={560} />
        </>
      )}
    </div>
  );
}

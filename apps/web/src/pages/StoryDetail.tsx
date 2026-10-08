import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { marked } from "marked";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ConfidenceChip, DorChip, ErrorNote, Loading, Section } from "../components/ui";
import { PRIORITY_LABEL } from "../hooks";
import type { HistoryEntry, Overview, StoryDetail as Story } from "../types";

interface Preview {
  kind: "preview" | "answer" | "clarify"; preview_id?: string; summary: string[]; answer?: string; question?: string;
  story_before?: string; stories_after?: Record<string, string>; flow_changes?: string[]; ops?: unknown[];
}

const md = (text: string) => ({ __html: marked.parse(text, { async: false }) as string });

export default function StoryDetail({ idea }: { idea: Overview }) {
  const { storyId = "" } = useParams();
  const qc = useQueryClient();
  const base = `/ideas/${idea.idea_id}/stories/${storyId}`;
  const story = useQuery({ queryKey: ["story", idea.idea_id, storyId], queryFn: () => api.get<Story>(base) });
  const history = useQuery({ queryKey: ["history", idea.idea_id, storyId], queryFn: () => api.get<HistoryEntry[]>(`${base}/history`) });
  const refreshAll = () => {
    for (const k of [["story", idea.idea_id], ["history", idea.idea_id], ["stories", idea.idea_id], ["idea", idea.idea_id], ["flow", idea.idea_id]]) {
      qc.invalidateQueries({ queryKey: k });
    }
  };
  if (story.isLoading) return <Loading />;
  if (story.error) return <ErrorNote error={story.error} />;
  const s = story.data!;
  return (
    <div className="space-y-4">
      <Link to={`/ideas/${idea.idea_id}/stories`} className="text-sm text-slate-500 hover:text-slate-800">← All stories</Link>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          <Header idea={idea} s={s} onChange={refreshAll} />
          <article className="card prose-story p-6" data-testid="story-markdown" dangerouslySetInnerHTML={md(s.markdown)} />
          <AcceptanceCriteria idea={idea} s={s} onChange={refreshAll} />
        </div>
        <div className="space-y-6">
          <Refine idea={idea} storyId={storyId} onApplied={refreshAll} />
          <Ask idea={idea} storyId={storyId} onAsked={refreshAll} />
          <History idea={idea} entries={history.data ?? []} onUndone={refreshAll} />
        </div>
      </div>
    </div>
  );
}

function useEdit(idea: Overview, storyId: string, onChange: () => void) {
  return useMutation({
    mutationFn: (body: object) => api.post(`/ideas/${idea.idea_id}/stories/${storyId}/edit`, body),
    onSuccess: onChange,
  });
}

function Header({ idea, s, onChange }: { idea: Overview; s: Story; onChange: () => void }) {
  const edit = useEdit(idea, s.story_id, onChange);
  const [outcome, setOutcome] = useState(s.editable.outcome ?? "");
  return (
    <section className="card space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-2 text-lg font-semibold text-slate-900">{s.title}</h2>
        <ConfidenceChip band={s.band} value={s.confidence} /><DorChip status={s.dor_status} />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="space-y-1"><span className="label">Priority</span>
          <select className="input" aria-label="Priority" value={s.priority ?? ""} onChange={(e) => edit.mutate({ field: "priority", value: e.target.value })}>
            <option value="" disabled>Not set</option>
            {Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="space-y-1"><span className="label">Control</span>
          <select className="input" aria-label="Control" value={s.editable.hitl.mode ?? ""}
                  onChange={(e) => edit.mutate({ field: "control_mode", value: e.target.value === "approval"
                    ? { mode: "approval", criteria: window.prompt("What does the approver check?") ?? "" } : e.target.value })}>
            <option value="" disabled>Not set</option>
            <option value="automated">Automated</option><option value="hitl_review">Automated + human review</option>
            <option value="human_task">Human task</option><option value="approval">Approval gate</option>
          </select>
        </label>
        <form className="space-y-1 sm:col-span-3" onSubmit={(e) => { e.preventDefault(); edit.mutate({ field: "outcome", value: outcome }); }}>
          <span className="label">Outcome (the "so that")</span>
          <div className="flex gap-2">
            <input className="input" value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Outcome" />
            <button className="btn-secondary" disabled={outcome === (s.editable.outcome ?? "") || edit.isPending}>Save</button>
          </div>
        </form>
      </div>
      <ErrorNote error={edit.error} />
      {s.dor_status !== "ready" && s.failed_checks.length > 0 && (
        <p className="text-xs text-slate-500">Not ready: {s.dor.checks.filter((c) => !c.passed).map((c) => `${c.check_id} ${c.message}`).join(" · ")}</p>
      )}
    </section>
  );
}

function AcceptanceCriteria({ idea, s, onChange }: { idea: Overview; s: Story; onChange: () => void }) {
  const edit = useEdit(idea, s.story_id, onChange);
  const [editing, setEditing] = useState<{ ac: string; part: "given" | "when" | "then"; text: string } | null>(null);
  return (
    <Section title="Edit acceptance criteria">
      <ul className="space-y-3 text-sm">
        {Object.entries(s.editable.acceptance_criteria).map(([id, ac]) => (
          <li key={id}>
            <p className="font-medium text-slate-900">{ac.title} <span className="text-xs text-slate-400">{id}</span></p>
            {(["given", "when", "then"] as const).map((part) => (
              editing?.ac === id && editing.part === part ? (
                <form key={part} className="mt-1 flex gap-2" onSubmit={(e) => {
                  e.preventDefault();
                  edit.mutate({ field: "acceptance_criterion", ac_id: id, part, value: editing.text.split("\n").filter((l) => l.trim()) },
                    { onSuccess: () => setEditing(null) });
                }}>
                  <textarea className="input" value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} aria-label={`${part} lines`} />
                  <button className="btn-secondary">Save</button>
                </form>
              ) : (
                <button key={part} className="mt-1 block text-left text-slate-600 hover:text-slate-900"
                        onClick={() => setEditing({ ac: id, part, text: ac[part].join("\n") })}>
                  <span className="mr-1 font-medium capitalize text-slate-500">{part}</span>{ac[part].join(" · ")}
                </button>
              )
            ))}
          </li>
        ))}
      </ul>
      <ErrorNote error={edit.error} />
    </Section>
  );
}

function Refine({ idea, storyId, onApplied }: { idea: Overview; storyId: string; onApplied: () => void }) {
  const [instruction, setInstruction] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const base = `/ideas/${idea.idea_id}/stories/${storyId}`;
  const ask = useMutation({ mutationFn: () => api.post<Preview>(`${base}/refine`, { instruction }), onSuccess: setPreview });
  const apply = useMutation({
    mutationFn: () => api.post(`${base}/refine/${preview!.preview_id}/apply`),
    onSuccess: () => { setPreview(null); setInstruction(""); onApplied(); },
  });
  return (
    <Section title="Refine this story">
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); setPreview(null); ask.mutate(); }}>
        <textarea className="input min-h-20" value={instruction} onChange={(e) => setInstruction(e.target.value)} aria-label="Refine instruction"
                  placeholder="e.g. Add what happens if the CRM is down" />
        <button className="btn-primary" disabled={!instruction.trim() || ask.isPending}>{ask.isPending ? "Thinking…" : "Preview change"}</button>
      </form>
      <div className="mt-3"><ErrorNote error={ask.error ?? apply.error} /></div>
      {preview?.kind === "answer" && <p className="mt-3 rounded-md bg-slate-50 p-3 text-sm text-slate-700" data-testid="refine-answer">{preview.answer}</p>}
      {preview?.kind === "clarify" && <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm text-amber-900">{preview.question}</p>}
      {preview?.kind === "preview" && (
        <div className="mt-4 space-y-3" data-testid="refine-preview">
          <ul className="list-disc pl-5 text-sm text-slate-700">{preview.summary.map((x) => <li key={x}>{x}</li>)}</ul>
          {preview.flow_changes && preview.flow_changes.length > 0 && (
            <div><p className="label">Flow changes</p>
              <ul className="list-disc pl-5 text-sm text-slate-700">{preview.flow_changes.map((x) => <li key={x}>{x}</li>)}</ul></div>
          )}
          <details className="text-sm"><summary className="cursor-pointer text-slate-600">Story before</summary>
            <div className="prose-story mt-2 rounded border border-slate-200 p-3" dangerouslySetInnerHTML={md(preview.story_before ?? "")} /></details>
          {Object.entries(preview.stories_after ?? {}).map(([sid, text]) => (
            <details key={sid} open className="text-sm"><summary className="cursor-pointer text-slate-600">After: {sid}</summary>
              <div className="prose-story mt-2 rounded border border-accent-100 bg-accent-50/30 p-3" dangerouslySetInnerHTML={md(text)} /></details>
          ))}
          <div className="flex gap-2">
            <button className="btn-primary" disabled={apply.isPending} onClick={() => apply.mutate()}>Apply</button>
            <button className="btn-ghost" onClick={() => setPreview(null)}>Discard</button>
          </div>
        </div>
      )}
    </Section>
  );
}

function Ask({ idea, storyId, onAsked }: { idea: Overview; storyId: string; onAsked: () => void }) {
  const smes = useQuery({ queryKey: ["smes"], queryFn: () => api.get<{ sme_id: string; name: string; role_title: string }[]>("/smes") });
  const [text, setText] = useState("");
  const [sme, setSme] = useState("");
  const ask = useMutation({
    mutationFn: () => api.post<{ captured: string }>(`/ideas/${idea.idea_id}/stories/${storyId}/ask`, { text, sme_id: sme }),
    onSuccess: () => { setText(""); onAsked(); },
  });
  return (
    <Section title="Ask someone">
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); ask.mutate(); }}>
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Your question" aria-label="Question" />
        <div className="flex gap-2">
          <select className="input" value={sme} onChange={(e) => setSme(e.target.value)} aria-label="Who">
            <option value="">Choose who…</option>
            {smes.data?.map((m) => <option key={m.sme_id} value={m.sme_id}>{m.name} ({m.role_title})</option>)}
          </select>
          <button className="btn-secondary" disabled={!text.trim() || !sme || ask.isPending}>Ask</button>
        </div>
      </form>
      {ask.data && <p className="mt-2 text-xs text-emerald-700">{ask.data.captured}</p>}
      <ErrorNote error={ask.error} />
    </Section>
  );
}

function History({ idea, entries, onUndone }: { idea: Overview; entries: HistoryEntry[]; onUndone: () => void }) {
  const undo = useMutation({ mutationFn: (pid: string) => api.post(`/ideas/${idea.idea_id}/patches/${pid}/undo`), onSuccess: onUndone });
  return (
    <Section title="Version history">
      <ErrorNote error={undo.error} />
      <ol className="divide-y divide-slate-100" data-testid="history">
        {entries.map((h) => (
          <li key={h.patch_id} className="flex items-start justify-between gap-3 py-2 text-sm">
            <div>
              <p className="text-slate-800">{h.reason}</p>
              <p className="text-xs text-slate-500">v{h.version} · {h.author.id}</p>
            </div>
            {!h.reason.startsWith("Undo ") && (
              <button className="btn-ghost shrink-0" disabled={undo.isPending} onClick={() => undo.mutate(h.patch_id)}>Undo</button>
            )}
          </li>
        ))}
      </ol>
    </Section>
  );
}

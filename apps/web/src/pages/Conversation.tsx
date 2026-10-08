import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import FlowCanvas from "../components/FlowCanvas";
import { ErrorNote, Loading, Meter } from "../components/ui";
import type { Flow, IntakeSession, Overview, StoryRow, TimelineEntry } from "../types";

const SLOT_NAMES: Record<string, string> = {
  C01: "Goal", C02: "Success metric", C03: "Beneficiaries", C04: "Trigger", C05: "Outcome", C06: "Steps", C07: "Who",
  C08: "Decisions", C09: "Exceptions", C10: "Data", C11: "Systems", C12: "Volume", C13: "Timing", C14: "Security & audit",
  C15: "Scope", C16: "Human checkpoints", C17: "Effort & pain points",
};
const STANDARD = ["Other…", "Not sure — ask someone", "Skip for now"];

// The M0 intake workspace (M0 §4): conversation · live process · coverage, stories and questions.
export default function Conversation({ idea }: { idea: Overview }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const key = ["session", idea.session_id];
  const session = useQuery({ queryKey: key, queryFn: () => api.get<IntakeSession>(`/intake-sessions/${idea.session_id}`), retry: false });
  const flow = useQuery({ queryKey: ["flow", idea.idea_id, "live"], queryFn: () => api.get<Flow>(`/ideas/${idea.idea_id}/flow`) });
  const [text, setText] = useState("");
  const [askSme, setAskSme] = useState("");
  const smes = useQuery({ queryKey: ["smes"], queryFn: () => api.get<{ sme_id: string; name: string; role_title: string }[]>("/smes") });
  const answer = useMutation({
    mutationFn: (body: object) => api.post(`/intake-sessions/${idea.session_id}/answers`, body),
    onSuccess: () => {
      setText(""); setAskSme("");
      qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["flow", idea.idea_id] });
      qc.invalidateQueries({ queryKey: ["idea", idea.idea_id] }); qc.invalidateQueries({ queryKey: ["stories", idea.idea_id] });
    },
  });
  const signOff = useMutation({
    mutationFn: () => api.post(`/intake-sessions/${idea.session_id}/signoff`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["idea", idea.idea_id] }); },
  });
  const undo = useMutation({
    mutationFn: (seq: number) => api.post(`/intake-sessions/${idea.session_id}/turns/${seq}/undo`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["flow", idea.idea_id] }); },
  });

  if (session.isLoading) return <Loading />;
  if (session.error) {
    return <p className="card p-6 text-sm text-slate-500">This idea was started from documents; it has no conversation yet.</p>;
  }
  const s = session.data!;
  const q = s.next_question;
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)_16rem]">
      <section className="card flex max-h-[44rem] flex-col" aria-label="Conversation">
        <ol className="flex-1 space-y-4 overflow-y-auto p-4">
          {s.timeline.map((e) => <Entry key={e.seq} e={e} onUndo={() => undo.mutate(e.seq)} />)}
        </ol>
        <div className="border-t border-slate-200 p-4">
          <ErrorNote error={answer.error ?? undo.error ?? signOff.error} />
          {q?.text ? (
            <div className="space-y-3" data-testid="open-question">
              <div>
                <p className="text-sm font-medium text-slate-900">{q.text}</p>
                {q.why && <p className="mt-1 text-xs text-slate-500">Why I'm asking: {q.why}</p>}
              </div>
              <div className="flex flex-wrap gap-2">
                {q.suggested_answers.filter((a) => !STANDARD.includes(a)).map((a) => (
                  <button key={a} className="btn-secondary" disabled={answer.isPending} onClick={() => answer.mutate({ choice: a })}>{a}</button>
                ))}
                <button className="btn-ghost" disabled={answer.isPending} onClick={() => answer.mutate({ special: "skip" })}>Skip for now</button>
              </div>
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); answer.mutate(askSme ? { text: text || undefined, special: "not_sure_ask", ask_sme_id: askSme } : { text }); }}>
                <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your answer…" aria-label="Your answer" />
                <button className="btn-primary" disabled={(!text.trim() && !askSme) || answer.isPending}>Send</button>
              </form>
              <label className="flex items-center gap-2 text-xs text-slate-500">
                Not sure — ask
                <select className="input w-56 py-1 text-xs" value={askSme} onChange={(e) => setAskSme(e.target.value)} aria-label="Ask someone">
                  <option value="">nobody</option>
                  {smes.data?.map((m) => <option key={m.sme_id} value={m.sme_id}>{m.name} ({m.role_title})</option>)}
                </select>
              </label>
            </div>
          ) : q?.target.kind === "signoff" ? (
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm text-slate-600">Every story is ready. Sign them off to mark the idea ready.</p>
              <button className="btn-primary" disabled={signOff.isPending} onClick={() => signOff.mutate()}>Sign off stories</button>
            </div>
          ) : (
            <p className="text-sm text-slate-500">{s.phase === "improve" ? "Waiting for the improvement decisions (Improvements tab)." : s.phase === "done" ? "This conversation is complete." : "No open question."}</p>
          )}
        </div>
      </section>

      <section aria-label="Live process" className="space-y-2">
        {flow.data ? <FlowCanvas flow={flow.data} height={600} onOpenStory={(sid) => navigate(`/ideas/${idea.idea_id}/stories/${sid}`)} /> : <Loading />}
        <p className="text-xs text-slate-500">
          Blue: automated · amber, thick border: AI with a person reviewing · white: a person does it · red hexagon:
          approval gate · dashed: a wait, a human queue, or a step whose control isn't set yet.
        </p>
      </section>

      <SidePanel idea={idea} session={s} />
    </div>
  );
}

function Entry({ e, onUndo }: { e: TimelineEntry; onUndo: () => void }) {
  if (e.kind === "phase_change") return <li className="text-center text-xs uppercase tracking-wide text-slate-400">{e.from_phase} → {e.to_phase}</li>;
  if (e.kind === "playback") return <li className="rounded-md bg-slate-50 p-3 text-sm text-slate-700"><span className="label block">Here's what I understand</span>{e.playback_text}</li>;
  return (
    <li className="space-y-2">
      {e.question && <p className="text-sm text-slate-800"><span className="mr-1 text-xs text-slate-400">{e.turn}</span>{e.question.text}</p>}
      {e.answer?.text && <p className="ml-6 rounded-md bg-accent-50 px-3 py-2 text-sm text-slate-800">{e.answer.text}</p>}
      {e.captured && e.captured.length > 0 && (
        <div className="ml-6 rounded-md border border-emerald-200 bg-emerald-50/60 p-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="label text-emerald-700">Captured</span>
            {e.patch_id && e.kind === "turn" && <button className="text-xs text-slate-500 hover:text-slate-800" onClick={onUndo}>Undo</button>}
          </div>
          <ul className="mt-1 list-disc pl-4 text-slate-700">{e.captured.map((c) => <li key={c}>{c}</li>)}</ul>
          {e.assumptions && e.assumptions.length > 0 && <p className="mt-2 text-xs text-slate-500">I assumed: {e.assumptions.join("; ")}</p>}
        </div>
      )}
    </li>
  );
}

function SidePanel({ idea, session }: { idea: Overview; session: IntakeSession }) {
  const [tab, setTab] = useState<"coverage" | "stories" | "questions">("coverage");
  const stories = useQuery({ queryKey: ["stories", idea.idea_id], queryFn: () => api.get<StoryRow[]>(`/ideas/${idea.idea_id}/stories`), enabled: tab === "stories" });
  const cov = session.coverage;
  return (
    <aside className="card p-4" aria-label="Coverage, stories and questions">
      <div className="mb-3 flex gap-1 text-sm">
        {(["coverage", "stories", "questions"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`rounded px-2 py-1 capitalize ${tab === t ? "bg-slate-100 font-medium text-slate-900" : "text-slate-500"}`}>{t}</button>
        ))}
      </div>
      {tab === "coverage" && (
        <div className="space-y-3">
          <Meter value={cov.percent ?? 0} label="Coverage" />
          <ul className="grid grid-cols-2 gap-1 text-xs">
            {[...(cov.filled ?? []), ...(cov.parked ?? []), ...(cov.unfilled ?? [])].map((slot) => {
              const state = cov.filled?.includes(slot) ? "✓" : cov.parked?.includes(slot) ? "⏸" : "○";
              return <li key={slot} className="text-slate-600"><span aria-hidden className="mr-1">{state}</span>{SLOT_NAMES[slot] ?? slot}</li>;
            })}
          </ul>
        </div>
      )}
      {tab === "stories" && (
        <ul className="space-y-2 text-sm">
          {stories.data?.map((s) => (
            <li key={s.story_id}>
              <span className="text-slate-800">{s.title}</span>
              <span className="block text-xs text-slate-500">{s.band} · DoR {s.dor_status.replace("_", " ")}{s.failed_checks.length > 0 && ` · missing ${s.failed_checks.join(", ")}`}</span>
            </li>
          ))}
        </ul>
      )}
      {tab === "questions" && (
        <ul className="space-y-2 text-sm">
          {idea.open_questions.filter((q) => q.asked_to).map((q) => (
            <li key={q.gap_id}>{q.text}<span className="block text-xs text-slate-500">waiting on {q.asked_to}</span></li>
          ))}
          {idea.open_questions.every((q) => !q.asked_to) && <li className="text-slate-500">No questions out.</li>}
        </ul>
      )}
    </aside>
  );
}

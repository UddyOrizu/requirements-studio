import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote } from "../components/ui";

const OPTIONS = [
  { value: "yes", label: "Yes", hint: "I'll capture how it works today first, then suggest improvements." },
  { value: "no", label: "No", hint: "We'll design the new process directly." },
  { value: "not_sure", label: "Not sure", hint: "We'll start with the idea; you can switch later." },
];

export default function NewIdea() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [answer, setAnswer] = useState("");
  const create = useMutation({
    mutationFn: () => api.post<{ idea_id: string }>("/ideas", { text, title: title || undefined, has_process_today: answer }),
    onSuccess: (r) => navigate(`/ideas/${r.idea_id}/conversation`),
  });
  return (
    <form className="mx-auto max-w-2xl space-y-6" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">New idea</h1>
        <p className="mt-1 text-sm text-slate-500">No documents needed. I'll ask one question at a time.</p>
      </div>
      <label className="block space-y-2">
        <span className="label">Title (optional)</span>
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Client KYC checks" />
      </label>
      <label className="block space-y-2">
        <span className="label">Describe your idea or the process you want to improve</span>
        <textarea className="input min-h-40" value={text} onChange={(e) => setText(e.target.value)} required
                  aria-label="Idea" placeholder="What takes too long today, and what would you like instead?" />
      </label>
      <fieldset className="space-y-2">
        <legend className="label">Is there a process today?</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {OPTIONS.map((o) => (
            <label key={o.value} className={`card cursor-pointer p-3 ${answer === o.value ? "border-accent-500 ring-1 ring-accent-500" : ""}`}>
              <input type="radio" name="has_process_today" value={o.value} className="sr-only" required
                     checked={answer === o.value} onChange={() => setAnswer(o.value)} />
              <div className="text-sm font-medium text-slate-900">{o.label}</div>
              <div className="mt-1 text-xs text-slate-500">{o.hint}</div>
            </label>
          ))}
        </div>
      </fieldset>
      <ErrorNote error={create.error} />
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={() => navigate("/")}>Cancel</button>
        <button className="btn-primary" disabled={!text.trim() || !answer || create.isPending}>
          {create.isPending ? "Starting…" : "Start the conversation"}
        </button>
      </div>
    </form>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, download } from "../api";
import { Section } from "../components/ui";
import type { Overview } from "../types";

interface Format { id: string; label: string; path: string; filename: string; preview: boolean }

export default function ExportTab({ idea }: { idea: Overview }) {
  const base = `/ideas/${idea.idea_id}`;
  const formats: Format[] = [
    { id: "stories", label: "User stories (Markdown)", path: `${base}/stories.md`, filename: "stories.md", preview: true },
    { id: "feature", label: "Acceptance tests (Gherkin .feature)", path: `${base}/features`, filename: "stories.feature", preview: true },
    ...(idea.to_be_process_id ? [
      { id: "tobe-drawio", label: "To-be flow for Lucidchart (.drawio)", path: `${base}/flow?variant=to_be&format=drawio`, filename: "to_be_process_flow.drawio", preview: false },
      { id: "tobe-mmd", label: "To-be flow (Mermaid)", path: `${base}/flow?variant=to_be&format=mermaid`, filename: "to_be_process_flow.mmd", preview: true },
    ] : []),
    ...(idea.as_is_process_id ? [
      { id: "asis-drawio", label: "As-is flow for Lucidchart (.drawio)", path: `${base}/flow?variant=as_is&format=drawio`, filename: "as_is_process_flow.drawio", preview: false },
      { id: "asis-mmd", label: "As-is flow (Mermaid)", path: `${base}/flow?variant=as_is&format=mermaid`, filename: "as_is_process_flow.mmd", preview: true },
    ] : []),
    ...(idea.to_be_process_id && idea.as_is_process_id ? [
      { id: "improvements", label: "Improvements report (Markdown)", path: `${base}/improvements.md`, filename: "improvements.md", preview: true },
    ] : []),
  ];
  const [selected, setSelected] = useState<Format>(formats[0]);
  const preview = useQuery({ queryKey: ["export", selected.path], queryFn: () => api.text(selected.path), enabled: selected.preview });
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Section title="Formats">
        <ul className="space-y-1">
          {formats.map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-2">
              <button className={`text-left text-sm ${selected.id === f.id ? "font-medium text-accent-700" : "text-slate-700 hover:text-slate-900"}`}
                      onClick={() => setSelected(f)}>{f.label}</button>
              <button className="btn-ghost" onClick={() => download(f.path, f.filename)} aria-label={`Download ${f.label}`}>Download</button>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-slate-500">Jira, Azure DevOps and Excel exports and the export history arrive with the export module (M9).</p>
      </Section>
      <div className="lg:col-span-2">
        <Section title={`Preview: ${selected.label}`}>
          {selected.preview ? <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap text-xs text-slate-700">{preview.data ?? "Loading…"}</pre>
            : <p className="text-sm text-slate-500">Download the file and import it into Lucidchart (File → Import → draw.io).</p>}
        </Section>
      </div>
    </div>
  );
}

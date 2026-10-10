import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { marked } from "marked";
import { useEffect, useState } from "react";
import { api, download } from "../api";
import FlowThumbnail from "../components/FlowThumbnail";
import { ErrorNote, Loading, Section } from "../components/ui";
import type { Overview } from "../types";

interface Format { id: string; label: string; import_into: string; default: boolean; files: string[] }
interface Formats { formats: Format[]; variants: string[]; ado_process: string }
interface Preview { files: { file: string; kind: string; text: string }[]; draft: boolean; not_ready: number }
interface ExportRecord {
  export_id: string; ir_version: number; formats: string[]; files: { name: string; size: number }[];
  variant: string; draft: boolean; created_by: string; created_at: string; superseded_by: string | null;
}

export default function ExportTab({ idea }: { idea: Overview }) {
  const qc = useQueryClient();
  const base = `/ideas/${idea.idea_id}/exports`;
  const formats = useQuery({ queryKey: ["export-formats", idea.idea_id], queryFn: () => api.get<Formats>(`${base}/formats`) });
  const history = useQuery({ queryKey: ["exports", idea.idea_id], queryFn: () => api.get<ExportRecord[]>(base) });
  const [chosen, setChosen] = useState<string[]>([]);
  const [previewing, setPreviewing] = useState<string>("");
  useEffect(() => {
    if (formats.data && chosen.length === 0) {
      const defaults = formats.data.formats.filter((f) => f.default).map((f) => f.id);
      setChosen(defaults);
      setPreviewing(defaults.includes("markdown") ? "markdown" : defaults[0]);
    }
  }, [formats.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const preview = useQuery({
    queryKey: ["export-preview", idea.idea_id, previewing],
    queryFn: () => api.get<Preview>(`${base}/preview?format=${previewing}`),
    enabled: Boolean(previewing) && !["lucidchart"].includes(previewing),
  });
  const create = useMutation({
    mutationFn: () => api.post<ExportRecord>(base, { formats: chosen }),
    onSuccess: async (record) => {
      qc.invalidateQueries({ queryKey: ["exports", idea.idea_id] });
      const files = record.files;
      if (files.length === 1) await download(`/exports/${record.export_id}/download?file=${encodeURIComponent(files[0].name)}`, files[0].name.split("/").pop()!);
      else await download(`/exports/${record.export_id}/download`, `${idea.idea_id}_v${record.ir_version}_export.zip`);
    },
  });
  if (formats.isLoading) return <Loading />;
  if (formats.error) return <ErrorNote error={formats.error} />;
  const all = formats.data!.formats;
  const fileCount = all.filter((f) => chosen.includes(f.id)).reduce((n, f) => n + f.files.length, 0);
  const notReady = idea.stats.stories - idea.stats.stories_ready;
  const toggle = (id: string) => setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));

  return (
    <div className="space-y-6">
      {notReady > 0 && (
        <div role="status" className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="draft-banner">
          <strong>Draft — {notReady} {notReady === 1 ? "story" : "stories"} not ready.</strong> You can still export: Markdown
          carries a draft banner and Jira/Azure DevOps items get a DRAFT label.
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <Section title="Formats">
          <ul className="space-y-1" aria-label="Formats">
            {all.map((f) => (
              <li key={f.id} className={`flex items-start gap-3 rounded-md px-2 py-2 ${previewing === f.id ? "bg-slate-50" : ""}`}>
                <input type="checkbox" className="mt-1 accent-[#256a64]" id={`fmt-${f.id}`} checked={chosen.includes(f.id)}
                       onChange={() => toggle(f.id)} />
                <label htmlFor={`fmt-${f.id}`} className="flex-1 cursor-pointer">
                  <span className="block text-sm font-medium text-slate-900">{f.label}</span>
                  <span className="block text-xs text-slate-500">{f.import_into} · {f.files.map((x) => x.split("/").pop()).join(", ")}</span>
                </label>
                <button className="text-xs text-accent-700 hover:underline" onClick={() => setPreviewing(f.id)}>Preview</button>
              </li>
            ))}
          </ul>
          {chosen.includes("ado") && <p className="mt-3 text-xs text-slate-500">Azure DevOps process: {formats.data!.ado_process} ({formats.data!.ado_process === "scrum" ? "Product Backlog Items" : "User Stories"}).</p>}
          <button className="btn-primary mt-4 w-full justify-center" disabled={chosen.length === 0 || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Exporting…" : fileCount === 1 ? "Download file" : `Download ${fileCount} files (zip)`}
          </button>
          <div className="mt-3"><ErrorNote error={create.error} /></div>
        </Section>

        <Section title={`Preview: ${all.find((f) => f.id === previewing)?.label ?? ""}`}>
          {previewing === "lucidchart" ? (
            <div className="space-y-3 text-sm text-slate-600">
              <FlowThumbnail thumb={idea.thumbnail} />
              <p>Import the .drawio file into Lucidchart (File → Import → draw.io) to get editable shapes.</p>
            </div>
          ) : preview.isLoading ? <Loading /> : preview.error ? <ErrorNote error={preview.error} /> : (
            <div className="space-y-4" data-testid="export-preview">
              {preview.data?.files.map((f) => (
                <div key={f.file}>
                  <p className="label mb-1">{f.file}</p>
                  {f.kind === "md" ? (
                    <div className="prose-story max-h-[28rem] overflow-auto rounded border border-slate-200 p-4"
                         dangerouslySetInnerHTML={{ __html: marked.parse(f.text, { async: false }) as string }} />
                  ) : (
                    <pre className="max-h-[28rem] overflow-auto whitespace-pre rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">{f.text}</pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>

      <Section title="Export history">
        {history.data?.length ? (
          <table className="w-full text-sm" data-testid="export-history">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="py-2">When</th><th>Who</th><th>IR version</th><th>Formats</th><th /></tr>
            </thead>
            <tbody>
              {history.data.map((h) => (
                <tr key={h.export_id} className="border-t border-slate-100">
                  <td className="py-2">{new Date(h.created_at).toLocaleString()}</td>
                  <td>{h.created_by}</td>
                  <td>v{h.ir_version}{h.draft && <span className="chip ml-2 bg-amber-50 text-amber-800">draft</span>}
                    {h.superseded_by && <span className="chip ml-2 bg-slate-100 text-slate-500">superseded</span>}</td>
                  <td className="text-slate-600">{h.formats.join(", ")}</td>
                  <td className="text-right">
                    <button className="btn-ghost" onClick={() => download(`/exports/${h.export_id}/download`, `${idea.idea_id}_v${h.ir_version}_export.zip`)}>
                      Download zip
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-sm text-slate-500">No exports yet.</p>}
      </Section>
    </div>
  );
}

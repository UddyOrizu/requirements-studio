import type { ReactNode } from "react";

const STATUS: Record<string, string> = {
  discovering: "bg-sky-50 text-sky-700 ring-sky-200",
  improving: "bg-amber-50 text-amber-800 ring-amber-200",
  refining: "bg-violet-50 text-violet-700 ring-violet-200",
  ready: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  exported: "bg-slate-100 text-slate-700 ring-slate-200",
};

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip ring-1 ${STATUS[status] ?? STATUS.exported}`}>{status}</span>;
}

const BAND: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-700", amber: "bg-amber-50 text-amber-800", red: "bg-rose-50 text-rose-700",
};

export function ConfidenceChip({ band, value }: { band: string; value: number }) {
  return <span className={`chip ${BAND[band]}`}>{band} {value}</span>;
}

export function DorChip({ status }: { status: string }) {
  const style = status === "ready" ? "bg-emerald-50 text-emerald-700" : status === "waived"
    ? "bg-slate-100 text-slate-700" : "bg-rose-50 text-rose-700";
  return <span className={`chip ${style}`}>DoR {status.replace("_", " ")}</span>;
}

export function Meter({ value, label }: { value: number; label?: string }) {
  return (
    <div className="flex items-center gap-2" aria-label={label}>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200">
        <div className="h-full rounded-full bg-accent-500" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slate-600">{Math.round(value * 100)}%</span>
    </div>
  );
}

export function Section({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
      {error instanceof Error ? error.message : String(error)}
    </div>
  );
}

export function Loading() {
  return <p className="py-8 text-center text-sm text-slate-500">Loading…</p>;
}

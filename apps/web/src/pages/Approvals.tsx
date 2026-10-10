import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading } from "../components/ui";
import type { Approval, ApprovalKind, ApprovalStatus } from "../types";

export const KIND_LABEL: Record<ApprovalKind, string> = {
  patch_review: "Change to review", story_signoff: "Story sign-off", suggestion: "Improvement decision", question: "Question",
};
export const STATUS_STYLE: Record<ApprovalStatus, string> = {
  pending: "bg-amber-50 text-amber-800", approved: "bg-emerald-50 text-emerald-700", answered: "bg-emerald-50 text-emerald-700",
  rejected: "bg-rose-50 text-rose-700", cancelled: "bg-slate-100 text-slate-500", closed: "bg-slate-100 text-slate-500",
};

export function ago(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

const TABS = [
  ["inbox", "pending", "Waiting for me"], ["sent", "pending", "I asked"], ["inbox", "any", "All sent to me"], ["sent", "any", "All I asked"],
] as const;

export default function Approvals() {
  const [tab, setTab] = useState(0);
  const [box, status] = TABS[tab];
  const list = useQuery({
    queryKey: ["approvals", box, status],
    queryFn: () => api.get<Approval[]>(`/approvals?box=${box}&status=${status}`),
  });
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Approvals</h1>
        <p className="mt-1 text-sm text-slate-500">Changes, sign-offs, improvement decisions and questions people have sent you, and the ones you sent.</p>
      </div>
      <nav className="flex gap-1 border-b border-slate-200" aria-label="Approval lists">
        {TABS.map(([, , label], i) => (
          <button key={label} onClick={() => setTab(i)}
                  className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${i === tab ? "border-accent-600 text-accent-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {label}
          </button>
        ))}
      </nav>
      {list.isLoading ? <Loading /> : list.error ? <ErrorNote error={list.error} /> : list.data!.length === 0 ? (
        <p className="card p-8 text-center text-sm text-slate-500">{tab === 0 ? "Nothing is waiting for you." : "Nothing here."}</p>
      ) : (
        <ul className="card divide-y divide-slate-100" data-testid="approvals-list">
          {list.data!.map((a) => (
            <li key={a.approval_id}>
              <Link to={`/approvals/${a.approval_id}`} className="flex items-start justify-between gap-4 px-5 py-4 hover:bg-slate-50">
                <div className="min-w-0">
                  <p className="text-xs text-slate-500">{KIND_LABEL[a.kind]}{a.idea_title && ` · ${a.idea_title}`}</p>
                  <p className="mt-0.5 truncate font-medium text-slate-900">{a.title}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {box === "inbox" ? `From ${a.requested_by.name}` : `To ${a.assignee.name}`} · {ago(a.created_at)}
                  </p>
                </div>
                <span className={`chip shrink-0 ${STATUS_STYLE[a.status]}`}>{a.status}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

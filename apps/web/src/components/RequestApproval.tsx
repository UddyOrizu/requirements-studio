import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { ApprovalDetail, ApprovalKind } from "../types";
import PersonPicker from "./PersonPicker";
import { ErrorNote } from "./ui";

/** "Send to someone": email a colleague an approval request for this patch, sign-off or suggestion. */
export default function RequestApproval({ kind, subjectId, ideaId, label, onSent }: {
  kind: Exclude<ApprovalKind, "question">; subjectId: string; ideaId?: string; label: string; onSent?: () => void;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [who, setWho] = useState("");
  const [message, setMessage] = useState("");
  const send = useMutation({
    mutationFn: () => api.post<ApprovalDetail>("/approvals", {
      kind, subject_id: subjectId, idea_id: ideaId, assignee_user_id: who, message: message || undefined,
    }),
    onSuccess: () => { setOpen(false); setWho(""); setMessage(""); qc.invalidateQueries({ queryKey: ["approvals"] }); onSent?.(); },
  });
  if (send.data && !open) {
    return (
      <p className="text-xs text-emerald-700" role="status">
        Sent to {send.data.assignee.name}. <Link className="underline" to={`/approvals/${send.data.approval_id}`}>Track it</Link>
      </p>
    );
  }
  if (!open) return <button type="button" className="btn-ghost" onClick={() => setOpen(true)}>{label}</button>;
  return (
    <form className="w-full space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3" aria-label={label}
          onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
      <PersonPicker value={who} onChange={setWho} label="Send to" />
      <input className="input" placeholder="Add a note (optional)" aria-label="Note" value={message} onChange={(e) => setMessage(e.target.value)} />
      <ErrorNote error={send.error} />
      <div className="flex gap-2">
        <button className="btn-primary" disabled={!who || send.isPending}>Send request</button>
        <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      <p className="text-xs text-slate-500">They get an email with a link, and decide in Requirements Studio.</p>
    </form>
  );
}

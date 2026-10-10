import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { authConfig, replaceToken } from "../auth";
import { ErrorNote, Section } from "../components/ui";
import { useMe } from "../hooks";

export default function Account() {
  const me = useMe();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({
    mutationFn: () => api.post<{ access_token: string }>("/me/password", { current_password: current, new_password: next }),
    onSuccess: (r) => { replaceToken(r.access_token); setCurrent(""); setNext(""); },
  });
  const passwords = authConfig()?.password ?? true;
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-xl font-semibold text-slate-900">Your account</h1>
      <Section title="Profile">
        <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
          <dt className="text-slate-500">Name</dt><dd>{me.data?.name}</dd>
          <dt className="text-slate-500">Email</dt><dd>{me.data?.email}</dd>
          <dt className="text-slate-500">Role</dt><dd className="capitalize">{me.data?.role}</dd>
        </dl>
        <p className="mt-3 text-xs text-slate-500">An administrator can change your name or role.</p>
      </Section>
      {passwords && (
        <Section title="Change password">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); change.mutate(); }}>
            <input className="input" type="password" autoComplete="current-password" placeholder="Current password"
                   aria-label="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} />
            <input className="input" type="password" autoComplete="new-password" placeholder="New password (12+ characters)"
                   aria-label="New password" value={next} onChange={(e) => setNext(e.target.value)} />
            <ErrorNote error={change.error} />
            {change.isSuccess && <p className="text-sm text-emerald-700">Password changed. Other devices have been signed out.</p>}
            <button className="btn-primary" disabled={!current || !next || change.isPending}>Change password</button>
          </form>
        </Section>
      )}
    </div>
  );
}

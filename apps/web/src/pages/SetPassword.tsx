import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { setPassword } from "../auth";
import AuthCard from "../components/AuthCard";
import { ErrorNote } from "../components/ui";

type LinkInfo = { purpose: "invite" | "reset"; email: string; name: string };

// Opened from an invitation or password-reset email: /set-password?token=…
export default function SetPassword() {
  const navigate = useNavigate();
  const token = useSearchParams()[0].get("token") ?? "";
  const info = useQuery({
    queryKey: ["password-link", token], enabled: Boolean(token),
    queryFn: async () => {
      const res = await fetch(`/auth/password/link?token=${encodeURIComponent(token)}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body.title ?? "This link does not work");
      return body as LinkInfo;
    },
  });
  const [password, setValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  if (!token || info.error) {
    return (
      <AuthCard title="This link has expired" subtitle="Links work once, and only for a limited time.">
        <ErrorNote error={info.error} />
        <p className="mt-3 text-sm text-slate-600">
          <Link to="/forgot-password" className="text-accent-700 hover:underline">Ask for a new link</Link>, or ask an administrator to send your invitation again.
        </p>
      </AuthCard>
    );
  }
  if (!info.data) return <AuthCard title="Set your password"><p className="text-sm text-slate-500">Loading…</p></AuthCard>;
  const invite = info.data.purpose === "invite";
  const mismatch = confirm.length > 0 && confirm !== password;
  return (
    <AuthCard title={invite ? `Welcome, ${info.data.name}` : "Choose a new password"}
              subtitle={invite ? `Choose a password for ${info.data.email}.` : `For ${info.data.email}.`}>
      <form className="space-y-3" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setError(undefined);
        try { await setPassword(token, password); navigate("/", { replace: true }); } catch (err) { setError(err); } finally { setBusy(false); }
      }}>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">New password</span>
          <input className="input mt-1" type="password" autoComplete="new-password" required minLength={12} value={password}
                 onChange={(e) => setValue(e.target.value)} />
          <span className="mt-1 block text-xs text-slate-500">At least 12 characters. A short phrase works well.</span>
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Confirm password</span>
          <input className="input mt-1" type="password" autoComplete="new-password" required value={confirm}
                 onChange={(e) => setConfirm(e.target.value)} />
          {mismatch && <span className="mt-1 block text-xs text-rose-700">The passwords do not match.</span>}
        </label>
        <ErrorNote error={error} />
        <button className="btn-primary w-full justify-center py-2.5" disabled={busy || mismatch || !password}>
          {invite ? "Set password and sign in" : "Save and sign in"}
        </button>
      </form>
    </AuthCard>
  );
}

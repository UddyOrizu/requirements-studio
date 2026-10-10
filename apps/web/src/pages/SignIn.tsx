import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { initAuth, isSignedIn, signInAs, signInWithMicrosoft, signInWithPassword, type AuthConfig } from "../auth";
import AuthCard from "../components/AuthCard";
import { ErrorNote } from "../components/ui";

type DevUser = { user_id: string; name: string; role: string; title: string | null };

export default function SignIn() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next")?.startsWith("/") ? params.get("next")! : "/";
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  useEffect(() => { void initAuth().then(setConfig); }, []);
  const devUsers = useQuery({
    queryKey: ["dev-users"], enabled: Boolean(config?.dev_sign_in),
    queryFn: async () => (await (await fetch("/dev/users")).json()) as DevUser[],
  });
  if (config && isSignedIn()) return <Navigate to={next} replace />;

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true); setError(undefined);
    try { await action(); navigate(next, { replace: true }); } catch (e) { setError(e); } finally { setBusy(false); }
  };

  return (
    <AuthCard title="Sign in" subtitle={config?.sso && !config.password ? "Use your organisation's Microsoft account." : undefined}>
      {!config ? <p className="text-sm text-slate-500">Loading…</p> : (
        <div className="space-y-5">
          {config.password && (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void run(() => signInWithPassword(email, password)); }}>
              <label className="block">
                <span className="text-sm font-medium text-slate-700">Email</span>
                <input className="input mt-1" type="email" autoComplete="username" required value={email}
                       onChange={(e) => setEmail(e.target.value)} />
              </label>
              <label className="block">
                <span className="flex items-baseline justify-between text-sm font-medium text-slate-700">
                  Password <Link to="/forgot-password" className="text-xs font-normal text-accent-700 hover:underline">Forgot password?</Link>
                </span>
                <input className="input mt-1" type="password" autoComplete="current-password" required value={password}
                       onChange={(e) => setPassword(e.target.value)} />
              </label>
              <button className="btn-primary w-full justify-center py-2.5" disabled={busy}>Sign in</button>
            </form>
          )}
          {config.password && config.sso && (
            <div className="flex items-center gap-3 text-xs text-slate-400"><span className="h-px flex-1 bg-slate-200" />or<span className="h-px flex-1 bg-slate-200" /></div>
          )}
          {config.sso && (
            <button className={`${config.password ? "btn-secondary" : "btn-primary"} w-full justify-center py-2.5`} disabled={busy}
                    onClick={() => void run(signInWithMicrosoft)}>
              Sign in with Microsoft
            </button>
          )}
          <ErrorNote error={error} />
          {config.dev_sign_in && (devUsers.data?.length ?? 0) > 0 && (
            <div className="border-t border-slate-200 pt-4">
              <p className="label">Development: sign in as</p>
              <ul className="mt-2 grid grid-cols-2 gap-2">
                {devUsers.data!.map((u) => (
                  <li key={u.user_id}>
                    <button className="w-full rounded-md border border-slate-200 px-3 py-2 text-left hover:border-accent-500 hover:bg-accent-50"
                            disabled={busy} onClick={() => void run(() => signInAs(u.user_id))}>
                      <div className="text-sm font-medium text-slate-900">{u.name}</div>
                      <div className="text-xs text-slate-500">{u.role === "admin" ? "Admin" : u.title ?? "User"}</div>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </AuthCard>
  );
}

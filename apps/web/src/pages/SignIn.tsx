import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { signIn } from "../api";
import { ErrorNote } from "../components/ui";

// Development sign-in against the stub OIDC provider (/dev/oidc). Production uses the organisation's SSO.
const USERS = [
  { id: "user_sarah_lin", name: "Sarah Lin", role: "Requester (Compliance Manager)" },
  { id: "user_daniel_okafor", name: "Daniel Okafor", role: "Process owner, BA" },
  { id: "user_viewer", name: "Dev Viewer", role: "Viewer" },
];

export default function SignIn() {
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>();
  return (
    <div className="grid min-h-screen place-items-center px-6">
      <div className="card w-full max-w-sm p-6">
        <h1 className="text-lg font-semibold text-slate-900">Requirements Studio</h1>
        <p className="mt-1 text-sm text-slate-500">Development sign-in. Choose who you are.</p>
        <ul className="mt-5 space-y-2">
          {USERS.map((u) => (
            <li key={u.id}>
              <button
                className="w-full rounded-md border border-slate-200 px-4 py-3 text-left hover:border-accent-500 hover:bg-accent-50"
                onClick={async () => {
                  try { await signIn(u.id); navigate("/"); } catch (e) { setError(e); }
                }}
              >
                <div className="text-sm font-medium text-slate-900">{u.name}</div>
                <div className="text-xs text-slate-500">{u.role}</div>
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-4"><ErrorNote error={error} /></div>
      </div>
    </div>
  );
}

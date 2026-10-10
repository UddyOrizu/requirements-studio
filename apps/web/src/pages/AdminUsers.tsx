import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { authConfig } from "../auth";
import { ErrorNote, Loading } from "../components/ui";
import { useMe } from "../hooks";
import type { AdminUser } from "../types";

const STATUS_STYLE: Record<AdminUser["status"], string> = {
  active: "bg-emerald-50 text-emerald-700", invited: "bg-amber-50 text-amber-800", disabled: "bg-slate-100 text-slate-500",
};

function when(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// Admins add people, set their role, disable or re-enable them, and resend invitations or password resets.
export default function AdminUsers() {
  const me = useMe();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const users = useQuery({
    queryKey: ["admin-users", q, status],
    queryFn: () => api.get<AdminUser[]>(`/admin/users?${new URLSearchParams({ ...(q && { q }), ...(status && { status }) })}`),
  });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin-users"] }); qc.invalidateQueries({ queryKey: ["people"] }); };
  const [notice, setNotice] = useState<string | null>(null);

  if (me.data && me.data.role !== "admin") return <p className="card p-6 text-sm text-slate-600">Only administrators can manage users.</p>;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Users</h1>
        <p className="mt-1 text-sm text-slate-500">
          People sign in with {authConfig()?.password ? "email and password" : ""}{authConfig()?.password && authConfig()?.sso ? " or " : ""}
          {authConfig()?.sso ? "their Microsoft account (only people added here)" : ""}. Admins manage users; everyone else is a user.
        </p>
      </div>
      <AddUser onAdded={(u) => { setNotice(`Invitation sent to ${u.email}.`); refresh(); }} />
      {notice && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{notice}</p>}
      <div className="flex gap-3">
        <input className="input max-w-xs" placeholder="Search name or email" aria-label="Search users" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input w-40" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option><option value="active">Active</option>
          <option value="invited">Invited</option><option value="disabled">Disabled</option>
        </select>
      </div>
      {users.isLoading ? <Loading /> : users.error ? <ErrorNote error={users.error} /> : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm" data-testid="users-table">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2 font-medium">Person</th><th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Status</th><th className="px-4 py-2 font-medium">Last sign-in</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.data!.map((u) => <Row key={u.user_id} u={u} self={u.user_id === me.data?.user_id} onChange={refresh} onNotice={setNotice} />)}
            </tbody>
          </table>
          {users.data!.length === 0 && <p className="p-6 text-center text-sm text-slate-500">Nobody matches.</p>}
        </div>
      )}
    </div>
  );
}

function AddUser({ onAdded }: { onAdded: (u: AdminUser) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const add = useMutation({
    mutationFn: () => api.post<AdminUser>("/admin/users", { name, email, role }),
    onSuccess: (u) => { setOpen(false); setName(""); setEmail(""); setRole("user"); onAdded(u); },
  });
  if (!open) return <button className="btn-primary" onClick={() => setOpen(true)}>Add user</button>;
  return (
    <form className="card space-y-3 p-5" aria-label="Add user" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
      <h2 className="text-sm font-semibold text-slate-900">Add a user</h2>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_10rem]">
        <input className="input" placeholder="Full name" aria-label="Full name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input className="input" type="email" placeholder="Work email" aria-label="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <select className="input" aria-label="Role" value={role} onChange={(e) => setRole(e.target.value as "user" | "admin")}>
          <option value="user">User</option><option value="admin">Admin</option>
        </select>
      </div>
      <p className="text-xs text-slate-500">They get an email invitation{authConfig()?.password ? " to choose a password" : " to sign in with Microsoft"}.</p>
      <ErrorNote error={add.error} />
      <div className="flex gap-2">
        <button className="btn-primary" disabled={add.isPending}>Add and invite</button>
        <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  );
}

function Row({ u, self, onChange, onNotice }: { u: AdminUser; self: boolean; onChange: () => void; onNotice: (s: string) => void }) {
  const update = useMutation({ mutationFn: (body: object) => api.patch<AdminUser>(`/admin/users/${u.user_id}`, body), onSuccess: onChange });
  const invite = useMutation({ mutationFn: () => api.post(`/admin/users/${u.user_id}/invite`), onSuccess: () => onNotice(`Invitation sent again to ${u.email}.`) });
  const reset = useMutation({ mutationFn: () => api.post(`/admin/users/${u.user_id}/password-reset`), onSuccess: () => onNotice(`Password reset link sent to ${u.email}.`) });
  const error = update.error ?? invite.error ?? reset.error;
  const passwords = authConfig()?.password ?? true;
  return (
    <tr data-testid={`user-${u.user_id}`} className={u.status === "disabled" ? "text-slate-400" : ""}>
      <td className="px-4 py-3">
        <div className="font-medium text-slate-900">{u.name}{self && <span className="ml-1 text-xs font-normal text-slate-400">(you)</span>}</div>
        <div className="text-xs text-slate-500">{u.email}{u.sso_linked && " · Microsoft"}</div>
        {error && <div className="mt-1"><ErrorNote error={error} /></div>}
      </td>
      <td className="px-4 py-3">
        <select className="input w-28 py-1" aria-label={`Role of ${u.name}`} value={u.role} disabled={update.isPending}
                onChange={(e) => update.mutate({ role: e.target.value })}>
          <option value="user">User</option><option value="admin">Admin</option>
        </select>
      </td>
      <td className="px-4 py-3">
        <span className={`chip ${STATUS_STYLE[u.status]}`}>{u.status}</span>
        {u.locked && <span className="chip ml-1 bg-rose-50 text-rose-700">locked</span>}
      </td>
      <td className="px-4 py-3 text-xs text-slate-500">{when(u.last_sign_in_at)}</td>
      <td className="px-4 py-3">
        <div className="flex justify-end gap-1">
          {u.status === "invited" && <button className="btn-ghost" disabled={invite.isPending} onClick={() => invite.mutate()}>Resend invite</button>}
          {u.status === "active" && passwords && <button className="btn-ghost" disabled={reset.isPending} onClick={() => reset.mutate()}>Reset password</button>}
          {u.status === "disabled"
            ? <button className="btn-secondary" disabled={update.isPending} onClick={() => update.mutate({ status: "active" })}>Enable</button>
            : !self && <button className="btn-ghost text-rose-700 hover:bg-rose-50" disabled={update.isPending}
                               onClick={() => { if (confirm(`Disable ${u.name}? They are signed out at once and can no longer sign in.`)) update.mutate({ status: "disabled" }); }}>Disable</button>}
        </div>
      </td>
    </tr>
  );
}

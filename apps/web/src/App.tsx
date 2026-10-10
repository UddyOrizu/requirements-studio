import { Link, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { isSignedIn, signOut } from "./auth";
import { useApprovalCount, useMe } from "./hooks";
import Account from "./pages/Account";
import AdminUsers from "./pages/AdminUsers";
import ApprovalDetail from "./pages/ApprovalDetail";
import Approvals from "./pages/Approvals";
import ForgotPassword from "./pages/ForgotPassword";
import IdeaDetail from "./pages/IdeaDetail";
import IdeasList from "./pages/IdeasList";
import NewIdea from "./pages/NewIdea";
import SetPassword from "./pages/SetPassword";
import SignIn from "./pages/SignIn";

const PUBLIC = ["/signin", "/set-password", "/forgot-password"];

function NavItem({ to, children, end }: { to: string; children: React.ReactNode; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) =>
      `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? "bg-slate-100 text-slate-900" : "text-slate-600 hover:text-slate-900"}`}>
      {children}
    </NavLink>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const pending = useApprovalCount().data?.pending ?? 0;
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2 font-semibold text-slate-900">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-accent-600 text-xs text-white">RS</span>
              Requirements Studio
            </Link>
            <nav className="flex items-center gap-1" aria-label="Main">
              <NavItem to="/" end>Ideas</NavItem>
              <NavItem to="/approvals">
                Approvals
                {pending > 0 && <span className="ml-1.5 rounded-full bg-accent-600 px-1.5 py-0.5 text-xs text-white" aria-label={`${pending} waiting`}>{pending}</span>}
              </NavItem>
              {me.data?.role === "admin" && <NavItem to="/admin/users">Users</NavItem>}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-600">
            {me.data && (
              <Link to="/account" className="hover:text-slate-900">
                {me.data.name}{me.data.role === "admin" && <span className="ml-1.5 chip bg-slate-100 text-slate-600">admin</span>}
              </Link>
            )}
            <button className="btn-ghost" onClick={() => void signOut()}>Sign out</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  if (!isSignedIn() && !PUBLIC.includes(location.pathname)) {
    const next = location.pathname === "/" ? "" : `?next=${encodeURIComponent(location.pathname)}`;
    return <Navigate to={`/signin${next}`} replace />;
  }
  return (
    <Routes>
      <Route path="/signin" element={<SignIn />} />
      <Route path="/set-password" element={<SetPassword />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/" element={<Shell><IdeasList /></Shell>} />
      <Route path="/ideas/new" element={<Shell><NewIdea /></Shell>} />
      <Route path="/ideas/:ideaId/*" element={<Shell><IdeaDetail /></Shell>} />
      <Route path="/approvals" element={<Shell><Approvals /></Shell>} />
      <Route path="/approvals/:approvalId" element={<Shell><ApprovalDetail /></Shell>} />
      <Route path="/admin/users" element={<Shell><AdminUsers /></Shell>} />
      <Route path="/account" element={<Shell><Account /></Shell>} />
    </Routes>
  );
}

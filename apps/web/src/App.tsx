import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { token } from "./api";
import { useMe } from "./hooks";
import IdeaDetail from "./pages/IdeaDetail";
import IdeasList from "./pages/IdeasList";
import NewIdea from "./pages/NewIdea";
import SignIn from "./pages/SignIn";

function Shell({ children }: { children: React.ReactNode }) {
  const me = useMe();
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <Link to="/" className="flex items-center gap-2 font-semibold text-slate-900">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-accent-600 text-xs text-white">RS</span>
            Requirements Studio
          </Link>
          <div className="flex items-center gap-3 text-sm text-slate-600">
            {me.data && <span>{me.data.name}</span>}
            <button className="btn-ghost" onClick={() => { token.clear(); window.location.assign("/signin"); }}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  if (!token.get() && location.pathname !== "/signin") return <Navigate to="/signin" replace />;
  return (
    <Routes>
      <Route path="/signin" element={<SignIn />} />
      <Route path="/" element={<Shell><IdeasList /></Shell>} />
      <Route path="/ideas/new" element={<Shell><NewIdea /></Shell>} />
      <Route path="/ideas/:ideaId/*" element={<Shell><IdeaDetail /></Shell>} />
    </Routes>
  );
}

import { useQuery } from "@tanstack/react-query";
import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, StatusChip } from "../components/ui";
import type { Overview as OverviewData } from "../types";
import Conversation from "./Conversation";
import ExportTab from "./ExportTab";
import FlowTab from "./FlowTab";
import Improvements from "./Improvements";
import Overview from "./Overview";
import Stories from "./Stories";
import StoryDetail from "./StoryDetail";

export function useIdea(ideaId: string) {
  return useQuery({ queryKey: ["idea", ideaId], queryFn: () => api.get<OverviewData>(`/ideas/${ideaId}`) });
}

export default function IdeaDetail() {
  const { ideaId = "" } = useParams();
  const idea = useIdea(ideaId);
  if (idea.isLoading) return <Loading />;
  if (idea.error) return <ErrorNote error={idea.error} />;
  const data = idea.data!;
  const tabs = [
    ["", "Overview"], ["conversation", "Conversation"], ["flow", "Flow"],
    ...(data.has_as_is ? [["improvements", "Improvements"]] : []), ["stories", "Stories"], ["export", "Export"],
  ];
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-slate-900">{data.title}</h1>
          <StatusChip status={data.status} />
        </div>
        <p className="mt-1 text-sm text-slate-500">
          {data.process.variant === "to_be" ? "To-be" : "As-is"} process v{data.process.version} · owner {data.owner_user_id}
        </p>
      </div>
      <nav className="flex gap-1 border-b border-slate-200" aria-label="Idea sections">
        {tabs.map(([path, label]) => (
          <NavLink key={path} to={`/ideas/${ideaId}${path ? `/${path}` : ""}`} end={!path}
                   className={({ isActive }) => `-mb-px border-b-2 px-3 py-2 text-sm font-medium ${isActive
                     ? "border-accent-600 text-accent-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Overview idea={data} />} />
        <Route path="conversation" element={<Conversation idea={data} />} />
        <Route path="flow" element={<FlowTab idea={data} />} />
        <Route path="improvements" element={<Improvements idea={data} />} />
        <Route path="stories" element={<Stories idea={data} />} />
        <Route path="stories/:storyId" element={<StoryDetail idea={data} />} />
        <Route path="export" element={<ExportTab idea={data} />} />
      </Routes>
    </div>
  );
}

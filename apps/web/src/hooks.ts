import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Person } from "./types";

export type Me = { user_id: string; name: string; email: string; role: "user" | "admin" | null; roles: string[] };

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/me"), staleTime: 60_000 });

/** People who can be asked to approve or answer something (not disabled). */
export const usePeople = () => useQuery({ queryKey: ["people"], queryFn: () => api.get<Person[]>("/users"), staleTime: 60_000 });

export const useApprovalCount = () =>
  useQuery({ queryKey: ["approvals", "summary"], queryFn: () => api.get<{ pending: number }>("/approvals/summary"),
             refetchInterval: 30_000 });

export const pct = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

export const PRIORITY_LABEL: Record<string, string> = {
  must: "Must have", should: "Should have", could: "Could have", wont: "Won't have",
};

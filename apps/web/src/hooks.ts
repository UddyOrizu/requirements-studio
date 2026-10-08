import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export const useMe = () =>
  useQuery({ queryKey: ["me"], queryFn: () => api.get<{ user_id: string; name: string; roles: string[] }>("/me") });

export const pct = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

export const PRIORITY_LABEL: Record<string, string> = {
  must: "Must have", should: "Should have", could: "Could have", wont: "Won't have",
};

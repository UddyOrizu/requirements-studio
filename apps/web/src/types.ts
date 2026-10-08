export type Control = "automated" | "hitl_review" | "human_task" | "approval" | "unset" | "decision" | "wait"
  | "start" | "end" | "event" | "queue";

export interface IdeaStats {
  stories: number; stories_ready: number; open_questions: number; suggestions_accepted: number;
  suggestions_rejected: number; hours_saved_per_month: number | null; coverage: number;
}

export interface IdeaSummary {
  idea_id: string; title: string; summary: string; owner_user_id: string; status: string; has_as_is: boolean;
  as_is_process_id: string | null; to_be_process_id: string | null; session_id: string; tags: string[];
  stats: IdeaStats; created_at: string; updated_at: string; phase: string | null; waiting_on: string[];
  thumbnail: { width: number; height: number; lanes: [number, number][]; nodes: [number, number, number, number, Control][] };
}

export interface Overview extends IdeaSummary {
  process: { id: string; name: string; variant: string; version: number; description?: string };
  goals: { id: string; statement: string; metrics: { name: string; unit?: string; baseline?: number; target?: number }[]; beneficiaries: string[] }[];
  beneficiaries: string[];
  scope: { in: string[]; out: string[]; assumptions: string[]; constraints: string[] };
  nfrs: { id: string; category: string; statement: string; measure?: string }[];
  open_questions: { story_id: string; gap_id: string; text: string; severity: string; status: string; asked_to: string | null }[];
}

export interface FlowNode {
  id: string; type: string; control: Control; lane: string; lines: string[]; x: number; y: number; w: number; h: number;
  story_id: string | null; changed_by: string | null;
}
export interface Flow {
  title: string; variant: string; version: number; width: number; height: number;
  lanes: { id: string; name: string; y: number; height: number }[];
  nodes: FlowNode[];
  edges: { id: string; source: string; target: string; label: string; kind: "flow" | "reject" | "route" | "queue" }[];
}

export interface StoryRow {
  story_id: string; title: string; priority: string | null; control: string; control_mode: string | null;
  confidence: number; band: string; dor_status: string; failed_checks: string[]; open_questions: number;
  change: string | null; node_ids: string[];
}

export interface StoryDetail extends StoryRow {
  markdown: string; process_id: string; version: number;
  story: { open_questions: { gap_id: string; text: string; asked_to: string | null }[]; edge_cases: { ref: string; title: string }[] };
  dor: { checks: { check_id: string; passed: boolean; message: string }[] };
  editable: {
    task_id: string; outcome?: string; hitl: { mode?: string; actor_id?: string; criteria?: string };
    acceptance_criteria: Record<string, { title: string; given: string[]; when: string[]; then: string[]; kind?: string }>;
  };
}

export interface Suggestion {
  suggestion_id: string; kind: string; target_refs: string[]; title: string; change_summary: string; rationale: string;
  evidence: { source_id: string; locator: string; excerpt: string }[];
  benefit: { minutes_saved_per_case: number | null; hours_saved_per_month: number | null; qualitative?: string };
  controls: string; risk?: string; confidence: number; status: string; decision: { reason?: string } | null;
}

export interface NextQuestion {
  turn: string | null; target: { kind: string; id: string }; text: string | null; why: string | null;
  answer_type: string | null; suggested_answers: string[];
}

export interface TimelineEntry {
  seq: number; kind: string; phase: string; turn?: string; target?: { kind: string; id: string };
  question?: { text: string; why: string }; answer?: { by: string; text?: string; special?: string };
  captured?: string[]; assumptions?: string[]; playback_text?: string; patch_id?: string;
  from_phase?: string; to_phase?: string;
}

export interface IntakeSession {
  session_id: string; phase: string; status: string; timeline: TimelineEntry[];
  coverage: { percent: number; filled: string[]; unfilled: string[]; parked: string[] };
  next_question: NextQuestion | null;
}

export interface HistoryEntry {
  patch_id: string; version: number; reason: string; author: { kind: string; id: string }; at: string; touched: string[];
}

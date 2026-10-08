import type { Control } from "../types";

// M10 control styling, a little softer for the screen. Every label also says what the shape is (never colour alone).
export const CONTROL_STYLE: Record<Control, { fill: string; stroke: string; dashed?: boolean; width?: number }> = {
  automated: { fill: "#DAE8FC", stroke: "#6C8EBF" },
  hitl_review: { fill: "#FFE6CC", stroke: "#D79B00", width: 3 },
  human_task: { fill: "#FFFFFF", stroke: "#4D4D4D", width: 2 },
  approval: { fill: "#F8CECC", stroke: "#B85450", width: 3 },
  unset: { fill: "#FFFFFF", stroke: "#999999", dashed: true },
  decision: { fill: "#FFF2CC", stroke: "#D6B656" },
  wait: { fill: "#F5F5F5", stroke: "#999999", dashed: true },
  event: { fill: "#F5F5F5", stroke: "#999999" },
  start: { fill: "#D5E8D4", stroke: "#82B366" },
  end: { fill: "#D5E8D4", stroke: "#82B366" },
  queue: { fill: "#FFE6CC", stroke: "#D79B00", dashed: true, width: 2 },
};

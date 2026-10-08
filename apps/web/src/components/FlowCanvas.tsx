import {
  Background, Controls, type Edge, Handle, MarkerType, type Node, type NodeProps, Position, ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { Flow, FlowNode } from "../types";
import { CONTROL_STYLE } from "./flowStyle";

type StepData = { node: FlowNode; highlight?: boolean };
type LaneData = { name: string; width: number; height: number };

function Step({ data }: NodeProps<Node<StepData>>) {
  const n = data.node;
  const s = CONTROL_STYLE[n.control] ?? CONTROL_STYLE.automated;
  const shape = n.control === "approval" ? "clip-hex" : n.type === "decision" ? "clip-diamond"
    : n.type === "start" || n.type === "end" ? "rounded-full" : "rounded-lg";
  const [head, ...rest] = n.lines;
  const tag = ["[", "APPROVAL", "HUMAN QUEUE"].some((p) => head.startsWith(p));
  return (
    <div
      data-testid={`flow-node-${n.id}`}
      className={`flex h-full w-full flex-col items-center justify-center px-2 text-center text-[11px] leading-tight ${shape} ${data.highlight ? "ring-4 ring-accent-500/40" : ""}`}
      style={{ background: s.fill, border: `${s.width ?? 1}px ${s.dashed ? "dashed" : "solid"} ${s.stroke}` }}
      title={n.story_id ? "Open the story" : undefined}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      {tag ? <span className="font-semibold text-[10px] tracking-wide text-slate-700">{head}</span>
        : <span className="text-slate-800">{head}</span>}
      {rest.map((line, i) => (
        <span key={i} className={i === 0 && tag ? "font-medium text-slate-900" : "italic text-slate-600"}>{line}</span>
      ))}
      <Handle type="source" position={Position.Right} className="!opacity-0" />
    </div>
  );
}

function Lane({ data }: NodeProps<Node<LaneData>>) {
  return (
    <div className="flex h-full w-full border-y border-slate-200 bg-slate-50/60" style={{ width: data.width }}>
      <div className="flex w-[140px] items-center border-r border-slate-200 bg-slate-100 px-3 text-xs font-semibold text-slate-700">
        {data.name}
      </div>
    </div>
  );
}

const nodeTypes = { step: Step, lane: Lane };

export default function FlowCanvas({ flow, onOpenStory, highlight = [], height = 520 }: {
  flow: Flow; onOpenStory?: (storyId: string) => void; highlight?: string[]; height?: number;
}) {
  const { nodes, edges } = useMemo(() => {
    const lanes: Node<LaneData>[] = flow.lanes.map((l) => ({
      id: `lane-${l.id}`, type: "lane", position: { x: 0, y: l.y }, draggable: false, selectable: false,
      data: { name: l.name, width: flow.width, height: l.height }, style: { width: flow.width, height: l.height },
      zIndex: -1,
    }));
    const steps: Node<StepData>[] = flow.nodes.map((n) => ({
      id: n.id, type: "step", position: { x: n.x, y: n.y }, draggable: false,
      data: { node: n, highlight: highlight.includes(n.id) }, style: { width: n.w, height: n.h },
    }));
    const es: Edge[] = flow.edges.map((e) => {
      const color = e.kind === "reject" ? "#B85450" : e.kind === "queue" ? "#D79B00" : e.kind === "route" ? "#7F7F7F" : "#64748b";
      return {
        id: e.id, source: e.source, target: e.target, label: e.label || undefined, type: "smoothstep",
        style: { stroke: color, strokeDasharray: e.kind === "route" || e.kind === "queue" ? "5 4" : undefined },
        labelStyle: { fontSize: 10, fill: color }, labelBgStyle: { fill: "#fff" },
        markerEnd: { type: MarkerType.ArrowClosed, color },
      };
    });
    return { nodes: [...lanes, ...steps], edges: es };
  }, [flow, highlight]);

  return (
    <div className="card overflow-hidden" style={{ height }} data-testid="flow-canvas">
      <ReactFlow
        nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView minZoom={0.2} proOptions={{ hideAttribution: true }}
        nodesConnectable={false} elementsSelectable={false}
        onNodeClick={(_, node) => {
          const sid = (node.data as StepData).node?.story_id;
          if (sid && onOpenStory) onOpenStory(sid);
        }}
      >
        <Background gap={20} color="#e2e8f0" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

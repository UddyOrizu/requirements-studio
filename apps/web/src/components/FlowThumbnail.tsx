import type { IdeaSummary } from "../types";
import { CONTROL_STYLE } from "./flowStyle";

export default function FlowThumbnail({ thumb }: { thumb: IdeaSummary["thumbnail"] }) {
  return (
    <svg viewBox={`0 0 ${thumb.width} ${thumb.height}`} className="h-16 w-40 rounded border border-slate-200 bg-white"
         role="img" aria-label="Flow thumbnail">
      {thumb.lanes.map(([y, h], i) => (
        <rect key={i} x={0} y={y} width={thumb.width} height={h} fill={i % 2 ? "#F8FAFC" : "#FFFFFF"} />
      ))}
      {thumb.nodes.map(([x, y, w, h, control], i) => {
        const s = CONTROL_STYLE[control] ?? CONTROL_STYLE.automated;
        return <rect key={i} x={x} y={y} width={w} height={h} rx={10} fill={s.fill} stroke={s.stroke} strokeWidth={6} />;
      })}
    </svg>
  );
}

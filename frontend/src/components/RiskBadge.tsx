import { TRIGGER_META, triggerForScore } from "@/lib/risk";
import { cn } from "@/lib/utils";
import type { TriggerLevel } from "@/types/foodready";

export const RiskBadge = ({
  level, score, className,
}: { level?: TriggerLevel; score?: number; className?: string }) => {
  const lvl: TriggerLevel = level ?? (typeof score === "number" ? triggerForScore(score) : "prepared");
  const meta = TRIGGER_META[lvl];
  return (
    <span
      className={cn("risk-pill", className)}
      style={{ backgroundColor: `${meta.color}22`, color: meta.color, border: `1px solid ${meta.color}55` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} />
      {meta.label}
      {typeof score === "number" && <span className="opacity-70">· {Math.round(score)}</span>}
    </span>
  );
};

export const RiskScore = ({ score, size = "md" }: { score: number; size?: "sm" | "md" | "lg" }) => {
  const meta = TRIGGER_META[triggerForScore(score)];
  const sizes = { sm: "text-lg", md: "text-3xl", lg: "text-5xl" };
  return (
    <div className="flex items-baseline gap-2">
      <span className={cn("font-bold tabular-nums", sizes[size])} style={{ color: meta.color }}>
        {Math.round(score)}
      </span>
      <span className="text-xs uppercase tracking-wider text-muted-foreground">/ 100</span>
    </div>
  );
};

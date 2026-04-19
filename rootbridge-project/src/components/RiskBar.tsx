import { riskColor } from "@/lib/api";

export function RiskBar({ score, label }: { score: number; label?: string }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div className="space-y-1">
      {label && (
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{label}</span>
          <span className="tabular-nums text-foreground">{pct.toFixed(0)}</span>
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: riskColor(pct) }}
        />
      </div>
    </div>
  );
}

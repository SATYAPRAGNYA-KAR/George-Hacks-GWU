import { Card } from "@/components/ui/card";
import { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const MetricCard = ({
  label, value, hint, icon, accent,
}: { label: string; value: ReactNode; hint?: string; icon?: ReactNode; accent?: string }) => (
  <Card className="metric-card">
    <div className="flex items-start justify-between">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <div className={cn("mt-1.5 text-2xl font-bold tabular-nums", accent)}>{value}</div>
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </div>
      {icon && <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-accent-foreground">{icon}</div>}
    </div>
  </Card>
);

export const MetricStrip = ({ children }: { children: ReactNode }) => (
  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{children}</div>
);

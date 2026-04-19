import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { computeBurnRate, type BurnRateResult } from "@/lib/burnRate";
import { useAppStore } from "@/store/appStore";
import type { Organization } from "@/types/foodready";
import { Package, AlertTriangle } from "lucide-react";

const STATUS_STYLE: Record<BurnRateResult["status"], { color: string; bg: string; label: string }> = {
  critical: { color: "text-red-700",    bg: "bg-red-50",     label: "Critical — restock now" },
  warning:  { color: "text-orange-700", bg: "bg-orange-50",  label: "Low — restock soon" },
  ok:       { color: "text-emerald-700",bg: "bg-emerald-50", label: "Adequate" },
  unknown:  { color: "text-muted-foreground", bg: "bg-muted", label: "Unknown" },
};

interface Props {
  org: Organization;
}

export const BurnRateCard = ({ org }: Props) => {
  const requests = useAppStore((s) => s.requests);
  const incidents = useAppStore((s) => s.incidents);

  const openRequests = requests.filter(
    (r) =>
      org.countiesCovered.includes(r.countyFips) &&
      !["closed", "resolved", "failed_delivery"].includes(r.status),
  ).length;

  const surgeActive = incidents.some(
    (i) =>
      i.status !== "closed" &&
      org.countiesCovered.some((fips) => fips === i.countyFips),
  );

  const result = computeBurnRate(org, openRequests, 3.5, surgeActive);
  const style = STATUS_STYLE[result.status];

  const daysLabel =
    result.daysOfSupply === Infinity
      ? "∞"
      : result.daysOfSupply === 0
      ? "0"
      : `${result.daysOfSupply}`;

  return (
    <Card className={`border ${result.status === "critical" ? "border-red-300" : result.status === "warning" ? "border-orange-300" : ""}`}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Package className="h-4 w-4" />
          Inventory forecast
          {surgeActive && (
            <span className="ml-auto text-[10px] font-normal text-orange-600 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" /> Surge active
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {/* Days of supply headline */}
        <div className={`rounded-lg p-3 ${style.bg}`}>
          <div className="flex items-end gap-2">
            <span className={`text-3xl font-bold tabular-nums ${style.color}`}>
              {daysLabel}
            </span>
            <span className="text-sm text-muted-foreground mb-0.5">days of supply</span>
          </div>
          <p className={`mt-1 text-[11px] font-medium ${style.color}`}>{style.label}</p>
        </div>

        {/* Detail rows */}
        <div className="space-y-1.5 text-muted-foreground">
          <div className="flex justify-between">
            <span>Current stock</span>
            <span className="font-medium text-foreground tabular-nums">
              {org.foodStockLbs.toLocaleString()} lbs
            </span>
          </div>
          <div className="flex justify-between">
            <span>Open requests</span>
            <span className="font-medium text-foreground tabular-nums">{openRequests}</span>
          </div>
          <div className="flex justify-between">
            <span>Est. households served</span>
            <span className="font-medium text-foreground tabular-nums">
              {result.activeHouseholds.toLocaleString()}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Daily burn rate</span>
            <span className="font-medium text-foreground tabular-nums">
              {result.dailyConsumptionLbs > 0
                ? `${result.dailyConsumptionLbs.toLocaleString()} lbs/day`
                : "No active load"}
            </span>
          </div>
          {surgeActive && (
            <p className="text-[10px] text-orange-600 mt-1">
              ×1.4 surge multiplier applied due to active incident.
            </p>
          )}
        </div>

        {/* Depletion progress bar */}
        {isFinite(result.daysOfSupply) && result.daysOfSupply > 0 && (
          <div className="space-y-1">
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>Stock depletion</span>
              <span>{Math.min(100, Math.round((1 - result.daysOfSupply / 30) * 100))}% used in 30d</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  result.status === "critical"
                    ? "bg-red-500"
                    : result.status === "warning"
                    ? "bg-orange-400"
                    : "bg-emerald-500"
                }`}
                style={{
                  width: `${Math.min(100, Math.round((result.daysOfSupply / 30) * 100))}%`,
                }}
              />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
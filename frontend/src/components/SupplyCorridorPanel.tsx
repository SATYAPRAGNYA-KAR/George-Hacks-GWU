import { ALL_CORRIDORS, corridorStatusFromShock, STATUS_META } from "@/data/corridors";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Route, AlertTriangle, Wheat } from "lucide-react";

interface Props {
  /** Filter to only corridors that touch this state (by waypoint state abbr). 
   *  If omitted, shows all corridors. */
  stateAbbr?: string;
  /** Shock score per source region id or corridor id (from weather API or FPI).
   *  Key is corridor.id → score 0-100. Build this from weather.shock_score. */
  shockScores?: Record<string, number>;
}

export const SupplyCorridorPanel = ({ stateAbbr, shockScores = {} }: Props) => {
  const corridors = stateAbbr
    ? ALL_CORRIDORS.filter((c) =>
        c.waypoints.some((w) => w.state === stateAbbr) ||
        (c.source_counties?.length ?? 0) > 0   // ← was: c.source_counties.length > 0
      )
    : ALL_CORRIDORS;

  if (corridors.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Route className="h-4 w-4" />
          Supply corridor status
          <span className="ml-auto text-[10px] font-normal text-muted-foreground">
            {corridors.length} corridor{corridors.length !== 1 ? "s" : ""} monitored
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        {corridors.map((corridor) => {
          const shock = shockScores[corridor.id] ?? shockScores["default"] ?? 20;
          const status = corridorStatusFromShock(shock);
          const meta = STATUS_META[status];
          const highDepCommunities = corridor.destination_communities.filter(
            (d) => d.dependency_weight >= 0.7
          );

          return (
            <div
              key={corridor.id}
              className={`rounded-lg border p-3 ${meta.bg} ${meta.border}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className={`font-semibold truncate ${meta.color}`}>
                    {corridor.name}
                  </p>
                  <p className="text-muted-foreground mt-0.5">
                    {corridor.primary_route}
                    {corridor.backup_route && (
                      <span className="ml-2 text-[10px]">
                        · Backup: {corridor.backup_route}
                      </span>
                    )}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${meta.bg} ${meta.color} border ${meta.border}`}
                >
                  {meta.label}
                </span>
              </div>

              {/* Crops */}
              <div className="mt-2 flex flex-wrap gap-1">
                {corridor.crop_types.map((crop) => (
                  <span
                    key={crop}
                    className="inline-flex items-center gap-0.5 rounded bg-background/60 px-1.5 py-0.5 text-[10px] text-muted-foreground border"
                  >
                    <Wheat className="h-2.5 w-2.5" />
                    {crop}
                  </span>
                ))}
              </div>

              {/* High-dependency communities at risk */}
              {(status === "degraded" || status === "blocked") &&
                highDepCommunities.length > 0 && (
                  <div className="mt-2 flex items-start gap-1.5">
                    <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5 text-orange-600" />
                    <p className="text-muted-foreground">
                      High-dependency communities affected:{" "}
                      <span className="font-medium text-foreground">
                        {highDepCommunities
                          .map(
                            (d) =>
                              `${d.name} (${Math.round(d.dependency_weight * 100)}% reliant)`
                          )
                          .join(", ")}
                      </span>
                    </p>
                  </div>
                )}

              {/* Shock indicator bar */}
              <div className="mt-2 flex items-center gap-2">
                <span className="text-muted-foreground w-16 shrink-0">Disruption</span>
                <div className="flex-1 h-1.5 rounded-full bg-background/60 overflow-hidden border">
                  <div
                    className={`h-full rounded-full ${
                      status === "blocked"
                        ? "bg-red-500"
                        : status === "degraded"
                        ? "bg-orange-400"
                        : status === "at_risk"
                        ? "bg-yellow-400"
                        : "bg-emerald-400"
                    }`}
                    style={{ width: `${Math.min(100, shock)}%` }}
                  />
                </div>
                <span className="w-6 text-right font-mono text-muted-foreground">
                  {Math.round(shock)}
                </span>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
};
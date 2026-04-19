import { useQuery } from "@tanstack/react-query";
import { fetchAllRisks } from "@/lib/api";

export function LiveDataBadge() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["risks-heartbeat"],
    queryFn: fetchAllRisks,
    staleTime: 60_000,
    retry: 0,
  });

  if (isLoading) return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-pulse" />
      Connecting to live data…
    </span>
  );

  if (isError || !data) return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
      <span className="h-1.5 w-1.5 rounded-full bg-yellow-500" />
      Baseline data (backend offline)
    </span>
  );

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
      Live — NOAA · FEMA · NASA · Gemini
    </span>
  );
}
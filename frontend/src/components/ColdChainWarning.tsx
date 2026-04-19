import { AlertTriangle, Snowflake } from "lucide-react";
import type { ColdChainCheckResult } from "@/lib/coldChain";
import { useAppStore } from "@/store/appStore";

interface Props {
  result: ColdChainCheckResult;
  onSelectAlternative?: (orgId: string) => void;
}

export const ColdChainWarning = ({ result, onSelectAlternative }: Props) => {
  const orgs = useAppStore((s) => s.organizations);

  if (result.safe) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-emerald-700">
        <Snowflake className="h-3.5 w-3.5" />
        Cold-chain requirements met
      </div>
    );
  }

  const alternatives = orgs.filter((o) =>
    result.suggestedAlternativeIds.includes(o.id)
  );

  return (
    <div className="rounded-lg border border-orange-200 bg-orange-50 p-3 text-xs space-y-2">
      <div className="flex items-start gap-2 text-orange-700">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
        <p className="font-medium">{result.warning}</p>
      </div>
      {alternatives.length > 0 && (
        <div>
          <p className="text-muted-foreground mb-1.5">
            Cold-chain capable alternatives in this area:
          </p>
          <div className="flex flex-wrap gap-2">
            {alternatives.map((org) => (
              <button
                key={org.id}
                onClick={() => onSelectAlternative?.(org.id)}
                className="inline-flex items-center gap-1 rounded border border-orange-300 bg-white px-2 py-1 text-[11px] text-orange-800 hover:bg-orange-100 transition-colors"
              >
                <Snowflake className="h-2.5 w-2.5" />
                {org.name}
              </button>
            ))}
          </div>
        </div>
      )}
      {alternatives.length === 0 && (
        <p className="text-muted-foreground">
          No verified cold-chain orgs found for this county. Consider voucher/cash delivery mode instead.
        </p>
      )}
    </div>
  );
};
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAppStore } from "@/store/appStore";
import { checkColdChain } from "@/lib/coldChain";
import { ColdChainWarning } from "@/components/ColdChainWarning";
import { toast } from "sonner";
import type { DeliveryMode, SupplySourceType } from "@/types/foodready";
import { Truck } from "lucide-react";

interface Props {
  requestId: string;
  countyFips: string;
  stateAbbr: string;
  onCreated?: () => void;
}

const DELIVERY_MODES: DeliveryMode[] = [
  "home_delivery", "pantry_pickup", "community_distribution",
  "shelter_delivery", "voucher_cash",
];

const SUPPLY_SOURCES: SupplySourceType[] = [
  "food_bank_stock", "pantry_stock", "municipal_reserve",
  "retailer_support", "voucher_cash",
];

export const LogisticsAssignmentForm = ({
  requestId, countyFips, stateAbbr, onCreated,
}: Props) => {
  const orgs = useAppStore((s) =>
    s.organizations.filter(
      (o) => o.verified && o.countiesCovered.includes(countyFips),
    )
  );
  const createLogistics = useAppStore((s) => s.createLogistics);
  const allOrgs = useAppStore((s) => s.organizations);

  const [supplyOrgId, setSupplyOrgId] = useState(orgs[0]?.id ?? "");
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("home_delivery");
  const [supplySource, setSupplySource] = useState<SupplySourceType>("food_bank_stock");

  const selectedOrg = orgs.find((o) => o.id === supplyOrgId);
  const coldChainCheck =
    selectedOrg
      ? checkColdChain(selectedOrg, deliveryMode, supplySource, allOrgs, countyFips)
      : null;

  const handleSubmit = () => {
    if (!selectedOrg) return;
    createLogistics({
      requestId,
      supplySource,
      supplyOrgId,
      stagingSite: "community_center",
      transportProvider: "supplier_truck",
      transportOrgId: supplyOrgId,
      deliveryMode,
      status: "allocated",
    });
    toast.success("Logistics assignment created");
    onCreated?.();
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Truck className="h-4 w-4" /> Create logistics assignment
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="space-y-1">
          <Label className="text-xs">Organization</Label>
          <Select value={supplyOrgId} onValueChange={setSupplyOrgId}>
            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {orgs.length === 0 && (
                <SelectItem value="" disabled>No verified orgs for this county</SelectItem>
              )}
              {orgs.map((o) => (
                <SelectItem key={o.id} value={o.id}>
                  {o.name}{o.coldChain ? " ❄️" : " (no cold chain)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-xs">Supply source</Label>
          <Select value={supplySource} onValueChange={(v) => setSupplySource(v as SupplySourceType)}>
            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {SUPPLY_SOURCES.map((s) => (
                <SelectItem key={s} value={s}>{s.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-xs">Delivery mode</Label>
          <Select value={deliveryMode} onValueChange={(v) => setDeliveryMode(v as DeliveryMode)}>
            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DELIVERY_MODES.map((m) => (
                <SelectItem key={m} value={m}>{m.replace(/_/g, " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Cold-chain validation */}
        {coldChainCheck && (
          <ColdChainWarning
            result={coldChainCheck}
            onSelectAlternative={(id) => setSupplyOrgId(id)}
          />
        )}

        <Button
          size="sm"
          className="w-full h-8 text-xs"
          onClick={handleSubmit}
          disabled={!selectedOrg}
        >
          Assign logistics
        </Button>
      </CardContent>
    </Card>
  );
};
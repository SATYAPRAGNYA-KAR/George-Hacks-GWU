import { AppShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { DataSource } from "@/types/foodready";
import { format } from "date-fns";

const SOURCES: DataSource[] = [
  { name: "NOAA / NWS Alerts", category: "Shock", geographicLevel: "county", description: "Severe weather, flood, fire alerts.", updateFrequency: "5 min", status: "mock", lastSync: new Date().toISOString() },
  { name: "FEMA Disaster Declarations", category: "Shock", geographicLevel: "county", description: "Federal disaster declarations and major incidents.", updateFrequency: "daily", status: "mock", lastSync: new Date().toISOString() },
  { name: "USDA Food Access Atlas", category: "Vulnerability", geographicLevel: "county", description: "Food deserts, low-income low-access populations.", updateFrequency: "annual", status: "planned", lastSync: new Date().toISOString() },
  { name: "Map the Meal Gap (Feeding America)", category: "Vulnerability", geographicLevel: "county", description: "County food insecurity & child food insecurity rates.", updateFrequency: "annual", status: "mock", lastSync: new Date().toISOString() },
  { name: "CDC Social Vulnerability Index", category: "Vulnerability", geographicLevel: "county", description: "Composite vulnerability score by census tract.", updateFrequency: "biennial", status: "planned", lastSync: new Date().toISOString() },
  { name: "Community Price Reports", category: "Supply", geographicLevel: "county", description: "User-submitted retail food prices.", updateFrequency: "real-time", status: "live", lastSync: new Date().toISOString() },
  { name: "Responder Capacity Declarations", category: "Readiness", geographicLevel: "county", description: "Self-reported food bank / NGO stockpile, vouchers, transport.", updateFrequency: "real-time", status: "live", lastSync: new Date().toISOString() },
  { name: "Road Disruption Feeds", category: "Supply", geographicLevel: "county", description: "DOT / 511 road closures and detours.", updateFrequency: "hourly", status: "planned", lastSync: new Date().toISOString() },
  { name: "NDVI / Vegetation Anomalies", category: "Shock", geographicLevel: "county", description: "Satellite-derived crop / vegetation stress.", updateFrequency: "weekly", status: "planned", lastSync: new Date().toISOString() },
];

const statusVariant = { mock: "secondary", live: "default", planned: "outline" } as const;

const Sources = () => (
  <AppShell>
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold">Data source registry</h1>
        <p className="mt-1 text-sm text-muted-foreground">All signals feeding the model. MVP runs on mock data; adapters are ready for live integrations.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {SOURCES.map((s) => (
          <Card key={s.name}>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-base">{s.name}</CardTitle>
                <Badge variant={statusVariant[s.status]} className="capitalize">{s.status}</Badge>
              </div>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <p>{s.description}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <Badge variant="outline">{s.category}</Badge>
                <Badge variant="outline" className="capitalize">{s.geographicLevel}</Badge>
                <Badge variant="outline">{s.updateFrequency}</Badge>
                <span className="text-[11px]">Last sync: {format(new Date(s.lastSync), "PP")}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  </AppShell>
);

export default Sources;
